"""로컬 LLM 용 한국어 보칙 가드.

  from localllm import guard, evaluate, check

guard(messages, complete) 로 다시 쓰기까지 건다. evaluate 와 check 는 검사만 한다.
"""
from .guard import check, evaluate, guard, inject_rules, last_user_text

__all__ = ["guard", "evaluate", "check", "inject_rules", "last_user_text"]
