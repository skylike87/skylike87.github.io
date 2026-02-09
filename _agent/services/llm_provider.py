import subprocess
import os
import re
from abc import ABC, abstractmethod
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class LLMProvider(ABC):
    @abstractmethod
    def generate_post(self, template: str, content: str) -> str:
        pass

class ClaudeCLIProvider(LLMProvider):
    def __init__(self):
        load_dotenv() # .env 로드
        self.model = os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-20250219")
        self.persona_path = os.path.join(BASE_DIR, os.getenv("PERSONA_PATH", "config/persona.txt"))

    def _load_persona(self):
        """페르소나 파일을 로드 (보안 격리)"""
        if not os.path.exists(self.persona_path):
            return "당신은 전문 기술 블로그 작가입니다." # Fail-safe
        with open(self.persona_path, 'r', encoding='utf-8') as f:
            return f.read()

    def generate_post(self, template: str, content: str) -> str:
        persona = self._load_persona()
        
        system_instruction = (
            f"{persona}\n\n"
            "TASK:\n"
            "주어진 [Content]를 바탕으로 전문 포스트를 작성하세요. [Template] 구조를 유지하세요.\n"
            "CONSTRAINTS:\n"
            "- 불필요한 인사나 워크스페이스 확인 시도를 하지 마세요.\n"
            "- 출력물은 오직 '마크다운 코드 블록' 하나여야 합니다."
        )
        
        prompt = f"{system_instruction}\n\n[Template]\n{template}\n\n[Content]\n{content}"
        
        try:
            cmd = [
                'claude', 
                '--model', self.model, 
                '--output-format', 'text'
            ]
            
            # 🚀 핵심: prompt를 -p 인자가 아닌 input 파라미터로 전달
            res = subprocess.run(
                cmd, 
                input=prompt,  # 표준 입력으로 주입
                capture_output=True, 
                text=True, 
                encoding='utf-8'
            )
            
            if res.returncode != 0:
                raise RuntimeError(f"Claude CLI ({self.model}) 실행 실패: {res.stderr}")
                
            return self._extract_markdown(res.stdout)
            
        except Exception as e:
            raise RuntimeError(f"LLM 가공 중 오류 발생 ({self.model}): {e}")

    def _extract_markdown(self, text: str) -> str:
        match = re.search(r"```(?:markdown)?\n(.*?)\n```", text, re.DOTALL)
        if not match:
            raise ValueError("LLM 응답에서 유효한 마크다운 블록을 찾을 수 없습니다.")
        return match.group(1).strip()