import os
import sqlite3
import subprocess
import argparse
import json
from services.llm_provider import ClaudeCLIProvider, LLMProvider

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class BlogOrchestrator:
    def __init__(self, llm_engine: LLMProvider):
        self.db_path = os.path.join(BASE_DIR, "blog_agent.db")
        self.repo_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        self.llm = llm_engine

    def _run_cmd(self, cmd):
        """기본 명령 실행"""
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=self.repo_root, encoding='utf-8'
        )

    def _run_cmd_safe(self, cmd, error_msg="Command failed"):
        """에러 핸들링이 강화된 명령 실행 (Fail-Fast)"""
        result = self._run_cmd(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"{error_msg}\nSTDERR: {result.stderr}")
        return result

    def get_issue_content(self, issue_id):
        """이슈 본문과 코멘트를 결합하여 가공 소스 생성 (JSON 안전 파싱)"""
        res = self._run_cmd(f"gh issue view {issue_id} --json body,comments")
        if res.returncode != 0:
            raise RuntimeError(f"Failed to fetch issue #{issue_id}: {res.stderr}")
        
        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from gh CLI for issue #{issue_id}: {e}")
        
        combined_content = f"Main Intent: {data.get('body', '')}\n\n"
        for comment in data.get('comments', []):
            combined_content += f"Additional Detail: {comment.get('body', '')}\n"
        
        return combined_content

    def update_status(self, issue_id, status_id):
        """작업 상태 업데이트 (컨텍스트 매니저 사용)"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE blog_tasks SET status_id = ?, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ?",
                (status_id, issue_id)
            )
            conn.commit()

    def process_task(self):
        # 1. 대상 조회
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT issue_id, file_path FROM blog_tasks WHERE status_id IN (1, 2)")
            tasks = cur.fetchall()

        for issue_id, file_path in tasks:
            try:
                print(f"🤖 Processing Issue #{issue_id}...")
                
                # 2. 데이터 수집
                source_content = self.get_issue_content(issue_id)
                
                # 3. 경로 보안 검증 및 템플릿 로드
                full_path = os.path.normpath(os.path.join(self.repo_root, file_path))
                if not full_path.startswith(self.repo_root):
                    raise ValueError(f"Security Alert: Path escape detected - {file_path}")
                if not os.path.exists(full_path):
                    raise FileNotFoundError(f"Template not found: {full_path}")
                
                with open(full_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                    template = f.read()
                
                # 4. LLM 가공
                final_md = self.llm.generate_post(template, source_content)
                
                # 5. 파일 업데이트
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(final_md)
                
                # 6. Git 워크플로우 (안전한 실행)
                self._run_cmd_safe(f"git add {file_path}", "Git add failed")
                self._run_cmd_safe(
                    f'git commit -m "Auto: Blog Post #{issue_id} finalized"',
                    "Git commit failed"
                )
                self._run_cmd_safe(
                    f"git push origin $(git branch --show-current)",
                    "Git push failed"
                )
                
                # 7. PR 생성 (중복 방지 로직)
                current_branch = self._run_cmd("git branch --show-current").stdout.strip()
                pr_check = self._run_cmd(f'gh pr list --head {current_branch} --json number')
                
                if pr_check.stdout.strip() == "[]":
                    self._run_cmd_safe(
                        f'gh pr create --title "Blog: #{issue_id} 가공완료" '
                        f'--body "에이전트 자동 생성" --label "auto-post"',
                        "PR creation failed"
                    )
                else:
                    print(f"ℹ️ PR already exists for branch {current_branch}")
                
                self.update_status(issue_id, 4) # COMPLETED
                print(f"✅ Issue #{issue_id} done.")
                
            except Exception as e:
                print(f"❌ Critical Error on Issue #{issue_id}: {e}")
                self.update_status(issue_id, 1) # 리셋

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["process", "watchdog"], required=True)
    args = parser.parse_args()

    # 나중에 DeepSeekProvider() 등으로 교체 가능
    engine = ClaudeCLIProvider() 
    orchestrator = BlogOrchestrator(engine)

    if args.mode == "process":
        orchestrator.process_task()
    # watchdog 등 기타 모드 생략