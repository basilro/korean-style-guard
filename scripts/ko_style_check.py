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
    # 줄 단위 마스크는 줄을 넘지 않게 [^\n] 으로 쓴다. 아래에서 re.S 로 돌리므로
    # ".*" 로 쓰면 인용 한 줄 뒤의 본문이 끝까지 지워진다(2회차 검토에서 찾았다).
    r"(?m)^ {4,}\S[^\n]*$",
    r"(?m)^[ \t]*>[^\n]*$",
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
    r"|(?<![그이저])것(?:은|이)\s?아니라고"
)

# 연결어미 바로 뒤의 쉼표. KatFish(ACL 2025)에서 사람과 LLM 을 가장 잘 가른 표기 신호다.
# 명사로 끝나는 말(보고, 참고, 사고)을 잡지 않도록 어미 형태를 좁혀 둔다.
COMMA_ENDINGS = ("하고", "되고", "이고", "있고", "없고", "았고", "었고", "했고", "였고",
                 "겠고", "지고", "으며", "하며", "이며", "되며", "지만", "면서",
                 "아서", "어서", "해서", "되어서", "는데", "은데", "인데")
# 문두 접속사는 연결어미가 아니다.
COMMA_EXEMPT = ("그리고", "그래서", "그런데", "하지만", "그러면서", "그러고")
# 어절 첫머리에서만 시작한다. 뒤보기가 없으면 공백 없는 긴 한글에서 이차 시간이 든다.
COMMA_AFTER = re.compile(r"(?<![가-힣])([가-힣]+),")

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
    r"|이유(?:다|입니다|예요|이다)[.!]?(?=\s|$)"
    r"|(?:^|(?<=[.!?]\s))(?:정리하면|정리해\s?보면)(?=[\s,])"
    # 접속사를 지운 자리를 채운 도치 결말(6회차 검토). 사람 글 419만 자에서 0건.
    r"|(?:이유|까닭)(?:이|가|도|는) (?:바로 )?(?:여기|이것|이 점|이 때문)(?:에|이)? ?있(?:습니다|다|어요)"
    r"|것도 (?:다 )?(?:이|그) ?때문(?:입니다|이다|이에요)",
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

# 묻지 않은 후속 제안 (11항). "추가로 궁금한 점이 있으시면 말씀해 주세요"로 닫는 꼴.
# 고객센터 안내처럼 연락처를 알려 주는 문장은 "말씀, 알려, 물어, 질문"으로 끝나지 않아 빠진다.
FOLLOWUP = re.compile(
    r"(?:궁금한|궁금하신|필요한|필요하신|추가)[가-힣\s]{0,12}?(?:점|사항|부분|내용|문구|것)[이가]?\s?"
    r"(?:있으시|있으면|생기시|생기면)[가-힣]*\s(?:언제든(?:지)?\s|편하게\s)*(?:말씀|알려|물어|질문)"
)

# 권고 꼬리 되풀이. "~하는 것이 좋습니다/바람직합니다/권장됩니다"가 문단마다 같은 자리에 온다.
# 7항(당위 되풀이)과 같은 취지다. 1회차 표본 넷에서 다섯 번 나왔고 사람 글에서는 10만 자당 0.8건이었다.
RECOMMEND = re.compile(
    r"[가-힣]\s?것이\s?(?:좋습니다|좋겠습니다|좋아요|좋다|좋겠다|바람직합니다|바람직하다|권장됩니다|권장된다"
    r"|중요합니다|중요해요)"
)

# 감상형 결말 (11항). 마지막 두 문장에서만 센다. "~하는 것은 어떨까요?", "읽어 볼 가치가 있는 책",
# "하루의 쉼표가 되어 줄 것입니다". 사람 논문 0건이지만 장르가 달라 검증력이 약하므로 위치를 좁힌다.
CLOSING_SENTIMENT = re.compile(
    r"(?:것은|것도|건|면)\s?어떨까요"
    r"|(?:볼|읽어\s?볼|들어\s?볼|가\s?볼)\s?(?:만한\s)?가치가\s?(?:있|충분)"
    r"|(?:되어|돼)\s?(?:줄|드릴)\s?(?:것|거)"
)

