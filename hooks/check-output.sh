#!/usr/bin/env bash
# Stop hook: 직전 답변이 한국어 보칙을 지켰는지 센다.
#
# 위반이 있으면 exit 2 로 턴을 막고, stderr 의 내용이 Claude 에게 다음 지시로 전달된다.
# 조항을 적어 두기만 하면 지켜지지 않는다. 표본 21,046자에서 이미 금지된 엠대시가
# 58회 나왔고, 그것이 이 검사를 붙인 이유다.
set -uo pipefail

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOOK="$ROOT/scripts/stop_hook.py"

[ -r "$HOOK" ] || exit 0
exec python3 "$HOOK"
