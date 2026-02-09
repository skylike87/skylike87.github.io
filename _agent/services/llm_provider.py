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
            "당신은 10년 차 이상의 'Senior Technical Writer'이자 에반젤리스트입니다.\n"
            "주어진 [Content]를 바탕으로, 기술적 깊이와 통찰이 느껴지는 전문 블로그 포스트를 작성하세요.\n"
            "1. 문체: 냉철하면서도 실무적인 시니어 개발자의 톤을 유지할 것.\n"
            "2. 구조: [Template]의 Frontmatter를 유지하되, 본문은 독자가 읽기 좋게 서사적으로 풀어서 설명할 것.\n"
            "3. 디테일: 단순히 나열하지 말고, 각 기술적 결정(예: Atomic Lock)이 왜 중요했는지 의미를 부여할 것.\n"
            "4. 금기: 지어내지 말되(Hallucination 방지), 주어진 사실 간의 논리적 연결은 강화할 것.\n"
            "5. 출력: 오직 마크다운 코드 블록만 반환할 것."
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