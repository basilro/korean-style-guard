#!/usr/bin/env python3
"""Stop hook 본체. 훅 입력 JSON 을 stdin 으로 받아 보칙 위반을 센다.

위반이 있으면 stderr 에 보고를 적고 2 로 끝낸다. 모델은 그 내용을
다음 지시로 받아 답변을 고쳐서 다시 낸다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ko_style_check import check  # noqa: E402

HANGUL = re.compile(r"[가-힣]")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # 이미 이 훅 때문에 다시 돌고 있으면 통과시킨다. 무한 루프 방지.
    if payload.get("stop_hook_active"):
        return 0

    message = payload.get("last_assistant_message") or ""

    # 한글이 없으면 한국어 답변이 아니므로 검사하지 않는다.
    if not HANGUL.search(message):
        return 0

    result = check(message)
    if result["통과"]:
        return 0

    lines = ["직전 답변이 한국어 보칙을 어겼습니다.", "보칙 위반"]
    for f in result["위반"]:
        line = f"  {f['항목']}: {f['검출']}건 (허용 {f['허용']})"
        if f["상세"]:
            line += f"  ← {f['상세']}"
        lines.append(line)
    lines += [
        "",
        "해당 부분을 고쳐서 답변을 다시 내주세요. 내용은 그대로 두고 서식만 바꿉니다.",
        "고친 뒤에는 무엇을 고쳤는지 한 줄로만 알리고 전체를 다시 설명하지 마세요.",
    ]
    print("\n".join(lines), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
