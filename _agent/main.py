import os
import sys
import sqlite3
import subprocess
import re
import argparse
from datetime import datetime, timedelta, timezone

# 1. 환경 및 시간 설정 (KST)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))

class BlogOrchestrator:
    def __init__(self):
        self.db_path = os.path.join(BASE_DIR, "blog_agent.db")
        self.repo_root = os.path.abspath(os.path.join(BASE_DIR, ".."))

    def _run_cmd(self, cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=self.repo_root, encoding='utf-8')

    def update_status(self, issue_id, status_id, result_text=None):
        """SQLite 상태 업데이트 및 결과 저장"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        if result_text:
            cur.execute("UPDATE blog_tasks SET status_id = ?, ai_result = ?, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ?", (status_id, result_text, issue_id))
        else:
            cur.execute("UPDATE blog_tasks SET status_id = ?, updated_at = CURRENT_TIMESTAMP WHERE issue_id = ?", (status_id, issue_id))
        conn.commit()
        conn.close()

    def process_task(self):
        """[MODE: PROCESS] 사용자의 의도를 확인하고 Claude로 가공"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # 가공 대상 (상태 1: INIT 또는 에러 후 재시도 대상) 조회
        cur.execute("SELECT issue_id, file_path FROM blog_tasks WHERE status_id IN (1, 2)")
        tasks = cur.fetchall()
        conn.close()

        for issue_id, file_path in tasks:
            try:
                # 1. 의도 파악 (Llama 8b) - 간단한 YES/NO 체크
                res = self._run_cmd(f"gh issue view {issue_id} --json comments")
                last_comment = re.sub(r'[^a-zA-Z가-힣0-9 ]', '', sys.stdin.read()) # 간단한 필터링 예시
                
                # 2. Claude 호출 (Pro CLI 패턴)
                # 프롬프트에는 Jekyll/Hugo 규격 준수 지시 포함
                full_path = os.path.join(self.repo_root, file_path)
                with open(full_path, 'r') as f: template = f.read()
                
                print(f"🤖 Processing Issue #{issue_id} with Claude...")
                prompt = f"아래 템플릿과 내용을 깃블로그 규격에 맞게 마크다운으로 완성해줘. 결과만 ```markdown ``` 안에 써줘.\n\n{template}"
                claude_res = self._run_cmd(f'claude -p "{prompt}" --output-format text')
                
                # 3. 추출 및 파일 업데이트
                match = re.search(r"```(?:markdown)?\n(.*?)\n```", claude_res.stdout, re.DOTALL)
                if not match: raise Exception("마크다운 추출 실패")
                
                final_md = match.group(1).strip()
                with open(full_path, 'w') as f: f.write(final_md)
                
                # 4. Git Commit & PR
                self._run_cmd(f"git add {file_path}")
                self._run_cmd(f'git commit -m "Auto: Blog Post #{issue_id}"')
                self._run_cmd(f"git push origin $(git branch --show-current)")
                self._run_cmd(f'gh pr create --title "Blog: #{issue_id} 가공완료" --body "에이전트 자동 생성"')
                
                self.update_status(issue_id, 4) # COMPLETED
                
            except Exception as e:
                print(f"❌ Error on #{issue_id}: {e}")
                self.update_status(issue_id, 1) # 리셋하여 재시도 유도
                self._run_cmd(f"gh issue comment {issue_id} --body '⚠️ 에이전트 오류: {str(e)}. 1시간 뒤 재시도합니다.'")

    def watchdog(self):
        """[MODE: WATCHDOG] 48시간 타임아웃 체크"""
        print("⏰ Running Watchdog...")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT issue_id FROM blog_tasks WHERE status_id = 1 AND created_at <= datetime('now', '-2 days')")
        for (issue_id,) in cur.fetchall():
            self._run_cmd(f"gh issue close {issue_id} --comment '48시간 미활동으로 자동 종료'")
            cur.execute("UPDATE blog_tasks SET status_id = 5 WHERE issue_id = ?", (issue_id,))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["process", "watchdog"], required=True)
    args = parser.parse_args()

    agent = BlogOrchestrator()
    if args.mode == "process":
        agent.process_task()
    else:
        agent.watchdog()
