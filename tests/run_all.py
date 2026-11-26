#!/usr/bin/env python3
"""회귀 시험을 모두 돌린다.

산문 계수기, 언어 판정기, 이름 검사기 시험을 차례로 돌리고, 마지막으로 두 가지를 확인한다.
스킬에 든 스크립트 사본이 scripts/ 원본과 같은지 보고, 저장소의 한국어 문서가 보칙을 지키는지 센다.
사본이 어긋나면 Codex 쪽 설치본만 옛 규칙으로 돈다.
"""

import filecmp
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUITES = ["run_prose_tests.py", "run_lang_tests.py", "run_lang_adversarial.py", "run_prose_adversarial.py", "run_identifier_tests.py"]
DOCS = ["README.md", "rules/ko-style-rules.md", "rules/ko-style-examples.md", "skills/ko-style/SKILL.md",
        "output-styles/korean-style.md", "commands/ko-check.md", "docs/guide.md", "docs/references.md"]


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


def check_rules_length():
    """보칙이 SessionStart 주입 상한 안에 드는지 본다.

    Claude Code 는 훅의 additionalContext 를 10,000자로 자른다. 넘으면 파일로 빼고 앞 2,000자만
    보여 준다. 그러면 보칙 대부분이 세션에 들어가지 않는다. 주입 훅은 파일을 그대로 내보내므로
    200자 여유를 두고 9,800자를 문턱으로 둔다.
    """
    bad = []
    # 주입 훅마다 따로 잰다. hooks.json 이 부르는 파일이 모두 있어야 한다.
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
        hooks_json = fh.read()
    names = ["ko-style-rules.md"] + re.findall(r"inject-rules\.sh\\\" ([\w.-]+\.md)", hooks_json)
    for name in names:
        path = os.path.join(ROOT, "rules", name)
        if not os.path.exists(path):
            bad.append(f"hooks.json 이 부르는 {name} 이 없음")
            continue
        with open(path, encoding="utf-8") as fh:
            n = len(fh.read())
        if n > 9800:
            bad.append(f"{name} {n}자, 주입 상한 여유선 9,800자 초과")
    return bad


def check_manifest():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    styles = manifest.get("outputStyles")
    if styles and not os.path.isdir(os.path.join(ROOT, styles)):
        return [f"outputStyles 경로 없음: {styles}"]
    return []


# 논문 근거 항목(31~36항)의 이름. 표본 시험에서 이 항목만 본다.
PAPER_ITEMS = ("이중부정", "헤지 겹쓰기", "사물 존대", "자기 높임", "말투 혼용", "조사 대치", "띄어쓰기")
# bad 표본에 넣은 오류 가운데 계수기가 잡아야 하는 항목. 헤지는 상한 1이라 한 번 나온 bad03 은 걸리지 않는다.
BAD_EXPECT = {
    "bad01.md": {"사물 존대", "자기 높임"},
    "bad02.md": {"사물 존대", "이중부정"},
    "bad03.md": {"조사 대치", "띄어쓰기"},
    "bad04.md": {"사물 존대", "자기 높임", "띄어쓰기"},
}


def check_samples():
    """tests/samples 의 실제 문장 표본으로 논문 근거 항목을 본다(9회차).

    ok 표본은 할수록, 수밖에, 파일이 있으시면, 제가 확인할 테니처럼 헷갈리는 정상 꼴을 많이 담았다.
    여기서 논문 근거 항목이 하나라도 나오면 오탐이다. bad 표본은 넣은 오류가 잡혀야 한다.
    """
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from ko_style_check import check
    bad = []
    folder = os.path.join(HERE, "samples")
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            got = {v["name"].split(" (")[0] for v in check(fh.read())["violations"]}
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            result = check(fh.read())
        # human 표본(19·20회차의 사람 투 글)은 어떤 항목에도 걸리면 안 되고,
        # default 표본(기본 AI 말투)은 하나 이상 걸려야 한다.
        if name.startswith("human") and not result["passed"]:
            bad.append(f"{name}: 사람 투 글 오탐 {[v['name'] for v in result['violations']]}")
        if name.startswith("default") and result["passed"]:
            bad.append(f"{name}: 기본 AI 말투를 놓침")
        got &= set(PAPER_ITEMS)
        if name.startswith("ok") and got:
            bad.append(f"{name}: 오탐 {sorted(got)}")
        if name in BAD_EXPECT and not BAD_EXPECT[name] <= got:
            bad.append(f"{name}: 놓침 {sorted(BAD_EXPECT[name] - got)}")
    return bad


def check_speed():
    """공백 없는 긴 입력에서 이차 시간이 드는 정규식이 다시 들어오지 않았는지 본다.

    Stop 훅의 제한 시간은 15초다. 한 번 6초가 걸린 적이 있어 2초를 문턱으로 둔다.
    """
    import time
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from ko_style_check import check
    from ko_lang_check import judge
    bad = []
    for sample in ["가" * 20000, "a" * 20000, "a." * 10000, "x/" * 10000, "가," * 10000, "a@" * 10000]:
        start = time.time()
        check(sample)
        judge("한국어 질문입니다", sample)
        took = time.time() - start
        if took > 2:
            bad.append(f"{sample[:4]}… {took:.1f}초")
    return bad


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
                      ("매니페스트", check_manifest), ("보칙 길이", check_rules_length),
                      ("실제 문장 표본", check_samples),
                      ("성능", check_speed)):
        bad = fn()
        print(f"{label}: {'통과' if not bad else '실패'}")
        for b in bad:
            print(f"  {b}")
        failed += bool(bad)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