# 문단 머리 접속 부사로 짠 작문 틀(24항). 문장 단위 상한은 문단 머리의 "우선, 또한, 물론, 결국"을 놓친다.
# 사람 논문에서 문단 머리 표지 비율은 0.205였다. 문단 넷 이상, 표지로 연 문단 셋 이상, 60% 이상일 때만 센다.
PARA_MARKER = re.compile(
    r"^(?:우선|먼저|또한|물론|결국|특히|다만|그리고|하지만|그러나|그래서|그런데|따라서|게다가|더불어|한편)(?=[\s,])"
)

# 끝맺음 제안의 나머지 꼴. 본문 마지막 두 문장에서만 센다. 같은 말이 본문 중간에 오면
# 실제로 정보를 청하는 문장일 수 있다. 안내문의 "문의해, 연락해, 요청해"는 정상이라 넣지 않는다.
CLOSING_OFFER = re.compile(
    r"(?:필요하시면|필요하면|원하시면|원하면|더\s?알고\s?싶)[^.!?]{0,40}"
    r"(?:말씀해|알려|질문해|물어봐)\s?(?:주세요|주십시오|줘|주시면|주시기)"
    r"|(?:공유해|보내|알려)\s?주시면[^.!?]{0,30}(?:도와|안내해|확인해|살펴|조정해|맞춰|다듬어|정리해)\s?드(?:리|릴)"
    r"|(?:어려우시면|막막하시면|고민되시면|어려우면|막막하면)[^.!?]{0,40}(?:말씀해|알려|질문해|물어봐)\s?(?:주세요|주십시오|줘)"
    r"|(?:필요하시면|필요하면|원하시면|원하면)[^.!?]{0,40}(?:만들어|정리해|작성해|바꿔|준비해)\s?드릴\s?수\s?있"
)

# 4회차 검토의 상투 표현. 사람 글에서 모두 0건이었다. 기준 말뭉치가 논문이라 증거가 약하므로
# 공감으로 여는 말은 처음 두 문장에서만 센다.
# 어림 표지 겹침: "대략 30분 정도", "0.8%p 정도로 추정되며". 어림은 하나로 충분하다(29항, 32항).
APPROX_STACK = re.compile(
    r"정도로\s?(?:추정|예상)(?:되|됩|된|합|한)|대략(?:적으로)?\s?[0-9][^.!?\n]{0,25}?정도"
)
# "~하는 데 도움이 됩니다"의 되풀이.
HELPS_WITH = re.compile(r"[는은]\s?데\s?(?:큰\s|많은\s)?도움이\s?(?:됩|되|돼|된)")
# 고민을 자연스러운 일로 바꿔 읽는 공감 첫말.
EMPATHY_OPEN = re.compile(
    r"(?:것은|건|것도)\s?(?:아주|매우|충분히|지극히|정말|너무나)?\s?(?:자연스러운|당연한|흔한)\s?"
    r"(?:일|반응|감정|고민)(?:입니다|이에요|이죠|이다|일)"
)
# 안심시키며 닫는 말과 고민을 칭찬으로 바꾸는 말.
EMPATHY_CLOSE = re.compile(
    r"(?:어떤|어느)\s?(?:선택|결정)을\s?(?:하시|하|내리시|내리)더라도|후회가\s?(?:적|없|덜)을\s?(?:것|거)"
    r"|결정은\s?(?:결국\s)?(?:본인|당신|스스로)의\s?몫|(?:다는|라는)\s?(?:증거|뜻|의미)이기도\s?(?:합니다|해요|하다)"
)
# 빈 면책 문장.
HOLLOW_DISCLAIMER = re.compile(
    r"(?:일반적인|참고용)\s?정보(?:이며|이고|입니다|일\s?뿐)|개인(?:에\s?따라|마다)\s?(?:효과가|결과가|차이가)\s?(?:다를|있을)\s?수"
)

# 받는 쪽(부서, 담당자, 연락처)을 밝힌 안내. 후속 제안에서 뺀다.
ELSEWHERE = re.compile(r"[가-힣0-9)]\s?(?:에게|께|에|로|으로|한테)\s?(?:말씀|알려|질문|물어|문의|연락)")

# successfully 직역. 완료 문구는 "저장되었습니다"로 충분하다. 사람 글 0건.
SUCCESSFULLY = re.compile(r"성공적으로\s(?:[가-힣]+\s)?[가-힣]*(?:되었|됐|완료되|완료했)")

