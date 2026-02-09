import subprocess
import re
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def generate_post(self, template: str, content: str) -> str:
        pass

class ClaudeCLIProvider(LLMProvider):
    """
    Claude CLI를 사용하는 공급자.
    모델명을 주입받아 Sonnet, Opus 등을 유연하게 선택 가능.
    """
    def __init__(self, model: str = "claude-3-7-sonnet-20250219"):
        self.model = model

    def generate_post(self, template: str, content: str) -> str:
        # 엄격한 데이터 격리를 위한 시스템 프롬프트 구성
        system_instruction = (
            "당신은 'Pure Data Transformer'입니다. 외부 지식을 배제하고 오직 제공된 [내용]만을 사용하여 포스트를 완성하세요.\n"
            "1. [템플릿]의 Frontmatter와 구조를 100% 유지할 것.\n"
            "2. 주어진 정보가 부족하다면 추측하지 말고 본문의 길이를 조절할 것.\n"
            "3. 답변은 반드시 ```markdown ``` 코드 블록 내에만 작성할 것."
        )
        
        prompt = (
            f"{system_instruction}\n\n"
            f"[템플릿]\n{template}\n\n"
            f"[내용]\n{content}"
        )
        
        try:
            # 사용 중인 CLI가 환경변수(CLAUDE_MODEL)를 지원하는 패턴일 경우
            # 혹은 --model 플래그를 지원하는 경우에 맞춰 호출
            cmd = [
                'claude', 
                '--model', self.model, 
                '-p', prompt, 
                '--output-format', 'text'
            ]
            
            # shell=False로 설정하여 쉘 인젝션을 방지 (리스트 형태 전달)
            res = subprocess.run(
                cmd, capture_output=True, text=True, encoding='utf-8'
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