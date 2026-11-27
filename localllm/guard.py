"""로컬 LLM(Qwen 등)에 한국어 보칙을 걸어 주는 공용 코어.

Claude Code 와 Codex 는 하네스가 Stop 훅을 주지만, Ollama·MLX·LM Studio 같은 모델 서버에는
끼어들 훅이 없다. 그래서 끼어드는 지점을 이 함수가 대신한다. 검사와 다시 쓰기 판단은
`scripts/stop_hook.py` 의 함수를 그대로 가져다 쓰므로 동작이 Claude·Codex 와 같다.

흐름은 Stop 훅과 같다.
  1. 보칙을 시스템 메시지에 넣는다(SessionStart 훅 대신).
  2. 모델이 답하면 언어 판정과 보칙 검사를 돌린다.
  3. 걸리면 위반 목록을 붙여 다시 쓰게 한다. 정해진 횟수까지만 되풀이한다.

`complete(messages)` 는 메시지 목록을 받아 답변 문자열을 돌려주는 함수다. 어떤 백엔드든
이 함수 하나만 맞추면 된다(proxy.py 는 OpenAI 호환 서버로 이 함수를 만든다).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from ko_lang_check import judge  # noqa: E402
from ko_style_check import check  # noqa: E402
from stop_hook import (  # noqa: E402
    LANG_REASON,
    build_reason,
    drop_answer_exempt,
    drop_writing_exempt,
)

HANGUL = re.compile(r"[가-힣]")
_RULE_CACHE: dict = {}

PREAMBLE = (
    "아래는 한국어로 답할 때 지켜야 할 문체 보칙입니다. 이 규칙을 따라 처음부터 "
    "자연스러운 한국어로 답하세요. 규칙 본문을 답에 옮기지 마세요.\n\n"
)


def _rules_text(inject: str) -> str:
    """주입할 보칙 본문을 돌려준다. inject 는 'rules', 'rules+examples', 'none'."""
    if inject == "none":
        return ""
    if inject in _RULE_CACHE:
        return _RULE_CACHE[inject]
    parts = [_read("rules/ko-style-rules.md")]
    if inject == "rules+examples":
        parts.append(_read("rules/ko-style-examples.md"))
    text = PREAMBLE + "\n\n".join(p for p in parts if p)
    _RULE_CACHE[inject] = text
    return text


def _read(rel: str) -> str:
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _content_text(content) -> str:
    """OpenAI 메시지의 content 가 문자열이거나 파트 목록이어도 글만 뽑는다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def last_user_text(messages) -> str:
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            return _content_text(m.get("content"))
    return ""


def inject_rules(messages, inject: str = "rules"):
    """보칙을 담은 시스템 메시지를 맨 앞에 끼운 새 목록을 돌려준다. 원본은 두지 않는다."""
    rules = _rules_text(inject)
    if not rules:
        return list(messages)
    return [{"role": "system", "content": rules}] + list(messages)


def evaluate(prompt: str, answer: str, skip_lang: bool = False, lite: bool = None):
    """답을 검사해 다시 쓰게 할 지시를 돌려준다. 통과하면 None.

    stop_hook.run 과 같은 순서다. 한국어 질문에 영어로 답했는지 먼저 보고, 다음으로 보칙을 센다.
    대신 써 주는 공지·메일의 안내와 물결표 띄움은 대화 답변에서 빼는 예외도 그대로 적용한다.
    """
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not skip_lang and judge(prompt, answer)["flagged"]:
        return LANG_REASON
    if not HANGUL.search(answer):
        return None
    result = check(answer, lite=lite)
    if not result["passed"]:
        result = drop_answer_exempt(drop_writing_exempt(result, prompt))
    if result["passed"]:
        return None
    return build_reason(result)


def guard(messages, complete, *, max_rounds: int = 2, inject: str = "rules",
          skip_lang: bool = False, lite: bool = None):
    """보칙을 걸어 답을 받는다.

    messages: OpenAI 형식의 메시지 목록.
    complete: messages 를 받아 답변 문자열을 돌려주는 함수.
    max_rounds: 다시 쓰기 최대 횟수. 그 안에 못 고치면 마지막 답을 그대로 돌려준다.
    lite: 참이면 교정·교열을 빼고 보칙만 건다. 다시 쓰기가 줄어 토큰을 아낀다.
    반환: (답변 문자열, 쓴 다시 쓰기 횟수).
    """
    prompt = last_user_text(messages)
    convo = inject_rules(messages, inject)
    answer = complete(convo)
    rounds = 0
    while rounds < max_rounds:
        reason = evaluate(prompt, answer, skip_lang, lite)
        if reason is None:
            break
        convo = convo + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": reason},
        ]
        answer = complete(convo)
        rounds += 1
    return answer, rounds
