#!/usr/bin/env bash
# SessionStart hook: 한국어 보칙을 세션 컨텍스트에 주입한다.
#
# 플러그인은 CLAUDE.md 를 배포할 구조가 없고, output style 은 메인 대화에만 적용된다.
# SessionStart 의 additionalContext 가 그 둘을 대신하는 유일한 경로다.
# matcher 에 clear 와 compact 를 넣어 두었으므로 /clear 뒤에도 다시 주입된다.
set -uo pipefail

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RULES="$ROOT/rules/ko-style-rules.md"

[ -r "$RULES" ] || exit 0

python3 - "$RULES" <<'PY'
import json, sys
body = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": body,
    }
}, ensure_ascii=False))
PY
