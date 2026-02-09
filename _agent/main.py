import os
import sqlite3
import subprocess
import argparse
import json
import re
import logging
import sys

from datetime import datetime
from services.llm_provider import ClaudeCLIProvider, LLMProvider

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# main.py 상단에 위치해야 합니다.
logging.basicConfig(
    level=logging.INFO, # 또는 logging.DEBUG
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # 🎯 쉘의 리다이렉션을 타기 위해 필요
    ]
)

class BlogOrchestrator:
    def __init__(self, llm_engine: LLMProvider):
        self.db_path = os.path.join(BASE_DIR, "blog_agent.db")
        # 이미 os.path.abspath로 초기화되어 있으므로 경로 검증 시 일관되게 사용
        self.repo_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        self.llm = llm_engine
        self._ensure_schema()

    def _ensure_schema(self):
        """DB 스키마 검증 및 자동 초기화 (QA 관점의 무결성 확보)"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blog_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_id INTEGER UNIQUE NOT NULL,
                    file_path TEXT NOT NULL,
                    status_id INTEGER DEFAULT 1,
                    ai_result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _run_cmd(self, cmd):
        """기본 명령 실행 (Shell 인터프리터 사용)"""
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=self.repo_root, encoding='utf-8'
        )

    def _run_cmd_safe(self, cmd, error_msg="Command failed"):
        """쉘 실행 명령의 에러 핸들링 강화"""
        result = self._run_cmd(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"{error_msg}\nSTDERR: {result.stderr}")
        return result
    
    def _run_git_safe(self, args, error_msg="Git command failed"):
        """리스트 형식을 사용한 안전한 Git 명령 실행 (쉘 인젝션 방어)"""
        result = subprocess.run(
            ['git'] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        if result.returncode != 0:
            raise RuntimeError(f"{error_msg}\nSTDERR: {result.stderr}")
        return result

    # ============================================================================
    # 1. 태스크 동기화 (GitHub Issue -> Local DB)
    # ============================================================================
    def sync_new_issues(self):
        res = self._run_cmd('gh issue list --label "to-blog" --state open --json number,title')
        if res.returncode != 0:
            raise RuntimeError(f"Failed to fetch issues: {res.stderr}")
        
        try:
            issues = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from gh CLI: {e}")

        if not issues:
            print("ℹ️ No new signals detected.")
            return

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            for issue in issues:
                issue_id = issue['number']
                cur.execute("SELECT 1 FROM blog_tasks WHERE issue_id = ?", (issue_id,))
                if cur.fetchone():
                    continue

                # 정밀한 파일명 정제 (파일명 보안 및 유효성 확보)
                date_str = datetime.now().strftime("%Y-%m-%d")
                title = issue.get('title', f"untitled-{issue_id}")
                clean_title = re.sub(r'[^a-zA-Z0-9가-힣]+', '-', title)
                clean_title = re.sub(r'-+', '-', clean_title).strip('-').lower()[:50].rstrip('-')
                
                file_path = f"_posts/{date_str}-{clean_title}.md"
                full_path = os.path.normpath(os.path.join(self.repo_root, file_path))

                if os.path.exists(full_path):
                    file_path = f"_posts/{date_str}-{clean_title}-issue-{issue_id}.md"
                    full_path = os.path.normpath(os.path.join(self.repo_root, file_path))

                # 경로 보안 검증 (일관된 repo_root 사용)
                if not full_path.startswith(self.repo_root):
                    print(f"⚠️ Security Alert: Blocked invalid path {file_path}")
                    continue

                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                template_content = f"""---
layout: post
title: "{title}"
date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S +0900")}
categories: []
tags: []
---

"""
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(template_content)

                cur.execute(
                    "INSERT INTO blog_tasks (issue_id, file_path, status_id) VALUES (?, ?, 1)",
                    (issue_id, file_path)
                )
                print(f"🆕 Registered: Issue #{issue_id} -> {file_path}")
            conn.commit()

    # ============================================================================
    # 2. 가공 및 배포 (Direct Push to Master)
    # ============================================================================
    def process_task(self):
        self.sync_new_issues()

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT issue_id, file_path FROM blog_tasks WHERE status_id IN (1, 2)")
            tasks = cur.fetchall()

        for issue_id, file_path in tasks:
            try:
                print(f"🤖 Processing Issue #{issue_id} and pushing to master...")
                source_content = self.get_issue_content(issue_id)
                full_path = os.path.normpath(os.path.join(self.repo_root, file_path))
                
                if not os.path.exists(full_path):
                    raise FileNotFoundError(f"Template not found: {file_path}")

                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    template = f.read()

                # Claude 가공 요청 (강화된 페르소나 적용 버전)
                final_md = self.llm.generate_post(template, source_content)

                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(final_md)

                # [Pragmatic Git Flow] 바로 마스터에 푸시
                current_branch = self._run_cmd("git branch --show-current").stdout.strip()
                
                self._run_git_safe(['add', file_path])
                self._run_git_safe(['commit', '-m', f'docs: automated technical post #{issue_id}'], "Commit failed")
                self._run_git_safe(['push', 'origin', current_branch], "Push failed")
                
                self.update_status(issue_id, 4) # COMPLETED
                print(f"✅ Issue #{issue_id} successfully pushed to {current_branch}.")

            except Exception as e:
                print(f"❌ Error on Issue #{issue_id}: {e}")
                self.update_status(issue_id, 1) # RETRY 가능하게 복구

    def get_issue_content(self, issue_id):
        res = self._run_cmd(f"gh issue view {issue_id} --json body,comments")
        if res.returncode != 0:
            raise RuntimeError(f"GH Fetch error: {res.stderr}")
        
        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON for issue #{issue_id}: {e}")
        
        content = f"Main: {data.get('body', '')}\n"
        for c in data.get('comments', []): 
            content += f"Comment: {c.get('body', '')}\n"
        return content

    def update_status(self, issue_id, status_id):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE blog_tasks SET status_id = ?, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ?",
                (status_id, issue_id)
            )
            conn.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["process", "watchdog"], required=True)
    args = parser.parse_args()

    # Orchestrator Ignition
    orchestrator = BlogOrchestrator(ClaudeCLIProvider())

    if args.mode == "process":
        orchestrator.process_task()
    elif args.mode == "watchdog":
        orchestrator.sync_new_issues()