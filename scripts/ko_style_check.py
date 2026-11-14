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


# 부정 대구. "A가 아니라 B", "~것은 아니다". im-not-ai 실측에서 사람 글의 12배였고
# 모델과 과업을 바꿔도 흔들리지 않은 유일한 신호다. 첨가의 "뿐(만) 아니라"는 대구가 아니다.
CONTRAST = re.compile(
    r"(?<!뿐만 )(?<!뿐 )(?<!뿐만)(?<!뿐)아니라(?![가-힣])"
    r"|것(?:은|이)\s?(?:아니다|아닙니다|아니에요|아니죠)"
)

# 연결어미 바로 뒤의 쉼표. KatFish(ACL 2025)에서 사람과 LLM 을 가장 잘 가른 표기 신호다.
# 명사로 끝나는 말(보고, 참고, 사고)을 잡지 않도록 어미 형태를 좁혀 둔다.
COMMA_ENDINGS = ("하고", "되고", "이고", "있고", "없고", "았고", "었고", "했고", "였고",
                 "겠고", "지고", "으며", "하며", "이며", "되며", "지만", "면서",
                 "아서", "어서", "해서", "되어서", "는데", "은데", "인데")
# 문두 접속사는 연결어미가 아니다.
COMMA_EXEMPT = ("그리고", "그래서", "그런데", "하지만", "그러면서", "그러고")
COMMA_AFTER = re.compile(r"([가-힣]+),")

# 문단 끝의 당위. 앞에서 한 번 쓰면 충분한데 문단마다 같은 자리에 되풀이된다.
OBLIGATION = re.compile(
    r"(?:야\s?(?:한다|합니다|해요|하죠)|필요가\s?있(?:다|습니다|어요))"
    r"[.!]?[\"'”’)]*$"
)


# 어휘 항목. im-not-ai 의 사람 60편 대 AI 99편 대조(2026-08-29)와 사람 532편 실측에서
# 사람 쪽이 0건이거나 AI 쪽이 몇 배 많고, 모델을 바꿔도 방향이 유지된 것만 넣는다.
# 사람이 더 많이 쓴 것(~를 통해, ~에 대해, 것이다 결말, 문두 접속사)은 일부러 뺐다.

# 분열문 강조 (D-8). "필요한 것은 X다", "핵심은 X다". 사람 0.09 대 AI 0.92, 약 10배.
CLEFT = re.compile(
    r"(?:필요한|중요한|핵심적인|주목할|눈여겨볼)\s?(?:것|점)은"
    r"|(?:^|(?<=[.!?,]\s)|(?<=[.!?,]))\s*(?:문제는|핵심은|관건은|답은)\s",
    re.M,
)

# 결산 표지 (D-1, D-9, D-10). 결산 부사와 "~하는 이유다" 도치 결말.
# 사람의 "결국"은 서사 귀결에만 쓰이고 논리 결산용은 0건이었다.
WRAPUP = re.compile(
    r"결론적으로|요약하면|요약하자면|종합하면|종합하자면|정리하자면|요컨대"
    r"|(?<![가-힣])결국(?![가-힣])"
    r"|이유(?:다|입니다|예요|이다)[.!]?(?=\s|$)",
    re.M,
)

# 범위 상승 (A-21). "단순한 X를 넘어 Y". 사람 60편 0건, AI 12편.
BEYOND = re.compile(r"단순(?:한|히)?\s?[가-힣\s]{0,12}?(?:을|를)\s?넘어")

# 생성형 은유 (D-14). 사람 532편에서 0건이었던 여덟 가지.
# 회계 용어로 굳은 "자본잠식", "비용이 수익을 잠식" 은 은유가 아니라 술어이므로 뺀다.
METAPHOR = re.compile(
    r"(?<!자본)(?<!자본 )(?<!비용)(?<!비용 )(?<!수익)(?<!수익 )(?<!비용이 수익 )(?<!수익을 )잠식|청사진|적신호|경고등|신호탄|움켜쥐|움켜잡|뿌리내리|뿌리를 내리|짓누르|짓눌"
)

