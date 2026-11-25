#!/usr/bin/env python3
"""언어 검사기(ko_lang_check)의 회귀 시험을 돌린다.

한국어 질문에 영어로 답한 경우를 잡는지, 그리고 코드와 경로와 기술 용어가 많은
한국어 답변이나 번역 요청을 잘못 잡지 않는지 본다.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

from ko_lang_check import judge, last_user_prompt  # noqa: E402

KO_Q = "이 함수가 왜 None을 돌려주는지 알려줘."
EN_A = ("The function returns None because the early return on line 12 runs before "
        "the value is assigned. Move the assignment above the guard and it will work.")
KO_A = "12번째 줄의 이른 반환이 값을 넣기 전에 실행되어 None이 나옵니다. 대입을 위로 옮기면 됩니다."

# (이름, 질문, 답변, 잡아야 하는가)
CASES = [
    ("english_answer", KO_Q, EN_A, True),
    ("korean_answer_ok", KO_Q, KO_A, False),
    ("english_prompt_ok", "Why does this return None?", EN_A, False),
    ("translation_request_ok", "다음 문단을 영어로 번역해 줘: 설정을 바꿨습니다.", EN_A, False),
    ("english_requested_ok", "릴리스 노트를 영어로 써 줘.", EN_A, False),
    ("short_english_ok", KO_Q, "Fixed. See `parse.py`.", False),
    ("code_heavy_korean_ok", KO_Q,
     "원인은 아래 코드입니다.\n\n```python\ndef parse(value):\n    if not value:\n"
     "        return None  # early return happens before assignment here\n"
     "    result = value.strip()\n    return result\n```\n\n"
     "`if not value` 분기가 빈 문자열에서도 참이 되어 None을 돌려줍니다.", False),
    ("paths_urls_korean_ok", KO_Q,
     "설정은 C:/Program Files/App/config.json 과 https://example.com/docs/getting-started "
     "에 있습니다. README.md 의 Installation 절도 보세요.", False),
    ("tech_terms_korean_ok", KO_Q,
     "React의 useEffect hook은 dependency array가 바뀔 때만 다시 실행됩니다. "
     "Strict Mode에서는 development build에서 두 번 실행됩니다.", False),
    ("quoted_error_ok", KO_Q,
     "오류는 다음과 같습니다.\n\n> TypeError: Cannot read properties of undefined "
     "(reading 'map') at render in the component tree when the list is empty\n\n"
     "목록이 비어 있을 때 map을 부르기 전에 확인하면 됩니다.", False),
    ("table_english_ok", KO_Q,
     "| Option | Description |\n|---|---|\n| --force | Overwrite the existing file "
     "without asking for confirmation first |\n| --dry-run | Print what would happen "
     "without changing anything on disk |\n\n두 옵션 가운데 --dry-run 을 먼저 쓰세요.", False),
    ("mixed_mostly_english", KO_Q,
     "요약: The root cause is that the cache key ignores the locale, so every user "
     "after the first one receives the same rendered page regardless of their language "
     "settings. Add the locale to the key.", True),
    ("prompt_with_code_korean", "```\nTraceback (most recent call last):\n  File \"a.py\"\n"
     "ValueError: invalid literal for int()\n```\n이거 왜 나?", EN_A, True),
    ("prompt_mostly_english_ok",
     "Please refactor the payment service to use async/await everywhere 고마워", EN_A, False),
    ("hook_noise_prompt",
     "<system-reminder>The following is English boilerplate injected by tooling that the "
     "user never typed and should be ignored entirely.</system-reminder>배포 스크립트 고쳐줘",
     EN_A, True),
    # 3회차 표본에서 찾은 빈틈
    ("pasted_log_prompt",
     "Traceback (most recent call last):\n  File \"/app/db.py\", line 42, in connect\n"
     "    engine = create_engine(url, pool_pre_ping=True)\n"
     "sqlalchemy.exc.OperationalError: could not connect to server: Connection refused\n"
     "\tIs the server running on host \"localhost\" and accepting TCP/IP connections on port 5432?\n"
     "이거 왜 이래?", EN_A, True),
    ("translate_to_korean_english_answer", "이 문단을 한국어로 번역해 줘.", EN_A, True),
    ("translate_to_english_with_korean_note_ok",
     "이 문장을 영어로 번역해 줘. 설명은 한국어로 해 줘.", EN_A, False),
    ("polish_english_email_ok", "이 영어 이메일 다듬어줘\n\nHi team, I want to share update.", EN_A, False),
]


def run_cases():
    failed = 0
    for name, prompt, answer, want in CASES:
        got = judge(prompt, answer)
        if got["flagged"] != want:
            failed += 1
            print(f"실패 {name}: 기대 {want}, 결과 {got}")
    return failed, len(CASES)


def run_transcript():
    failed = 0
    p = last_user_prompt(os.path.join(HERE, "lang", "transcript.jsonl"))
    if "None을 돌려주는지" not in p:
        failed += 1
        print(f"실패 transcript_last_prompt: {p!r}")
    p = last_user_prompt(os.path.join(HERE, "lang", "transcript_en.jsonl"))
    if not p.startswith("Why does"):
        failed += 1
        print(f"실패 transcript_block_content: {p!r}")
    if last_user_prompt(os.path.join(HERE, "lang", "missing.jsonl")) != "":
        failed += 1
        print("실패 transcript_missing")
    return failed, 3


def run_hook():
    """stop_hook.py 를 실제 훅처럼 불러 종료 코드와 출력 계약을 본다."""
    hook = os.path.join(SCRIPTS, "stop_hook.py")
    tr = os.path.join(HERE, "lang", "transcript.jsonl")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("KO_STYLE_SKIP_LANG", None)
    cases = [
        ("hook_blocks_english", {"transcript_path": tr, "last_assistant_message": EN_A}, 2),
        ("hook_passes_korean", {"transcript_path": tr, "last_assistant_message": KO_A}, 0),
        ("hook_respects_active", {"transcript_path": tr, "last_assistant_message": EN_A,
                                  "stop_hook_active": True}, 0),
        ("hook_codex_json", {"transcript_path": tr, "last_assistant_message": EN_A,
                             "turn_id": "x"}, 0),
    ]
    failed = 0
    for name, payload, code in cases:
        r = subprocess.run([sys.executable, hook], input=json.dumps(payload).encode("utf-8"),
                           capture_output=True, env=env)
        out, err = r.stdout.decode("utf-8"), r.stderr.decode("utf-8")
        ok = r.returncode == code
        if name == "hook_codex_json":
            ok = ok and json.loads(out or "{}").get("decision") == "block"
        if name == "hook_blocks_english":
            ok = ok and "한국어로 다시" in err
        if not ok:
            failed += 1
            print(f"실패 {name}: 종료 {r.returncode} / {err[:160]}")
    return failed, len(cases)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    total_failed = total = 0
    for fn in (run_cases, run_transcript, run_hook):
        f, n = fn()
        total_failed += f
        total += n
    print(f"{total - total_failed}/{total} 통과")
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
