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
# 사람이 더 많이 쓴 것(~를 통해, ~에 대해, 것이다 결말, 문두 접속사)은 AI 판별 신호가 못 되므로
# 여기 두지 않고, 아래 번역투 절에서 빈도 상한으로 따로 센다.

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


# 번역투. 여기부터는 AI 판별 신호가 아니라 자연스러운 한국어의 기준이다.
# 근거는 김정우(2003, 2007), 이근희(2005), 김순영(2012, 새국어생활 22-1), 이희재(2009).
# 사람 글에도 흔하므로 0건을 요구하지 않고 되풀이만 잡는다.

# 영어 전치사(about, through, from, by, in)를 옮긴 조사 구.
# "에 있어서"는 "방에 있어서"(존재)와 겹치므로 보조사나 쉼표가 붙은 꼴과 "데 있어서"만 센다.
PREP_CALQUE = re.compile(
    r"에\s?(?:대해(?:서)?|대한|관해(?:서)?|관한|의해(?:서)?|의한)(?![가-힣])"
    r"|(?:을|를)\s?통(?:해(?:서)?|한|하여)(?![가-힣])"
    r"|로부터"
    r"|에\s?있어서?(?:는|도|,)"
    r"|데\s?있어(?:서)?(?:는|도)?(?![가-힣])"
)

# have 를 옮긴 소유 구문. "인자를 가지고 있다", "권한을 가진".
POSSESS = re.compile(r"(?:을|를)\s?(?:가지고\s?있|가진(?=\s)|갖고\s?있)")

# 피동을 두 번 겹친 꼴. 되다/보이다/쓰이다/잊히다로 충분하다.
DOUBLE_PASSIVE = re.compile(
    r"(?:되어|보여|쓰여|잊혀|읽혀|불려|믿겨|짜여|놓여|닫혀|열려|잡혀|찢겨)(?:지|져|진|짐|집|졌|질)"
)

# 수량어 뒤의 중복 복수 "-들". "여러 파일들", "많은 사용자들이".
PLURAL_DUP = re.compile(
    r"(?:여러|많은|수많은|다양한|각종|몇몇|모든)\s(?:[가-힣]+\s)?[가-힣]+들"
    r"(?=[이가을를은는의과와도에로]|\s|[.,])"
)

# 앞 명사를 받는 3인칭 대명사.
PRONOUN = re.compile(r"(?<![가-힣])(?:그것|그녀|그들)(?:은|는|이|가|을|를|의|에게|과|와|도|만)?(?![가-힣])")

# 문장 끝 "~것이다". "끝날 것입니다"처럼 ㄹ 관형형 뒤의 추측과 예정은 뺀다.
GEOT_END = re.compile(r"([가-힣])\s?것(?:이다|입니다|이에요|이죠)[.!?]")

# 문두 접속사.
SENT_CONJ = re.compile(
    r"^(?:그리고|또한|따라서|그러나|하지만|그래서|그런데|게다가|더불어|한편|그러므로|즉)(?=[\s,])"
)


# 여기부터는 국어 작법서의 기준이다. 김정선(2016), 이오덕(1989), 국립국어원 다듬은 말과 겹말 풀이,
# 스티븐 킹 『유혹하는 글쓰기』. 역시 판별 신호가 아니라 자연스러운 한국어의 기준이다.

# 한자어 뒤의 접미사 "-적". 앞이 두 음절 이상일 때만 센다(목적, 지적, 흔적, 실적은 빠진다).
JUK = re.compile(r"(?<![가-힣])[가-힣]{2,}적(?:인|으로|이다|입니다|이고|일|임)(?![가-힣])")

# 조사 뒤에 "의"를 겹친 일본어투(での, への, との). "과의", "로의"는 결과, 경로 같은 명사와 겹쳐 뺀다.
PARTICLE_UI = re.compile(r"(?:에서|으로|에게|로부터|로서|와|에)의(?=\s)")

# "의"로 끝나는 명사. 관형격 "의"가 이어지는지 볼 때 뺀다.
UI_NOUNS = set("회의 정의 주의 논의 동의 문의 합의 의의 결의 건의 강의 모의 협의 신의 민의 "
               "자의 예의 편의 호의 무의 수의 유의 이의 질의 심의 고의 대의 본의 선의 악의 성의 "
               "창의 상의 하의 내의 견의".split())

# 하다로 충분한 타동사에 붙인 "-시키다".
SIKIDA = re.compile(
    r"(?:소개|교육|연결|입력|완료|종료|실행|설치|해결|적용|반영|구분|분리|설득|대입|배포|"
    r"등록|삭제|저장|변경|수정|개선|발전|향상)시(?:키|켜|켰|킨|킬|킴)"
)

# 영어 과거완료를 옮긴 "-었었-".
PLUPERFECT = re.compile(r"(?:았|었|였|했)었(?=[다습던어고는지])")

# 일본어와 영어에서 온 관용구. 에 다름 아니다, ~을 요하다, 과언이 아니다, one of the most.
CALQUE_IDIOM = re.compile(
    r"다름\s?아니|(?:을|를)\s?요하|과언이\s?아니"
    r"|가장\s[가-힣]+\s(?:[가-힣]+\s)?(?:것\s)?중\s?(?:의\s)?하나"
)