# 내용 없는 반론 문패 (D-12). 독립 문장으로 쓴 경우만 센다. 사람 0건, AI 8편.
HOLLOW_CAVEAT = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:그러나\s|하지만\s|다만\s)?"
    r"(?:과제도|한계도|아쉬운 점도|숙제도|우려도)\s?"
    r"(?:남아\s?있|분명하|존재하|있)(?:다|습니다|어요)[.]",
    re.M,
)

# 결말부 시간지평 (D-11). 본문 뒤쪽 30% 에서 "향후", "앞으로"로 여는 문장.
# 위치를 빼면 사람도 쓰지만, 결말 위치에서는 사람 0건 대 AI 12편이었다.
HORIZON = re.compile(r"^(?:향후|앞으로|장기적으로|중장기적으로|머지않아)(?:는|에는)?[\s,]")


def closing_horizon(body: str):
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(prose_paragraphs(body)))
             if s.strip()]
    if len(sents) < 4:
        return []
    start = int(len(sents) * 0.7)
    return [s for s in sents[start:] if HORIZON.search(s)]


def prose_paragraphs(body: str):
    """헤딩과 목록과 표를 뺀 본문 문단을 돌려준다."""
    paras, cur = [], []
    for line in body.split("\n"):
        t = line.strip()
        skip = (not t or t.startswith(("#", "-", "*", "|", ">", "="))
                or re.match(r"^\d+[.)]", t))
        if skip:
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        cur.append(t)
    if cur:
        paras.append(" ".join(cur))
    return paras


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

    contrast = CONTRAST.findall(body)
    comma_after = [w for w in COMMA_AFTER.findall(body)
                   if w.endswith(COMMA_ENDINGS) and w not in COMMA_EXEMPT]
    colon_heads = [h for h in heads if re.search(r"\S\s*[:：]\s+\S", h)]
    obligation = [p for p in prose_paragraphs(body) if OBLIGATION.search(p)]

    cleft = CLEFT.findall(body)
    wrapup = WRAPUP.findall(body)
    beyond = BEYOND.findall(body)
    metaphor = METAPHOR.findall(body)
    caveat = HOLLOW_CAVEAT.findall(body)
    horizon = closing_horizon(body)

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
    add("부정 대구 (A가 아니라 B)", contrast, 1)
    add("연결어미 뒤 쉼표", comma_after, 5,
        " / ".join(w + "," for w in comma_after[:4]))
    add("콜론 부제 헤딩 (X: Y)", colon_heads, 1,
        " / ".join(h.strip()[:30] for h in colon_heads[:3]))
    add("당위로 끝나는 문단", obligation, 2,
        " / ".join(p[-26:] for p in obligation[:3]))
    add("분열문 강조 (중요한 것은 X)", cleft, 1,
        " / ".join(c.strip() for c in cleft[:3]))
    add("결산 표지 (결국, 요컨대, ~하는 이유다)", wrapup, 1,
        " / ".join(w for w in wrapup[:4]))
    add("범위 상승 (단순한 X를 넘어)", beyond, 0,
        " / ".join(b for b in beyond[:3]))
    add("생성형 은유", metaphor, 0, " / ".join(metaphor[:4]))
    add("내용 없는 반론 문패", caveat, 0)
    add("결말부 시간지평 (향후, 앞으로)", horizon, 0,
        " / ".join(h[:26] for h in horizon[:2]))

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
            "negative_contrast": len(contrast),
            "comma_after_connective": len(comma_after),
            "colon_headings": len(colon_heads),
            "obligation_paragraphs": len(obligation),
            "cleft_emphasis": len(cleft),
            "wrapup_markers": len(wrapup),
            "beyond_escalation": len(beyond),
            "generative_metaphor": len(metaphor),
            "hollow_caveat": len(caveat),
            "closing_horizon": len(horizon),
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
