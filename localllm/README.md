# 로컬 LLM에서 쓰기

Qwen 같은 로컬 모델에 한국어 보칙을 걸어 줍니다. Claude Code와 Codex는 하네스가 훅을 주지만, Ollama·MLX·LM Studio 같은 모델 서버에는 끼어들 훅이 없습니다. 그래서 끼어드는 지점을 이 폴더가 대신합니다.

흐름은 Claude Code의 훅과 같습니다.

1. 보칙을 시스템 프롬프트에 넣습니다.
2. 모델이 답하면 검사기를 돌립니다.
3. 걸리면 위반 목록을 붙여 다시 쓰게 합니다. 정해진 횟수까지만 되풀이합니다.

검사와 다시 쓰기 판단은 `scripts/`의 코드를 그대로 가져다 쓰므로, 판정이 Claude·Codex와 같습니다. 파이썬 3.8 이상만 있으면 되고 외부 라이브러리는 없습니다.

## 프록시로 쓰기 (권장)

모델 서버 앞에 프록시를 두면, 클라이언트는 프록시만 바라봅니다. 클라이언트를 고치지 않아도 됩니다.

```bash
# Ollama 앞에 두기(기본값)
python localllm/proxy.py

# LM Studio 앞에 두기
GUARD_UPSTREAM=http://localhost:1234/v1 python localllm/proxy.py

# MLX(mlx_lm.server --port 8080) 앞에 두기
GUARD_UPSTREAM=http://localhost:8080/v1 python localllm/proxy.py
```

그다음 클라이언트의 `base_url`을 `http://localhost:8089/v1`로 바꾸면 됩니다. OpenAI 호환 API라 `curl`도 됩니다.

```bash
curl http://localhost:8089/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "qwen2.5",
  "messages": [{"role": "user", "content": "캐시가 왜 느린지 알려줘"}]
}'
```

응답 헤더 `X-Guard-Rounds`에 다시 쓰기를 몇 번 했는지 나옵니다.

### 환경 변수

| 변수 | 하는 일 | 기본값 |
|---|---|---|
| `GUARD_UPSTREAM` | 업스트림 OpenAI 호환 주소 | `http://localhost:11434/v1` |
| `GUARD_UPSTREAM_KEY` | 업스트림이 키를 요구할 때 | 없음 |
| `GUARD_HOST`, `GUARD_PORT` | 프록시가 들을 주소 | `127.0.0.1`, `8089` |
| `GUARD_MAX_ROUNDS` | 다시 쓰기 최대 횟수 | `2` |
| `GUARD_INJECT` | `rules`, `rules+examples`, `none` | `rules` |
| `GUARD_SKIP_LANG` | `1`이면 영어 답변 되돌리기를 끔 | 꺼짐 |
| `GUARD_LITE` | `1`이면 교정·교열을 빼고 보칙만 검사 | 꺼짐 |

## 코드에서 쓰기

메시지 목록을 받아 답변 문자열을 돌려주는 함수(`complete`) 하나만 맞추면 됩니다.

```python
import json, urllib.request
from localllm import guard

def complete(messages):
    body = {"model": "qwen2.5", "messages": messages, "stream": False}
    req = urllib.request.Request(
        "http://localhost:11434/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["choices"][0]["message"]["content"]

answer, rounds = guard(
    [{"role": "user", "content": "전세와 월세 중 뭐가 나아?"}],
    complete, max_rounds=2)
print(answer, f"(다시 쓰기 {rounds}회)")
```

검사만 하고 싶으면 `evaluate(prompt, answer)`가 다시 쓰기 지시를 돌려주고(통과하면 `None`), `check(text)`가 보칙 위반을 셉니다.

## 작은 모델에서 알아 둘 점

- 작은 모델은 Claude만큼 38항목을 다 지키지 못해 첫 답이 더 자주 걸립니다. 그만큼 다시 쓰기가 자주 돕니다. `GUARD_MAX_ROUNDS`로 횟수를 막아 시간과 품질을 지킵니다.
- 보칙 본문은 약 1만 자입니다. 문맥이 좁은 모델에는 부담이라, 기본값은 예문을 뺀 본문만 넣습니다(`GUARD_INJECT=rules`). 더 잘 지키게 하려면 `rules+examples`로 예문까지 넣되 문맥을 더 씁니다.
- 교정 항목(외래어 오표기, 사이시옷, 띄어쓰기, 문장 부호)은 한국어가 약한 모델에서 자주 걸려 다시 쓰기를 늘립니다. 가볍게 쓰고 싶으면 `GUARD_LITE=1`로 보칙(문체)만 거세요. 맞춤법 교정 대신 AI 티만 지웁니다.

## 다른 틀의 훅에 꽂기

Open WebUI의 필터나 LiteLLM의 콜백처럼 훅이 있는 틀을 쓰면, 그 훅에서 `localllm`의 `evaluate`와 `guard`를 부르면 됩니다. 프록시와 같은 코어를 쓰므로 판정이 같습니다.
