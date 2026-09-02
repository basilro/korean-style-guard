#!/usr/bin/env python3
"""한글 이름 검사기의 회귀 시험을 돌린다.

tests/expected.txt 에 적힌 대로 케이스마다 잡히는지 넘어가는지 확인한다.
케이스는 마스킹이 무너지기 쉬운 자리를 골라 모은 것이라,
스캐너를 손볼 때마다 이 시험을 먼저 돌려 회귀를 잡는다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

from ko_identifier_check import check  # noqa: E402


def load_expected(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 2)
            rows.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    return rows


def main():
    rows = load_expected(os.path.join(HERE, "expected.txt"))
    failed = []
    for want, name, note in rows:
        path = os.path.join(HERE, "cases", name)
        if not os.path.exists(path):
            failed.append((name, "케이스 파일이 없습니다", ""))
            continue
        with open(path, encoding="utf-8") as fh:
            result = check(fh.read(), path)
        got = "hit" if not result["passed"] else "pass"
        if got != want:
            names = ", ".join(h["name"] for h in result["hits"][:5])
            failed.append((name, f"{want} 를 바랐는데 {got} 입니다", names))

    print(f"케이스 {len(rows)}개 가운데 {len(rows) - len(failed)}개 통과")
    for name, why, extra in failed:
        print(f"  {name}: {why}" + (f" ({extra})" if extra else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
