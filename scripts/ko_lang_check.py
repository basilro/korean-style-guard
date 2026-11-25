#!/usr/bin/env python3
"""사용자가 한국어로 물었는데 답변이 영어로 나갔는지 판정한다.

Stop 훅이 부른다. 판정은 일부러 보수적으로 한다. 놓치는 쪽이 잘못 막는 쪽보다 싸다.
잘못 막으면 멀쩡한 답변을 한 번 더 쓰게 되고, 사용자는 그 이유를 알 수 없다.

  1. 사용자 질문: 마지막 사람 입력에서 코드와 경로와 URL을 가린 뒤 단어를 센다.
     한글 단어가 하나 이상이고 한글 단어 비율이 0.3 이상이면 한국어 질문으로 본다.
  2. 예외: 질문에 번역이나 영어 답변을 청하는 말이 있으면 판정하지 않는다.
  3. 답변: 코드 블록, 인라인 코드, 인용, 표, URL, 경로, 식별자, 약어를 가린다.
     남은 산문에서 영어 단어가 MIN_EN_WORDS 이상이고 영어 비율이 EN_RATIO 이상이면 영어 답변이다.

사용법:
    ko_lang_check.py 질문.txt 답변.txt     두 파일을 판정한다(시험용)
반환 구조의 키는 영문이다. 프로그램 인터페이스이므로 다른 도구가 파싱한다.
"""
import json
import re
import sys

MIN_EN_WORDS = 12
EN_RATIO = 0.6
KO_PROMPT_RATIO = 0.3

HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")

# 영어 답변을 사용자가 청한 경우. 이때 영어 답변은 정상이다.
WANTS_ENGLISH = re.compile(
    r"영어로|영문으로|영어\s?(?:답변|버전|문장|원문|이메일|메일|요약)|영작|영역(?:해|하)"
    r"|번역|옮겨\s?(?:줘|주세요|줄래)|translat|in english|english\s?(?:only|version|please)",
    re.I,
)

# 사람이 쓰지 않은 부분. 훅이 붙이는 꼬리표와 명령 출력이 사용자 입력에 섞여 온다.
PROMPT_NOISE = [
    r"<system-reminder>.*?</system-reminder>",
    r"<(command-[a-z-]+|local-command-[a-z-]+|user-prompt-submit-hook|bash-[a-z]+)>.*?</\1>",
    r"<pasted_content[^>]*>.*?</pasted_content[^>]*>",
    r"<[a-z_-]+>.*?</[a-z_-]+>",
]

# 저자가 산문으로 쓰지 않은 부분. 이 안의 영어는 세지 않는다.
MASKS = [
    r"```.*?```",
    r"~~~.*?~~~",
    r"`[^`\n]+`",
    r"(?m)^ {4,}\S.*$",
    r"(?m)^\t+\S.*$",
    r"(?m)^\s*>.*$",
    r"(?m)^\s*\|.*\|\s*$",
    r"(?m)^\s*\$ .*$",
    r"<[^>\n]+>",
    r"\]\([^)\s]+\)",
    r"(?:https?|ftp|file)://\S+",
    r"www\.\S+",
    r"[\w.+-]+@[\w-]+\.[\w.]+",
    # 경로: 슬래시나 역슬래시를 품은 토큰, 드라이브 문자, 홈 디렉터리
    r"(?<!\S)(?:[A-Za-z]:)?[~.]?[\\/]\S*",
    r"\S+[\\/]\S+",
    # 파일명과 점으로 이은 이름(foo.py, os.path.join)
    r"\b[\w-]+(?:\.[\w-]+)+\b",
]

WORD = re.compile(r"[A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ][A-Za-z0-9가-힣ㄱ-ㅎㅏ-ㅣ'’_-]*")


def _is_identifier(w: str) -> bool:
    """코드 이름이나 약어로 보이는 영어 토큰. 산문 단어로 세지 않는다."""
    if "_" in w or any(c.isdigit() for c in w):
        return True
    if len(w) >= 2 and w.isupper():
        return True
    # camelCase, PascalCase 혼합(useEffect, GitHub)
    if re.search(r"[a-z][A-Z]", w):
        return True
    return False


def word_counts(text: str):
    """(한글 단어 수, 영어 산문 단어 수)를 센다. 한글이 섞인 토큰은 한글 단어다."""
    ko = en = 0
    for w in WORD.findall(text):
        if HANGUL.search(w):
            ko += 1
        elif len(w) >= 2 and not _is_identifier(w):
            en += 1
    return ko, en


def mask(text: str) -> str:
    out = text
    for pat in MASKS:
        out = re.sub(pat, " ", out, flags=re.S)
    return out


def clean_prompt(text: str) -> str:
    out = text
    for pat in PROMPT_NOISE:
        out = re.sub(pat, " ", out, flags=re.S | re.I)
    return mask(out)


def is_korean_prompt(prompt: str) -> bool:
    ko, en = word_counts(clean_prompt(prompt))
    if ko == 0:
        return False
    return ko / (ko + en) >= KO_PROMPT_RATIO


def judge(prompt: str, answer: str) -> dict:
    """영어 답변이면 flagged 가 참이다."""
    result = {"flagged": False, "reason": "", "ko_words": 0, "en_words": 0}
    if not prompt or not answer:
        result["reason"] = "no_input"
        return result
    if not is_korean_prompt(prompt):
        result["reason"] = "prompt_not_korean"
        return result
    if WANTS_ENGLISH.search(clean_prompt(prompt)):
        result["reason"] = "english_requested"
        return result

    ko, en = word_counts(mask(answer))
    result["ko_words"], result["en_words"] = ko, en
    if en < MIN_EN_WORDS:
        result["reason"] = "too_short"
        return result
    if en / (ko + en) < EN_RATIO:
        result["reason"] = "mostly_korean"
        return result
    result["flagged"] = True
    result["reason"] = "english_answer"
    return result


def _text_of(content) -> str:
    """메시지 content 에서 사람이 친 글만 꺼낸다. tool_result 만 있으면 빈 문자열이다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def last_user_prompt(transcript_path: str) -> str:
    """대화 기록 JSONL 에서 마지막 사람 입력을 찾는다.

    도구 결과도 type 이 user 로 들어오므로 글이 없는 항목은 건너뛴다.
    훅이 덧붙인 메타 항목과 압축 요약도 건너뛴다.
    """
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except (OSError, TypeError):
        return ""
    for raw in reversed(lines):
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
            continue
        msg = entry.get("message") or {}
        text = _text_of(msg.get("content"))
        if not text.strip():
            continue
        if not clean_prompt(text).strip():
            continue
        return text
    return ""


def prompt_from_payload(payload: dict) -> str:
    for key in ("prompt", "user_prompt", "last_user_message"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return last_user_prompt(payload.get("transcript_path") or "")


REASON = (
    "사용자는 한국어로 물었는데 직전 답변이 영어로 나갔습니다.\n"
    "같은 내용을 한국어로 다시 쓰세요. 내용은 바꾸지 않습니다.\n"
    "코드, 명령, 경로, URL, 식별자, 고유명사, 오류 메시지 원문은 그대로 둡니다.\n"
    "다시 썼다는 말이나 사과는 붙이지 마세요."
)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        prompt = fh.read()
    with open(sys.argv[2], encoding="utf-8") as fh:
        answer = fh.read()
    print(json.dumps(judge(prompt, answer), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