# 겹말. 한자어가 이미 품은 뜻을 고유어로 한 번 더 쓴다.
PLEONASM = re.compile(
    r"미리\s?예(?:약|상|측|비|습|고|매)|과반수\s?이상|과반수를\s?넘|다시\s?재(?:개|발|시작|확인|검토|발송|설치)"
    r"|가장\s?최(?:고|선|대|소|초|상|하|적)|먼저\s?선(?:행|결|착)|함께\s?동(?:행|참|반)"
    r"|남은\s?여생|새로\s?신(?:설|규|축)|서로\s?상(?:호|의)|약\s?[0-9][0-9,.]*\S*\s?정도"
    r"|분명히\s?명시|가까운\s?근(?:처|방)|뒤로\s?후퇴|역전\s?앞"
)

# 강조 부사.
INTENSIFIER = re.compile(
    r"(?<![가-힣])(?:매우|정말|정말로|굉장히|상당히|대단히|무척|너무나|아주|엄청|몹시|극히)(?![가-힣])"
)


def ui_chains(body: str):
    """관형격 "의"가 세 어절 연달아 이어지는 곳을 찾는다(사용자의 설정의 값)."""
    found = []
    for sent in re.split(r"[.!?\n]", body):
        words = sent.split()
        for a, b in zip(words, words[1:]):
            if (len(a) >= 2 and len(b) >= 2 and a.endswith("의") and b.endswith("의")
                    and a not in UI_NOUNS and b not in UI_NOUNS):
                found.append(f"{a} {b}")
    return found

def _has_rieul_batchim(ch: str) -> bool:
    code = ord(ch) - 0xAC00
    return 0 <= code < 11172 and code % 28 == 8


def geot_endings(body: str):
    return [m.group(0) for m in GEOT_END.finditer(body)
            if not _has_rieul_batchim(m.group(1))]


def prose_sentences(body: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(prose_paragraphs(body)))
            if s.strip()]


def sentence_conjunctions(body: str):
    sents = prose_sentences(body)
    return [s for s in sents if SENT_CONJ.search(s)], len(sents)

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

    prep = PREP_CALQUE.findall(body)
    possess = POSSESS.findall(body)
    double_passive = DOUBLE_PASSIVE.findall(body)
    plural_dup = PLURAL_DUP.findall(body)
    pronoun = PRONOUN.findall(body)
    geot = geot_endings(body)
    conj, n_sent = sentence_conjunctions(body)

    juk = JUK.findall(body)
    particle_ui = PARTICLE_UI.findall(body)
    chain = ui_chains(body)
    sikida = SIKIDA.findall(body)
    pluperfect = PLUPERFECT.findall(body)
    idiom = CALQUE_IDIOM.findall(body)
    pleonasm = PLEONASM.findall(body)
    intens = INTENSIFIER.findall(body)

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
    # 긴 문서에서는 800자마다 하나씩 더 허용한다. 짧은 답변의 기준은 셋이다.
    add("전치사 번역투 (~에 대해, ~를 통해, ~로부터)", prep, max(3, len(body) // 800),
        " / ".join(x.strip() for x in prep[:5]))
    add("소유 구문 (~를 가지고 있다)", possess, 1)
    add("이중 피동 (되어지다, 보여지다)", double_passive, 0,
        " / ".join(double_passive[:4]))
    add("중복 복수 (여러 X들)", plural_dup, 1,
        " / ".join(plural_dup[:3]))
    add("3인칭 대명사 (그것, 그녀, 그들)", pronoun, 1)
    add("~것이다 결말", geot, 2, " / ".join(geot[:3]))
    add("문두 접속사", conj, max(1, n_sent // 5),
        " / ".join(c[:14] for c in conj[:3]))
    add("접미사 -적 (효과적인, 구체적으로)", juk, max(3, len(body) // 800),
        " / ".join(juk[:5]))
    add("조사 뒤 -의 (에서의, 와의, 으로의)", particle_ui, 1)
    add("관형격 -의 연쇄 (A의 B의 C)", chain, 0, " / ".join(chain[:3]))
    add("불필요한 -시키다 (소개시키다)", sikida, 0, " / ".join(sikida[:3]))
    add("과거완료 -었었-", pluperfect, 1)
    add("번역투 관용구 (다름 아니다, 요하다, 가장 ~ 중 하나)", idiom, 0,
        " / ".join(idiom[:3]))
    add("겹말 (미리 예약, 과반수 이상)", pleonasm, 0, " / ".join(pleonasm[:3]))
    add("강조 부사 (매우, 정말, 굉장히)", intens, max(2, len(body) // 1000),
        " / ".join(intens[:5]))

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
            "preposition_calque": len(prep),
            "possessive_have": len(possess),
            "double_passive": len(double_passive),
            "redundant_plural": len(plural_dup),
            "third_person_pronoun": len(pronoun),
            "geot_ending": len(geot),
            "sentence_initial_conjunction": len(conj),
            "suffix_jeok": len(juk),
            "particle_ui": len(particle_ui),
            "ui_chain": len(chain),
            "needless_causative": len(sikida),
            "pluperfect": len(pluperfect),
            "calque_idiom": len(idiom),
            "pleonasm": len(pleonasm),
            "intensifier": len(intens),
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
