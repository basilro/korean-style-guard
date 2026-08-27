#!/usr/bin/env bash
# PostToolUse 훅: 방금 쓴 산문 파일을 검사한다.
# Stop 훅이 보지 못하는 파일 내용을 이쪽이 맡는다.
set -uo pipefail

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOOK="$ROOT/scripts/post_write_hook.py"

[ -r "$HOOK" ] || exit 0
exec python3 "$HOOK"
