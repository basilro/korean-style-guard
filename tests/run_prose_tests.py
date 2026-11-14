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
    ("cleft_twice",
     "지금 필요한 것은 속도입니다. 핵심은 정확도입니다.",
     ["분열문 강조 (중요한 것은 X)"], []),
    ("cleft_mid_ok",
     "이 문제는 어제 고쳤습니다. 그 핵심은 로그에 남겼습니다.",
     [], ["분열문 강조 (중요한 것은 X)"]),
    ("wrapup_twice",
     "캐시를 비웠습니다. 결국 속도가 돌아왔습니다. 요컨대 설정이 원인이었습니다.",
     ["결산 표지 (결국, 요컨대, ~하는 이유다)"], []),
    ("wrapup_reason",
     "로그가 비어 있었습니다. 결국 재시작했습니다. 이 값을 따로 둔 이유입니다.",
     ["결산 표지 (결국, 요컨대, ~하는 이유다)"], []),
    ("wrapup_once_ok",
     "세 번 시도했고 결국 성공했습니다. 이유는 권한이었습니다.",
     [], ["결산 표지 (결국, 요컨대, ~하는 이유다)"]),
    ("beyond",
     "이 도구는 단순한 계수기를 넘어 글쓰기 습관을 바꿉니다.",
     ["범위 상승 (단순한 X를 넘어)"], []),
    ("beyond_number_ok",
     "요청이 100건을 넘어 대기열에 쌓였습니다.",
     [], ["범위 상승 (단순한 X를 넘어)"]),
    ("metaphor",
     "느린 응답이 사용자 경험을 잠식합니다.",
     ["생성형 은유"], []),
    ("hollow_caveat",
     "속도는 두 배가 됐습니다. 그러나 과제도 남아 있습니다. 메모리가 늘었습니다.",
     ["내용 없는 반론 문패"], []),
    ("caveat_with_content_ok",
     "속도는 두 배가 됐습니다. 메모리 정리는 과제로 남아 있습니다.",
     [], ["내용 없는 반론 문패"]),
    ("closing_horizon",
     "설정을 바꿨습니다. 캐시를 비웠습니다. 서버를 다시 띄웠습니다. "
     "응답이 빨라졌습니다. 앞으로 이 구조가 표준이 될 것입니다.",
     ["결말부 시간지평 (향후, 앞으로)"], []),
    ("horizon_early_ok",
     "앞으로 할 일을 적었습니다. 설정을 바꿨습니다. 캐시를 비웠습니다. "
     "서버를 다시 띄웠습니다. 응답이 빨라졌습니다.",
     [], ["결말부 시간지평 (향후, 앞으로)"]),
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
