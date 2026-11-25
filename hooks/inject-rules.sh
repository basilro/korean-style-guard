#!/usr/bin/env bash
# SessionStart hook: 한국어 보칙을 세션 컨텍스트에 주입한다.
#
# 플러그인은 CLAUDE.md 를 배포할 구조가 없고, output style 은 메인 대화에만 적용된다.
# SessionStart 의 additionalContext 가 그 둘을 대신하는 유일한 경로다.
# matcher 에 clear 와 compact 를 넣어 두었으므로 /clear 뒤에도 다시 주입된다.
#
# 인자로 rules/ 아래 파일 이름을 받는다. 없으면 보칙 본문을 주입한다.
# Claude Code 는 훅 출력 하나를 10,000자로 자르므로 본문과 부록을 두 훅으로 나눠 주입한다.
# 각 출력은 따로 재고, 여러 훅이 낸 내용은 모두 전달된다.
set -uo pipefail

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
FILE="${1:-ko-style-rules.md}"
case "$FILE" in
  */*|*..*) exit 0 ;;
esac
RULES="$ROOT/rules/$FILE"

[ -r "$RULES" ] || exit 0

. "$ROOT/hooks/find-python.sh" 2>/dev/null || PY=(python3)
[ ${#PY[@]} -gt 0 ] || exit 0
"${PY[@]}" - "$RULES" <<'PY'
import json, sys
body = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": body,
    }
}, ensure_ascii=False))
PY
