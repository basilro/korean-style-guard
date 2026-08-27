#!/usr/bin/env python3
"""한국어 출력 보칙(~/.claude/CLAUDE.md) 위반을 센다.

코드 블록, 인라인 코드, 프로그램 출력 인용은 검사 대상에서 뺀다.
그 부분의 이모지와 대시는 저자가 쓴 것이 아니기 때문이다.

사용법:
    ko-style-check.py [파일]        파일 또는 stdin 을 검사한다
    ko-style-check.py --json        결과를 JSON 으로 낸다
종료 코드: 위반이 없으면 0, 있으면 1.
"""
import json
import re
import sys

# 저자가 쓰지 않은 부분을 먼저 지운다.
MASKS = [
    (r"```.*?```", "코드 블록"),
    (r"~~~.*?~~~", "코드 블록"),
    (r"`[^`\n]+`", "인라인 코드"),
    (r"(?m)^ {4,}\S.*$", "들여쓴 코드"),
    (r"(?m)^>.*$", "인용"),
]


def strip_noncounting(text: str) -> str:
    out = text
    for pat, _ in MASKS:
        out = re.sub(pat, " ", out, flags=re.S)
    # 부호를 '쓴' 것이 아니라 '논의 대상으로 언급한' 자리는 세지 않는다.
    # 예: 엠대시(—), 엔대시(–). 규칙 자신이 자기 규칙에 걸리는 것을 막는다.
    out = re.sub(r"\((\s*[—–]\s*)\)", " ", out)
    return out


EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF"
    "\U00002B00-\U00002BFF\U0000FE0F\U0001F1E6-\U0001F1FF]"
)


def check(text: str) -> dict:
    body = strip_noncounting(text)
    lines = body.split("\n")

    dash = re.findall(r"—|–|(?<= )--(?= )", body)

    # 볼드 세 형태
    bold_all = re.findall(r"\*\*([^*\n]+)\*\*", body)
    bold_sentence = [b for b in bold_all if re.search(r"(다|요)\.$|[.!?]$", b.strip())]
    bold_lead = [l for l in lines if re.match(r"^\s*\*\*", l)]
    bold_label = [l for l in lines if re.match(r"^\s*\*\*[^*\n]+\*\*\s*:", l)]

    emoji = EMOJI.findall(body)
    bang = re.findall(r"(?<![!\s])!(?!\=)", body)

    # 헤딩의 개수 예고 틀
    heads = [l for l in lines if re.match(r"^#{1,6}\s", l)]
    counted = [h for h in heads if re.search(r"(한|두|세|네|다섯|[0-9]+)\s*가지", h)]

    findings = []

    def add(name, n, limit, detail=""):
        if n > limit:
            findings.append({"항목": name, "검출": n, "허용": limit, "상세": detail})

    add("엠·엔 대시", len(dash), 0)
    add("완결 문장 볼드", len(bold_sentence), 0,
        " / ".join(b[:28] for b in bold_sentence[:3]))
    add("줄머리 볼드", len(bold_lead), 0,
        " / ".join(l.strip()[:32] for l in bold_lead[:3]))
    add("볼드 라벨 (**라벨**:)", len(bold_label), 0,
        " / ".join(l.strip()[:32] for l in bold_label[:3]))
    add("볼드 총량", len(bold_all), 3)
    add("이모지", len(emoji), 0, "".join(emoji[:6]))
    add("느낌표", len(bang), 0)
    add("개수 예고 헤딩", len(counted), 1,
        " / ".join(h.strip()[:30] for h in counted[:3]))

    return {
        "위반": findings,
        "통과": not findings,
        "계수": {
            "대시": len(dash), "볼드": len(bold_all), "이모지": len(emoji),
            "느낌표": len(bang), "개수예고헤딩": len(counted),
            "검사한 글자수": len(body),
        },
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv

    if args:
        with open(args[0], encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()

    result = check(text)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["통과"] else 1

    if result["통과"]:
        print("보칙 위반 없음")
        return 0

    print("보칙 위반")
    for f in result["위반"]:
        line = f"  {f['항목']}: {f['검출']}건 (허용 {f['허용']})"
        if f["상세"]:
            line += f"  ← {f['상세']}"
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
