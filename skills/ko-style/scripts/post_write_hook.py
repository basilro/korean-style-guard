#!/usr/bin/env python3
"""PostToolUse 훅. 방금 쓴 산문 파일이 보칙을 지켰는지 센다.

Stop 훅은 대화 답변만 본다. 도구로 쓴 파일은 그 시야 밖이라 이 훅이 맡는다.

대상을 좁게 잡는다. 코드 파일에 서식 규칙을 들이대면 오탐이 쏟아지기 때문이다.
  - 확장자가 산문 문서인 것만 본다
  - 한글이 일정 비율 넘는 파일만 본다
  - 남이 관리하는 트리는 건너뛴다

KO_STYLE_SKIP_FILES=1 이면 아무것도 하지 않는다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ko_style_check import check, format_report  # noqa: E402

PROSE_EXT = {".md", ".markdown", ".mdx", ".txt", ".rst"}
SKIP_PARTS = {".git", "node_modules", "vendor", "dist", "build",
              "__pycache__", ".venv", "site-packages", ".cache"}
MIN_HANGUL_RATIO = 0.15
MIN_CHARS = 100

HANGUL = re.compile(r"[가-힣]")


def target_path(payload: dict):
    resp = payload.get("tool_response") or {}
    inp = payload.get("tool_input") or {}
    for v in (resp.get("filePath"), resp.get("file_path"), inp.get("file_path")):
        if isinstance(v, str) and v:
            return v
    return None


def should_check(path: str) -> bool:
    if os.path.splitext(path)[1].lower() not in PROSE_EXT:
        return False
    if SKIP_PARTS & set(os.path.normpath(path).split(os.sep)):
        return False
    return os.path.isfile(path)


def main() -> int:
    if os.environ.get("KO_STYLE_SKIP_FILES"):
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    path = target_path(payload)
    if not path or not should_check(path):
        return 0

    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return 0

    if len(text) < MIN_CHARS:
        return 0
    if len(HANGUL.findall(text)) / len(text) < MIN_HANGUL_RATIO:
        return 0

    result = check(text)
    if result["passed"]:
        return 0

    reason = "\n".join([
        f"방금 쓴 {os.path.basename(path)} 가 한국어 보칙을 어겼습니다.",
        format_report(result),
        "",
        "해당 부분만 고쳐 주세요. 내용은 그대로 두고 서식만 바꿉니다.",
        "이 파일이 다른 프로젝트의 관례를 따라야 한다면 고치지 말고 그렇게 알려 주세요.",
    ])

    if "turn_id" in payload:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        return 0

    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
