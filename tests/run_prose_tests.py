#!/usr/bin/env python3
"""산문 계수기의 회귀 시험을 돌린다.

케이스마다 기대하는 위반 이름이 나오는지, 나오면 안 되는 것이 안 나오는지 본다.
새 항목의 오탐을 막으려고 사람 글에 흔한 정상 표현을 함께 넣어 둔다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

from ko_style_check import check  # noqa: E402

# (이름, 본문, 나와야 할 위반, 나오면 안 될 위반)
CASES = [
    ("contrast_twice",
     "원인은 캐시가 아니라 권한입니다. 문제는 속도가 아니라 정확도입니다.",
     ["부정 대구 (A가 아니라 B)"], []),
    ("contrast_once_ok",
     "원인은 캐시가 아니라 권한입니다. 설정 파일을 고쳤습니다.",
     [], ["부정 대구 (A가 아니라 B)"]),
    ("contrast_additive_ok",
     "속도뿐만 아니라 정확도도 올랐습니다. 메모리뿐 아니라 디스크도 줄었습니다.",
     [], ["부정 대구 (A가 아니라 B)"]),
    ("contrast_geot",
     "이것은 버그인 것은 아닙니다. 그렇다고 의도한 것이 아닙니다.",
     ["부정 대구 (A가 아니라 B)"], []),
    ("comma_after_connective",
     "파일을 열었고, 내용을 읽으며, 값을 확인하고, 값을 고치지만, 저장하면서, 닫아서, "
     "확인했는데, 문제가 없었습니다.",
     ["연결어미 뒤 쉼표"], []),
    ("comma_nouns_ok",
     "보고, 참고, 사고, 경고, 광고, 재고, 최고 항목을 나열했습니다. "
     "그리고, 그래서, 하지만, 그런데 같은 접속사도 썼습니다.",
     [], ["연결어미 뒤 쉼표"]),
    ("colon_headings",
     "## 설치: 준비\n\n본문입니다.\n\n## 설정: 값 바꾸기\n\n본문입니다.\n",
     ["콜론 부제 헤딩 (X: Y)"], []),
    ("obligation_paragraphs",
     "첫 문단입니다. 이 값을 확인해야 합니다.\n\n"
     "둘째 문단입니다. 캐시를 비워야 합니다.\n\n"
     "셋째 문단입니다. 다시 검토할 필요가 있습니다.\n",
     ["당위로 끝나는 문단"], []),
    ("obligation_list_ok",
     "- 값을 확인해야 합니다.\n- 캐시를 비워야 합니다.\n- 다시 시작해야 합니다.\n",
     [], ["당위로 끝나는 문단"]),
    ("code_masked",
     "예시는 아래와 같습니다.\n\n```\n캐시가 아니라 권한, 속도가 아니라 정확도\n```\n",
     [], ["부정 대구 (A가 아니라 B)"]),
]


def main():
    failed = 0
    for name, text, must, must_not in CASES:
        got = {v["name"] for v in check(text)["violations"]}
        missing = [m for m in must if m not in got]
        extra = [m for m in must_not if m in got]
        if missing or extra:
            failed += 1
            print(f"실패 {name}: 빠짐 {missing} / 잘못 잡음 {extra}")
    print(f"{len(CASES) - failed}/{len(CASES)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
