#!/usr/bin/env python3
"""로컬 LLM 가드(localllm/guard.py)의 다시 쓰기 반복을 네트워크 없이 시험한다.

complete 를 대본으로 대신해 모델을 흉내 낸다. 실제 모델이나 서버는 부르지 않는다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "localllm"))
import guard as kg  # noqa: E402


def scripted(answers):
    """부를 때마다 대본의 다음 답을 내는 complete. 마지막 답은 계속 되풀이한다."""
    box = {"i": 0, "seen": []}

    def complete(messages):
        box["seen"].append(messages)
        i = min(box["i"], len(answers) - 1)
        box["i"] += 1
        return answers[i]

    return complete, box


def run_cases():
    cases = []

    # 1. 첫 답이 보칙을 지키면 다시 쓰지 않는다.
    c, box = scripted(["캐시 설정을 조정하면 응답이 빨라집니다."])
    text, rounds = kg.guard([{"role": "user", "content": "캐시 왜 느려?"}], c, max_rounds=2)
    cases.append(("clean_no_rewrite", rounds == 0 and "빨라집니다" in text and len(box["seen"]) == 1))

    # 2. 엠대시로 걸린 답은 다시 쓰게 하고, 고친 답이 통과하면 멈춘다.
    bad = "캐시 설정을 조정합니다 — 응답이 빨라집니다."
    good = "캐시 설정을 조정하면 응답이 빨라집니다."
    c, box = scripted([bad, good])
    text, rounds = kg.guard([{"role": "user", "content": "캐시 왜 느려?"}], c, max_rounds=2)
    # 다시 쓰기 지시에 보칙 위반 보고가 들어갔는지 본다.
    retry_prompt = box["seen"][1][-1]["content"] if len(box["seen"]) > 1 else ""
    cases.append(("rewrite_until_clean",
                  rounds == 1 and text == good and "보칙 위반" in retry_prompt))

    # 3. 한국어 질문에 영어로 답하면 한국어로 다시 쓰게 한다.
    en = ("The cache is cold so the first request recomputes everything, "
          "and that makes the whole page slow for every new visitor today.")
    c, box = scripted([en, good])
    text, rounds = kg.guard([{"role": "user", "content": "캐시 왜 느려?"}], c, max_rounds=2)
    lang_prompt = box["seen"][1][-1]["content"] if len(box["seen"]) > 1 else ""
    cases.append(("english_answer_redone",
                  rounds == 1 and text == good and "한국어로 다시" in lang_prompt))

    # 4. 끝까지 못 고치면 정해진 횟수만큼만 돌고 마지막 답을 그대로 돌려준다(무한 루프 없음).
    c, box = scripted([bad])
    text, rounds = kg.guard([{"role": "user", "content": "캐시 왜 느려?"}], c, max_rounds=2)
    cases.append(("max_rounds_cap", rounds == 2 and text == bad and len(box["seen"]) == 3))

    # 5. 보칙을 시스템 메시지로 넣는다.
    msgs = kg.inject_rules([{"role": "user", "content": "안녕"}], "rules")
    cases.append(("inject_adds_system",
                  msgs[0]["role"] == "system" and "보칙" in msgs[0]["content"] and len(msgs) == 2))

    # 6. none 으로 주입하면 메시지를 그대로 둔다.
    msgs = kg.inject_rules([{"role": "user", "content": "안녕"}], "none")
    cases.append(("inject_none_passthrough", len(msgs) == 1 and msgs[0]["role"] == "user"))

    # 7. lite 는 교정 항목을 빼고 보칙만 센다.
    jeong = "홈 디렉토리에서 설정 파일을 엽니다."          # 교정: 디렉토리→디렉터리
    bochik = "설정을 조정합니다 — 응답이 빨라집니다."       # 보칙: 엠대시
    cases.append(("correction_on_full", not kg.check(jeong)["passed"]))
    cases.append(("correction_off_lite", kg.check(jeong, lite=True)["passed"]))
    cases.append(("bochik_hits_both",
                  not kg.check(bochik)["passed"] and not kg.check(bochik, lite=True)["passed"]))
    # lite 가드는 교정만 걸린 답을 다시 쓰게 하지 않는다.
    c, box = scripted([jeong])
    text, rounds = kg.guard([{"role": "user", "content": "설정 파일 어디 있어?"}], c,
                            max_rounds=2, lite=True)
    cases.append(("guard_lite_no_rewrite", rounds == 0 and text == jeong))

    failed = 0
    for name, ok in cases:
        if not ok:
            failed += 1
            print(f"실패 {name}")
    return failed, len(cases)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    f, n = run_cases()
    print(f"{n - f}/{n} 통과")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
