#!/usr/bin/env python3
"""한국어 출력 보칙 위반을 센다.

코드 블록, 인라인 코드, 프로그램 출력 인용은 검사 대상에서 뺀다.
그 부분의 이모지와 대시는 저자가 쓴 것이 아니기 때문이다.

사용법:
    ko-style-check.py [파일]        파일 또는 stdin 을 검사한다
    ko-style-check.py --json        결과를 JSON 으로 낸다
종료 코드: 위반이 없으면 0, 있으면 1.

반환 구조의 키는 영문이다. 프로그램 인터페이스이므로 다른 도구가 파싱한다.
사람에게 보이는 한국어는 값 쪽에만 둔다.
"""
import json
import re
import sys

# 저자가 쓰지 않은 부분을 먼저 지운다.
MASKS = [
    r"```.*?```",
    r"~~~.*?~~~",
    r"`[^`\n]+`",
    r"(?m)^ {4,}\S.*$",
    r"(?m)^>.*$",
]

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF"
    "\U00002B00-\U00002BFF\U0000FE0F\U0001F1E6-\U0001F1FF]"
)

# 본문 산문에서 서술어 없이 끝난 문장을 센다.
# 헤딩과 목록과 표는 대상이 아니다. 한국어에서 제목과 목차는 명사구가 표준이다.
CLOSERS = "다요까죠오네군"
CONNECTIVES = ("하고", "이고", "으며", "하며", "인데", "는데", "지만", "아서",
               "어서", "하여", "이며", "면서", "거나", "이나")


def strip_noncounting(text: str) -> str:
    out = text
    for pat in MASKS:
        out = re.sub(pat, " ", out, flags=re.S)
    # 부호를 '쓴' 것이 아니라 '논의 대상으로 언급한' 자리는 세지 않는다.
    # 예: 엠대시(—), 엔대시(–). 규칙 자신이 자기 규칙에 걸리는 것을 막는다.
    return re.sub(r"\((\s*[—–]\s*)\)", " ", out)


def unfinished_sentences(body: str):
    prose = []
    for line in body.split("\n"):
        t = line.strip()
        if not t or t.startswith(("#", "-", "*", "|", ">", "=")):
            continue
        if re.match(r"^\d+\.", t):
            continue
        prose.append(t)

    bad = []
    for raw in re.split(r"(?<=[.!?])\s+", " ".join(prose)):
        sent = raw.strip()
        if len(sent) < 12 or not re.search(r"[가-힣]", sent):
            continue
        if not sent.endswith((".", "!", "?")):
            continue
        stem = sent.rstrip(".!?\"'”’) ").rstrip()
        if not stem:
            continue
        if stem.endswith(CONNECTIVES) or stem[-1] not in CLOSERS:
            bad.append(sent)
    return bad


def check(text: str) -> dict:
    body = strip_noncounting(text)
    lines = body.split("\n")

    dash = re.findall(r"—|–|(?<= )--(?= )", body)

    bold_all = re.findall(r"\*\*([^*\n]+)\*\*", body)
    bold_sentence = [b for b in bold_all if re.search(r"(다|요)\.$|[.!?]$", b.strip())]
    bold_lead = [l for l in lines if re.match(r"^\s*\*\*", l)]
    bold_label = [l for l in lines if re.match(r"^\s*\*\*[^*\n]+\*\*\s*:", l)]

    emoji = EMOJI.findall(body)
    bang = re.findall(r"(?<![!\s])!(?!\=)", body)

    heads = [l for l in lines if re.match(r"^#{1,6}\s", l)]
    counted = [h for h in heads if re.search(r"(한|두|세|네|다섯|[0-9]+)\s*가지", h)]

    unfinished = unfinished_sentences(body)

    violations = []

    def add(label, items, limit, detail=""):
        if len(items) > limit:
            violations.append({
                "name": label, "found": len(items),
                "allowed": limit, "detail": detail,
            })

    add("엠·엔 대시", dash, 0)
    add("완결 문장 볼드", bold_sentence, 0,
        " / ".join(b[:28] for b in bold_sentence[:3]))
    add("줄머리 볼드", bold_lead, 0,
        " / ".join(l.strip()[:32] for l in bold_lead[:3]))
    add("볼드 라벨 (**라벨**:)", bold_label, 0,
        " / ".join(l.strip()[:32] for l in bold_label[:3]))
    add("볼드 총량", bold_all, 3)
    add("이모지", emoji, 0, "".join(emoji[:6]))
    add("느낌표", bang, 0)
    add("개수 예고 헤딩", counted, 1,
        " / ".join(h.strip()[:30] for h in counted[:3]))
    add("서술어 없이 끝난 문장", unfinished, 2,
        " / ".join(u[-26:] for u in unfinished[:3]))

    return {
        "violations": violations,
        "passed": not violations,
        "counts": {
            "dash": len(dash),
            "bold": len(bold_all),
            "emoji": len(emoji),
            "exclamation": len(bang),
            "counted_headings": len(counted),
            "unfinished_sentences": len(unfinished),
            "checked_chars": len(body),
        },
    }


def format_report(result: dict) -> str:
    lines = ["보칙 위반"]
    for v in result["violations"]:
        line = f"  {v['name']}: {v['found']}건 (허용 {v['allowed']})"
        if v["detail"]:
            line += f"  ← {v['detail']}"
        lines.append(line)
    return "\n".join(lines)


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
        return 0 if result["passed"] else 1

    if result["passed"]:
        print("보칙 위반 없음")
        return 0

    print(format_report(result))
    return 1


if __name__ == "__main__":
    sys.exit(main())
