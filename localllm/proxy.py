"""한국어 보칙을 거는 OpenAI 호환 프록시.

Ollama·MLX(mlx_lm.server)·LM Studio 같은 로컬 모델 서버 앞에 두면, 클라이언트는 이 프록시만
바라본다. 프록시가 보칙을 시스템 프롬프트에 넣고, 답을 검사하고, 걸리면 다시 쓰게 한 뒤
OpenAI 형식으로 돌려준다. 표준 라이브러리만 쓴다.

  # Ollama 앞에 두기(기본값)
  python localllm/proxy.py

  # LM Studio 앞에 두기
  GUARD_UPSTREAM=http://localhost:1234/v1 python localllm/proxy.py

  # MLX(mlx_lm.server --port 8080) 앞에 두기
  GUARD_UPSTREAM=http://localhost:8080/v1 python localllm/proxy.py

그다음 클라이언트의 base_url 을 http://localhost:8089/v1 로 바꾸면 된다.

환경 변수
  GUARD_UPSTREAM       업스트림 OpenAI 호환 주소. 기본 http://localhost:11434/v1
  GUARD_UPSTREAM_KEY   업스트림이 키를 요구하면 넣는다(로컬은 대개 불필요).
  GUARD_HOST, GUARD_PORT  프록시가 들을 주소. 기본 127.0.0.1:8089
  GUARD_MAX_ROUNDS     다시 쓰기 최대 횟수. 기본 2
  GUARD_INJECT         rules | rules+examples | none. 기본 rules
  GUARD_SKIP_LANG      1 이면 영어 답변 되돌리기를 끈다.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard as kg  # noqa: E402

UPSTREAM = os.environ.get("GUARD_UPSTREAM", "http://localhost:11434/v1").rstrip("/")
UPSTREAM_KEY = os.environ.get("GUARD_UPSTREAM_KEY", "")
HOST = os.environ.get("GUARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("GUARD_PORT", "8089"))
MAX_ROUNDS = int(os.environ.get("GUARD_MAX_ROUNDS", "2"))
INJECT = os.environ.get("GUARD_INJECT", "rules")
SKIP_LANG = os.environ.get("GUARD_SKIP_LANG") == "1"


def _upstream(path: str, payload=None, method="POST"):
    url = UPSTREAM + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if UPSTREAM_KEY:
        req.add_header("Authorization", "Bearer " + UPSTREAM_KEY)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def _make_complete(body: dict):
    """업스트림을 부르는 complete(messages) 를 만든다. 모델과 표본 매개변수는 그대로 넘긴다."""
    def complete(messages):
        payload = {k: v for k, v in body.items() if k not in ("messages", "stream")}
        payload["messages"] = messages
        payload["stream"] = False
        resp = _upstream("/chat/completions", payload)
        try:
            return resp["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return ""
    return complete


def _completion_object(body: dict, text: str) -> dict:
    return {
        "id": "guarded",
        "object": "chat.completion",
        "model": body.get("model", ""),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # 접속 로그를 끈다
        pass

    def _send_json(self, obj: dict, code=200, headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_stream(self, body: dict, text: str, rounds: int):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("X-Guard-Rounds", str(rounds))
        self.send_header("Connection", "close")
        self.end_headers()
        model = body.get("model", "")
        first = {"id": "guarded", "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {"role": "assistant", "content": text},
                              "finish_reason": None}]}
        last = {"id": "guarded", "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        for chunk in (first, last):
            self.wfile.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            try:
                self._send_json(_upstream("/models", method="GET"))
            except urllib.error.URLError as e:
                self._send_json({"error": str(e)}, 502)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            messages = body.get("messages", [])
        except (ValueError, TypeError):
            self._send_json({"error": "bad request"}, 400)
            return
        try:
            text, rounds = kg.guard(messages, _make_complete(body),
                                    max_rounds=MAX_ROUNDS, inject=INJECT, skip_lang=SKIP_LANG)
        except urllib.error.URLError as e:
            self._send_json({"error": "upstream: " + str(e)}, 502)
            return
        if body.get("stream"):
            self._send_stream(body, text, rounds)
        else:
            self._send_json(_completion_object(body, text), headers={"X-Guard-Rounds": str(rounds)})


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"한국어 보칙 프록시: http://{HOST}:{PORT}/v1  ->  {UPSTREAM}")
    print(f"  다시 쓰기 최대 {MAX_ROUNDS}회, 보칙 주입 {INJECT}"
          + (", 언어 판정 끔" if SKIP_LANG else ""))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
