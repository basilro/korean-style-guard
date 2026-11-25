#!/usr/bin/env python3
"""Stop 훅 본체. 훅 입력 JSON 을 stdin 으로 받아 보칙 위반을 센다.

두 에이전트의 출력 계약이 다르므로 입력을 보고 갈라진다.

  Claude Code : stderr 에 보고를 적고 2 로 끝낸다.
  Codex       : stdout 에 {"decision":"block","reason":...} 를 적고 0 으로 끝낸다.
                입력에 turn_id 가 있으면 Codex 로 판정한다.

두 경우 모두 reason 이 다음 지시로 전달되어 답변을 고쳐서 다시 내게 만든다.

검사는 두 단계다. 먼저 한국어 질문에 영어로 답했는지 보고(ko_lang_check),
다음으로 한국어 답변이 보칙을 지켰는지 센다(ko_style_check).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 문체 계수기는 정규식 60여 개를 컴파일하느라 불러오는 데 40ms 안팎이 든다.
# 한국어 답변일 때만 run() 안에서 불러온다. 영어 답변과 빈 답변은 그 비용을 내지 않는다.
from ko_lang_check import REASON as LANG_REASON  # noqa: E402
from ko_lang_check import judge, prompt_from_payload  # noqa: E402

HANGUL = re.compile(r"[가-힣]")

INSTRUCTION = (
    "해당 부분을 고쳐서 답변을 다시 내주세요. 내용은 그대로 두고 서식만 바꿉니다.\n"
    "고친 답변만 내고 전체를 다시 설명하지 마세요.\n"
    "무엇을 고쳤는지는 적지 마세요. 이 훅이 돌았다는 사실은 사용자가 알 필요가 없고,\n"
    "고쳤다는 한 줄이 답변 끝에 남으면 그것 자체가 군더더기입니다."
)


def build_reason(result: dict) -> str:
    from ko_style_check import format_report
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

    if not isinstance(payload, dict):
        return 0
    try:
        return run(payload)
    except Exception:
        # 검사기 결함으로 훅이 죽으면 사용자는 영문 모를 오류를 본다. 검사를 건너뛰는 편이 낫다.
        return 0


def run(payload: dict) -> int:
    is_codex = "turn_id" in payload

    # 이미 이 훅 때문에 다시 돌고 있으면 통과시킨다. 무한 루프 방지.
    if payload.get("stop_hook_active"):
        return 0

    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return 0

    # 한국어로 물었는데 영어로 답했으면 한국어로 다시 쓰게 한다.
    # 영어 답변에는 한글이 없어 아래 보칙 검사를 그냥 지나가므로 먼저 본다.
    # KO_STYLE_SKIP_LANG=1 이면 건너뛴다.
    if message and os.environ.get("KO_STYLE_SKIP_LANG") != "1":
        verdict = judge(prompt_from_payload(payload), message)
        if verdict["flagged"]:
            return emit(LANG_REASON, is_codex)

    # 한글이 없으면 한국어 답변이 아니므로 검사하지 않는다.
    if not HANGUL.search(message):
        return 0

    from ko_style_check import check
    result = check(message)
    if result["passed"]:
        return 0

    return emit(build_reason(result), is_codex)


def emit(reason: str, is_codex: bool) -> int:
    if is_codex:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        return 0
    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