# more 직역 "더 많은 X"의 되풀이. 한 번은 허용한다. 사람 글 10만 자당 1.4건.
MORE_MANY = re.compile(r"(?<![가-힣])더\s많은\s")

# 첫머리 예고 (10항). "~에 대해 쉽게 설명해 드릴게요"처럼 할 일을 예고하며 여는 문장.
# 본문 처음 두 문장에서만 센다. 시점이나 조건이 붙은 약속("내일까지 정리해 드리겠습니다")은 뺀다.
OPENER = re.compile(
    r"^(?![^.!?]*(?:까지|내일|오늘|나중에|대로|되면|끝나면|회의에서|따로))"
    r"[^.!?]{0,60}?(?:설명|정리|요약|비교|소개)(?:해|하여)\s?드(?:릴게요|리겠습니다|릴께요)[.!]"
    r"|^(?![^.!?]*(?:까지|내일|오늘\s?중|나중에|대로|되면|끝나면|회의에서|따로))"
    r"[^.!?]{0,60}?(?:알아|살펴)(?:보아요|봐요|볼게요|볼께요|보겠습니다|볼까요|봅시다)[.!?]"
)

# 콜론이 볼드 안에 든 라벨(**일시:**)과 목록 머리 라벨(- **장점**:). 회의록과 공문의
# "일시: 값" 머리글은 표준이므로 볼드만 걷으면 된다. 2회차 검토의 판단이다.
BOLD_LABEL = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?\*\*[^*\n]{1,30}?(?:\*\*\s*[:：]|[:：]\s*\*\*)"
)

