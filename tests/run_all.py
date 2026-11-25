#!/usr/bin/env python3
"""회귀 시험을 모두 돌린다.

산문 계수기, 언어 판정기, 이름 검사기 시험을 차례로 돌리고, 마지막으로 두 가지를 확인한다.
스킬에 든 스크립트 사본이 scripts/ 원본과 같은지 보고, 저장소의 한국어 문서가 보칙을 지키는지 센다.
사본이 어긋나면 Codex 쪽 설치본만 옛 규칙으로 돈다.
"""

import filecmp
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUITES = ["run_prose_tests.py", "run_lang_tests.py", "run_identifier_tests.py"]
DOCS = ["README.md", "rules/ko-style-rules.md", "skills/ko-style/SKILL.md",
        "output-styles/korean-style.md", "commands/ko-check.md"]


def check_sync():
    src = os.path.join(ROOT, "scripts")
    dst = os.path.join(ROOT, "skills", "ko-style", "scripts")
    bad = []
    for name in sorted(os.listdir(src)):
        if not name.endswith(".py"):
            continue
        other = os.path.join(dst, name)
        if not os.path.exists(other) or not filecmp.cmp(os.path.join(src, name), other, shallow=False):
            bad.append(name)
    return bad


def check_docs():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from ko_style_check import check
    bad = []
    for rel in DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            result = check(fh.read())
        if not result["passed"]:
            bad.append(f"{rel}: " + ", ".join(v["name"] for v in result["violations"]))
    return bad


def check_manifest():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    styles = manifest.get("outputStyles")
    if styles and not os.path.isdir(os.path.join(ROOT, styles)):
        return [f"outputStyles 경로 없음: {styles}"]
    return []


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    failed = 0
    for suite in SUITES:
        r = subprocess.run([sys.executable, os.path.join(HERE, suite)], env=env,
                           capture_output=True, text=True, encoding="utf-8")
        last = (r.stdout.strip().splitlines() or ["(출력 없음)"])[-1]
        print(f"{suite}: {last}")
        if r.returncode != 0:
            failed += 1
            print(r.stdout)
            print(r.stderr)
    for label, fn in (("사본 일치", check_sync), ("문서 자기 검사", check_docs),
                      ("매니페스트", check_manifest)):
        bad = fn()
        print(f"{label}: {'통과' if not bad else '실패'}")
        for b in bad:
            print(f"  {b}")
        failed += bool(bad)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
