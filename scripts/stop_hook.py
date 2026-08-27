#!/usr/bin/env python3
"""Stop 훅 본체. 훅 입력 JSON 을 stdin 으로 받아 보칙 위반을 센다.

두 에이전트의 출력 계약이 다르므로 입력을 보고 갈라진다.

  Claude Code : stderr 에 보고를 적고 2 로 끝낸다.
  Codex       : stdout 에 {"decision":"block","reason":...} 를 적고 0 으로 끝낸다.
                입력에 turn_id 가 있으면 Codex 로 판정한다.

두 경우 모두 reason 이 다음 지시로 전달되어 답변을 고쳐서 다시 내게 만든다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ko_style_check import check, format_report  # noqa: E402

HANGUL = re.compile(r"[가-힣]")

INSTRUCTION = (
    "해당 부분을 고쳐서 답변을 다시 내주세요. 내용은 그대로 두고 서식만 바꿉니다.\n"
    "고친 뒤에는 무엇을 고쳤는지 한 줄로만 알리고 전체를 다시 설명하지 마세요."
)


def build_reason(result: dict) -> str:
    return "\n".join([
        "직전 답변이 한국어 보칙을 어겼습니다.",
        format_report(result),
        "",
        INSTRUCTION,
    ])


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    is_codex = "turn_id" in payload

    # 이미 이 훅 때문에 다시 돌고 있으면 통과시킨다. 무한 루프 방지.
    if payload.get("stop_hook_active"):
        return 0

    message = payload.get("last_assistant_message") or ""

    # 한글이 없으면 한국어 답변이 아니므로 검사하지 않는다.
    if not HANGUL.search(message):
        return 0

    result = check(message)
    if result["passed"]:
        return 0

    reason = build_reason(result)

    if is_codex:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        return 0

    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