# 콜론 앞이 순서 표시인 헤딩(1단계:, 제2장:, Step 3:)은 9항의 콜론 부제가 아니다.
STEP_HEAD = re.compile(
    r"^#{1,6}\s*(?:제\s?)?(?:\d+|[일이삼사오육칠팔구십]+)\s?(?:단계|부|장|절|편|회차|일차|주차|차시)\s*[:：]"
    r"|^#{1,6}\s*(?:Step|STEP|Part|PART|Q|부록)\s?[0-9A-Z]+\s*[:：]"
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
# 활용형까지 본다(가지는, 가집니다, 갖는다). "가방을 가지고 왔다", "시간을 가지고"는 걸리지 않는다.
POSSESS = re.compile(
    r"(?:을|를)\s?(?:가지(?:고\s?있|는(?=\s)|며(?=\s)|게\s?되)|가집니다|가진다|가졌|가진(?=\s)"
    r"|갖고\s?있|갖는(?=\s)|갖습니다|갖는다)"
)

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
PRONOUN = re.compile(
    r"(?<![가-힣])(?:그것|그녀|그들)(?:은|는|이|가|을|를|의|에게|과|와|도|만)?(?![가-힣])"
    r"|(?<![가-힣])(?:이것|그것|저것)들"
)

# 무생물 명사의 복수 "-들"(22항). 영어 복수를 따라 붙인 꼴이다. "사람들", "값들", "파일들"은 목록에 없다.
INANIMATE_PLURAL = re.compile(
    r"(?<![가-힣])(?:요소|단계|방법|호출|기능|설정|항목|요청|결과|함수|변수|모듈|옵션|버전|경우|부분|조건"
    r"|문제|특징|장점|단점|과정|방식|규칙|명령|도구)들(?=[이가을를은는의과와도에로만]|\s|$)"
)

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


# 여기부터는 이 저장소가 읽은 국어학 논문의 기준이다(1.11.0).

# 일본어 이중부정 직역. 金恩愛(2009)의 なければならない 번역례 470개 중 76.6%가 긍정형이었고,
# 오경순(2007)은 "~하지 않으면 안 된다"를 직역투로, "~해야 한다"를 간결한 형태로 보았다.
DOUBLE_NEG = re.compile(r"지\s?않으면\s?안\s?(?:된|돼|됩|되|될)")

# 헤지 겹쓰기. 강수진·이미혜(2019)는 헤지 1,369회 중 "-ㄹ 수 있다"가 79.4%였고,
# 하나로 족한 자리에 둘을 겹친 것("알 수 있을 것이다")을 과잉 사용으로 분류했다.
# "될 수 있을 것 같다"는 구어의 자연스러운 추측이라 "것 같"은 뺀다.
HEDGE_STACK = re.compile(
    r"수\s?있을\s?(?:것(?:이다|입니다|이라|으로|이며|이고)|듯(?:하|합|싶))"
    r"|것으로\s?(?:보일|생각될|판단될|여겨질)\s?수\s?있"
    r"|(?:보인다|생각된다|판단된다)고\s?(?:할|볼)\s?수\s?있"
)

# 사물 주어의 -시-. Yoon(2017)의 모어 화자 70명 평정에서 사물을 높인 문장은 평균 1.62점(5점 척도),
# 사람의 신체와 소유를 높인 문장은 3.34점이었다. 국립국어원은 "나오셨습니다"류를 오용으로 본다.
# 사람과 이어지는 명사(주문, 말씀, 댁, 건강)는 정도의 문제라 넣지 않는다.
THING_NOUNS = ("결과|오류|에러|파일|함수|코드|설정|화면|메뉴|제품|상품|커피|음료|서버|문서|링크"
               "|메시지|버전|업데이트|배송|택배|요금|가격|비용|프로그램|앱|기능|빌드|테스트|로그"
               "|데이터|값|창|버튼|페이지|사이트|계정|비밀번호|설치|작업|명령|응답|요청|이메일|메일")
THING_NOUNS += ("|포인트|쿠폰|적립금|재고|사이즈|색상|옵션|금액|배송비|할인|혜택|점검|시스템|서비스"
                "|매장|좌석|객실|티켓|상품권|영수증|송장")
# 3회차 검토에서 챗봇 말투로 시험했더니 8개 중 1개만 잡혀 넓혔다. 은/는 주어, "적립되셨습니다"처럼
# 한자어+되다, "45,000원이세요", "품절이세요"를 받는다. "쓰실 수 있으세요"의 "수 있으"는 뺀다.
HON_THING = re.compile(
    rf"(?<![가-힣])(?:{THING_NOUNS})(?:이|가|은|는)\s(?:[가-힣0-9,]+\s){{0,2}}(?<!수\s)"
    r"(?:[가-힣]{0,3}되|나오|발생하|뜨|들어가|들어오|도착하|출발하|걸리|열리|닫히|끝나|바뀌)"
    r"(?:세요|셨|십니|시는|시면|실|신)"
    # "파일이 있으시면", "계정이 없으시면"은 청자의 소유를 높인 표준 표현이다(Yoon 2017, 3.34점).
    # 사물 자체를 높인 "재고가 없으십니다", "자리가 있으셨습니다"만 센다.
    rf"|(?<![가-힣])(?:{THING_NOUNS})(?:이|가|은|는)\s(?:[가-힣0-9,]+\s){{0,2}}(?<!수\s)(?:있으|없으)(?:셨|십니)"
    r"|[0-9][0-9,]*\s?원이(?:세요|십니다|셔요|셨)"
    r"|(?<![가-힣])(?:품절|매진|무료)이(?:세요|십니다|셔요)"
)

# 자기 쪽의 -시-. Yoon(2017)에서 "저희 매장은 세일 안 들어가세요"류는 평균 1.61점이었다.
# 같은 절 안에서만 본다. 연결어미에서 절이 끝나면 뒤의 -시-는 청자의 일이다.
SELF_SUBJ = re.compile(
    r"(?<![가-힣])(?:제가|저는|저희가|저희는|저도|저희도|저희\s[가-힣]+(?:은|는|이|가|에서는|에서도|에서))\s"
)
# 청자나 제삼자가 주어로 들어오면 그 뒤의 -시-는 그 사람의 일이다(저는 고객님이 원하시는).
OTHER_SUBJ = re.compile(r"(?:님|께서)(?:이|은|는|께서|께|의|도)?$")
HON_FORM = re.compile(r"(?:시겠|셨|십니|세요|셔요|셔서|시고|시는|신다|실\b)")
# "제가 할 테니 쉬세요", "저도 몰랐어요 확인해 보세요"처럼 -니, -므로, 문장부호 없이 끝난 종결에서도 절이 끝난다.
CLAUSE_END = re.compile(r"(?:면|고|서|니|니까|테니|므로|는데|은데|지만|도록|려고|러|며|게|든지|요|죠|다)[,]?$")


QUOTE_ONLY = re.compile(r"^[\"“'‘「『][^\"”'’」』]+[\"”'’」』][.!?]?$")

FIELD = re.compile(r"^\s*(?:[-*+]\s+)?\*\*([^*\n]{1,12}?)(?:\*\*\s*[:：]|[:：]\s*\*\*)\s*(\S[^\n]*)$")
SENTENCE_VALUE = re.compile(r"[.!?]\s*$|(?:다|요|죠)\s*$|(?:다|요)[.!?]")


def field_blocks(lines):
    """값이 문장이 아닌 짧은 서식 칸이 두 줄 이상 이어진 덩어리의 줄 번호 묶음을 돌려준다."""
    blocks, cur = [], []
    for i, line in enumerate(lines):
        m = FIELD.match(line)
        if m and len(m.group(2)) <= 40 and not SENTENCE_VALUE.search(m.group(2)):
            cur.append(i)
            continue
        if len(cur) >= 2:
            blocks.append(cur)
        cur = []
    if len(cur) >= 2:
        blocks.append(cur)
    return blocks


def _has_nieun_batchim(ch: str) -> bool:
    code = ord(ch) - 0xAC00
    return 0 <= code < 11172 and code % 28 == 4


def self_honorifics(body: str):
    found = []
    for m in SELF_SUBJ.finditer(body):
        words = body[m.end():].split(maxsplit=5)[:4]
        for raw in words:
            w = raw.rstrip(".,!?")
            if OTHER_SUBJ.search(w):
                break
            if HON_FORM.search(w):
                found.append(m.group(0).strip() + " " + w)
                break
            if CLAUSE_END.search(w) or re.search(r"[.?!]$", raw):
                break
            # 관형형(ㄴ 받침, -던)이면 거기서 명사구가 시작되므로 멈춘다. 부정의 "안"은 뺀다.
            if w != "안" and w and (_has_nieun_batchim(w[-1]) or w.endswith("던")):
                break
    return found


# 말투 혼용. Kim(2023)은 하십시오체와 해요체의 혼용은 격식 자리에서도 흔하지만
# 하십시오체와 해체·해라체의 혼용은 관찰되지 않았다고 했다. 그래서 합니다·해요 계열과
# 한다체가 한 답변의 본문에 함께 나올 때만 센다.
ENDING_HON = re.compile(r"(?:니다|니까|시오|요|죠)[.?!]$")
ENDING_PLAIN = re.compile(r"[가-힣](?<!니)다[.?!]$")


def speech_level_mix(body: str):
    """존대 문장과 한다체 문장이 섞인 본문에서 소수 쪽 문장을 돌려준다."""
    hon, plain = [], []
    for s in prose_sentences(body):
        s = re.sub(r"[\"'“”‘’)]+$", "", s.strip())
        if re.search(r"[\"“][^\"”]*$", s):
            continue
        if ENDING_HON.search(s):
            hon.append(s)
        elif ENDING_PLAIN.search(s):
            plain.append(s)
    if len(hon) >= 3 and len(plain) >= 2:
        minority = plain if len(plain) <= len(hon) else hon
        if len(minority) / (len(hon) + len(plain)) >= 0.15:
            return minority
    return []


# 조사 대치. 장석배(2019)의 영어권 학습자 말뭉치에서 "영향, 도움, 관심" 앞에 "에" 대신
# 목적격을 쓴 오류가 따로 분류됐다. 사이에 다른 어절이 없을 때만 잡는다.
PARTICLE_SWAP = re.compile(
    r"[가-힣][을를]\s(?:(?:큰|많은|깊은|좋은|나쁜|가장\s큰)\s)?영향을\s(?:주|줬|준|미치|미쳤|끼치)"
    r"|[가-힣][을를]\s(?:큰\s|많은\s)?관심이\s(?:있|많|없)"
)


# 띄어쓰기. 주지연(2017)이 인용한 신호철 외(2015)의 오표기 빈도에서 1~3위가 모두 의존 명사
# (제43항 단위, 제42항 체언·관형어 뒤)였다. 앞말의 품사로 갈리는 만큼, 대로, 뿐, 데, 지는
# 표면형으로 판정할 수 없어 넣지 않는다. 여기 둔 것은 앞말이 정해진 꼴뿐이다.
#   할수 있다, 할 수있다 (제42항)      하고있다, 하지않다, 하지못하다 (제47항)
#   너때문에 (제42항)                  할 수 밖에 (제41항, 밖에는 조사)
# 될수록, 할수록은 어미 -ㄹ수록이고 수많은, 수없이, 실수는 한 단어라 걸리지 않는다.
SPACING = re.compile(
    r"(?:(?<![가-힣])[할될볼갈올쓸알줄살]|[가-힣]을)수\s?(?:있|없(?!이))"
    r"|(?<=[가-힣])\s수(?:있|없(?!이))"
    r"|[가-힣]고있(?=[는다어었으지을습네])"
    r"|[가-힣]지(?:않[는다아았을습으]|못하)"
    r"|[가-힣]때문(?=에|이)"
    r"|(?<=[가-힣])\s수\s밖에"
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
    # 인용만 감싼 볼드(**"열심히 하겠습니다."**)는 완결 문장 볼드로 세지 않는다. 총량에는 든다.
    bold_sentence = [b for b in bold_all if re.search(r"(다|요)\.$|[.!?]$", b.strip())
                     and not QUOTE_ONLY.match(b.strip())]
    # 서식 칸 목록(- **일시**: 12월 3일)은 웹 공지의 관례라 볼드 라벨로 세지 않고,
    # 볼드 총량에는 덩어리 하나를 1건으로 넣는다.
    fields = field_blocks(lines)
    field_lines = {i for block in fields for i in block}
    bold_all = (bold_all[:len(bold_all) - sum(len(re.findall(r"\*\*[^*\n]+\*\*", lines[i]))
                                              for i in field_lines)]
                + ["(서식 칸 목록)"] * min(1, len(fields)))
    # 볼드만 있는 독립 줄은 헤딩 구실을 하므로 문단을 여는 볼드로 세지 않는다. 총량 상한은 그대로 묶인다.
    # 라벨 볼드는 따로 세고 줄머리 볼드에서는 뺀다. 한 줄이 두 항목에 겹쳐 걸리지 않게 한다.
    bold_label = [l for i, l in enumerate(lines) if BOLD_LABEL.match(l) and i not in field_lines]
    bold_lead = [l for l in lines if re.match(r"^\s*\*\*", l)
                 and not re.match(r"^\s*\*\*[^*\n]+\*\*\s*$", l)
                 and not BOLD_LABEL.match(l)]

    emoji = EMOJI.findall(body)
    bang = re.findall(r"(?<![!\s])!(?!\=)", body)

    heads = [l for l in lines if re.match(r"^#{1,6}\s", l)]
    counted = [h for h in heads if re.search(r"(한|두|세|네|다섯|[0-9]+)\s*가지", h)]

    unfinished = unfinished_sentences(body)

    contrast = CONTRAST.findall(body)
    comma_after = [w for w in COMMA_AFTER.findall(body)
                   if w.endswith(COMMA_ENDINGS) and w not in COMMA_EXEMPT]
    colon_heads = [h for h in heads if re.search(r"\S\s*[:：]\s+\S", h) and not STEP_HEAD.match(h)]
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

    double_neg = DOUBLE_NEG.findall(body)
    hedge = HEDGE_STACK.findall(body)
    hon_thing = HON_THING.findall(body)
    hon_self = self_honorifics(body)
    level_mix = speech_level_mix(body)
    particle_swap = PARTICLE_SWAP.findall(body)
    spacing = SPACING.findall(body)
    sents = prose_sentences(body)
    # "정보보안팀(내선 4410)에 알려 주십시오"처럼 받는 쪽을 밝힌 안내는 답변자에게 되묻게 하는
    # 권유가 아니므로 뺀다(6회차 표본의 오탐).
    followup = [m.group(0) for m in FOLLOWUP.finditer(body) if not ELSEWHERE.search(m.group(0))]
    followup += [s for s in sents[-2:]
                 if (m := CLOSING_OFFER.search(s)) and not ELSEWHERE.search(m.group(0))]
    # 인사말은 3항이 따로 막으므로 첫 두 문장을 고를 때 건너뛴다.
    head = [s for s in sents if not re.match(r"안녕하세요", s)][:2]
    opener = [s for s in head if OPENER.search(s)]
    sentiment = [s for s in sents[-2:] if CLOSING_SENTIMENT.search(s)]
    approx = APPROX_STACK.findall(body)
    helps = HELPS_WITH.findall(body)
    empathy = ([s for s in head if EMPATHY_OPEN.search(s)] + EMPATHY_CLOSE.findall(body))
    disclaimer = HOLLOW_DISCLAIMER.findall(body)
    paras = prose_paragraphs(body)
    led = [p for p in paras if PARA_MARKER.match(p)]
    para_frame = led if len(paras) >= 4 and len(led) >= 3 and len(led) / len(paras) >= 0.6 else []
    recommend = RECOMMEND.findall(body)
    inanimate_pl = INANIMATE_PLURAL.findall(body)
    succ = SUCCESSFULLY.findall(body)
    more_many = MORE_MANY.findall(body)

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
    # 사람 글은 1,000자당 약 1건이었다. 긴 글은 그 두 배(500자당 1건)까지 허용한다.
    # 고정 상한 5 로는 7회차의 2,500자 안팎 문서 여섯 편 중 다섯이 걸렸다.
    add("연결어미 뒤 쉼표", comma_after, max(5, len(body) // 500),
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
    add("이중부정 (~하지 않으면 안 된다)", double_neg, 0)
    # 사람이 쓴 학술 논문에도 한 편에 2~5회 나왔다. 0건을 요구하지 않고 되풀이만 잡는다.
    add("헤지 겹쓰기 (~할 수 있을 것이다)", hedge, 1, " / ".join(h.strip() for h in hedge[:3]))
    add("사물 존대 (결과가 나오셨습니다)", hon_thing, 0, " / ".join(hon_thing[:3]))
    add("자기 높임 (제가 확인하시겠습니다)", hon_self, 0, " / ".join(hon_self[:3]))
    add("말투 혼용 (합니다체와 한다체)", level_mix, 0,
        " / ".join(s[-20:] for s in level_mix[:3]))
    add("조사 대치 (X를 영향을 주다)", particle_swap, 0, " / ".join(particle_swap[:3]))
    add("묻지 않은 후속 제안 (궁금한 점이 있으시면)", followup, 0,
        " / ".join(f[-24:] for f in followup[:2]))
    add("첫머리 예고 (설명해 드릴게요)", opener, 0, " / ".join(o[:24] for o in opener[:2]))
    add("권고 꼬리 (~하는 것이 좋습니다)", recommend, 1, " / ".join(recommend[:3]))
    add("어림 표지 겹침 (대략 ~ 정도)", approx, 1, " / ".join(approx[:2]))
    add("~하는 데 도움이 됩니다 되풀이", helps, 1)
    add("공감·안심 상투 (자연스러운 일입니다)", empathy, 0,
        " / ".join(e[-20:] for e in empathy[:2]))
    add("빈 면책 (일반적인 정보이며)", disclaimer, 1)
    add("감상형 결말 (어떨까요, 가치가 있는)", sentiment, 0, " / ".join(s[-24:] for s in sentiment))
    add("문단 머리 접속 부사 틀", para_frame, 0, " / ".join(p[:6] for p in para_frame[:4]))
    add("무생물 복수 (단계들, 방법들)", inanimate_pl, 1, " / ".join(inanimate_pl[:3]))
    add("성공적으로 ~되었습니다", succ, 0, " / ".join(succ[:2]))
    add("더 많은 X 되풀이", more_many, 1)
    add("띄어쓰기 (할수있다, 하고있다)", spacing, 0, " / ".join(s.strip() for s in spacing[:4]))

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
            "double_negation": len(double_neg),
            "hedge_stack": len(hedge),
            "honorific_thing": len(hon_thing),
            "honorific_self": len(hon_self),
            "speech_level_mix": len(level_mix),
            "particle_swap": len(particle_swap),
            "spacing": len(spacing),
            "followup_offer": len(followup),
            "recommend_tail": len(recommend),
            "inanimate_plural": len(inanimate_pl),
            "closing_sentiment": len(sentiment),
            "approx_stack": len(approx),
            "helps_with": len(helps),
            "empathy_cliche": len(empathy),
            "hollow_disclaimer": len(disclaimer),
            "paragraph_marker_frame": len(para_frame),
            "successfully": len(succ),
            "more_many": len(more_many),
            "opener_preview": len(opener),
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
