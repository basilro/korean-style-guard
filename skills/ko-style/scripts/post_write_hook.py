#!/usr/bin/env python3
"""PostToolUse 훅. 방금 쓴 파일이 보칙을 지켰는지 센다.

Stop 훅은 대화 답변만 본다. 도구로 쓴 파일은 그 시야 밖이라 이 훅이 맡는다.

파일 종류에 따라 다른 것을 본다. 두 검사는 조건이 정반대다.
  - 산문 문서는 서식을 본다. 대시와 볼드와 이모지를 센다.
  - 코드 파일은 이름을 본다. 식별자에 한글이 섞였는지 센다.

코드 파일에 서식 규칙을 들이대면 오탐이 쏟아지므로 서로 넘어가지 않게 가른다.

KO_STYLE_SKIP_FILES=1 이면 아무것도 하지 않는다.
KO_STYLE_SKIP_IDENTIFIERS=1 이면 이름 검사만 건너뛴다.
프로젝트의 기존 관례가 한글 이름인 경우를 위한 스위치다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ko_style_check import check, format_report  # noqa: E402
from ko_identifier_check import EXT_LANG  # noqa: E402
from ko_identifier_check import check as check_names  # noqa: E402
from ko_identifier_check import format_report as format_names  # noqa: E402

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


def read_text(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def prose_reason(path: str, text: str):
    if len(text) < MIN_CHARS:
        return None
    if len(HANGUL.findall(text)) / len(text) < MIN_HANGUL_RATIO:
        return None
    result = check(text)
    if result["passed"]:
        return None
    return "\n".join([
        f"방금 쓴 {os.path.basename(path)} 가 한국어 보칙을 어겼습니다.",
        format_report(result),
        "",
        "해당 부분만 고쳐 주세요. 내용은 그대로 두고 서식만 바꿉니다.",
        "이 파일이 다른 프로젝트의 관례를 따라야 한다면 고치지 말고 그렇게 알려 주세요.",
    ])


def identifier_reason(path: str, text: str):
    if os.environ.get("KO_STYLE_SKIP_IDENTIFIERS"):
        return None
    result = check_names(text, path)
    if result["passed"]:
        return None
    return "\n".join([
        f"방금 쓴 {os.path.basename(path)} 에 한글로 된 이름이 있습니다.",
        format_names(result),
        "",
        "코드에 속하는 이름은 영문으로 씁니다.",
        "식별자와 딕셔너리 키와 열거형 값과 파일명이 여기 해당합니다.",
        "화면에 보이는 문자열과 주석은 한국어 그대로 두세요. 이름만 바꿉니다.",
        "이 프로젝트의 기존 관례가 한글 이름이라면 고치지 말고 그렇게 알려 주세요.",
    ])


def main() -> int:
    if os.environ.get("KO_STYLE_SKIP_FILES"):
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    path = target_path(payload)
    if not path or not os.path.isfile(path):
        return 0
    if SKIP_PARTS & set(os.path.normpath(path).split(os.sep)):
        return 0

    ext = os.path.splitext(path)[1].lower()
    if ext in PROSE_EXT:
        handler = prose_reason
    elif ext in EXT_LANG:
        handler = identifier_reason
    else:
        return 0

    text = read_text(path)
    if text is None:
        return 0

    reason = handler(path, text)
    if not reason:
        return 0

    if "turn_id" in payload:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        return 0

    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
