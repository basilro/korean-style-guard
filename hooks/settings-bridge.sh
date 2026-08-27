#!/usr/bin/env bash
# korean-style-guard 플러그인의 Stop 검사를 부르는 연결자.
#
# 플러그인이 선언한 Stop hook 은 등록되지 않는 것으로 확인됐다(SessionStart 는 된다).
# 그래서 settings.json 에 이 한 줄만 걸고, 실제 로직은 플러그인 안에 둔다.
# 설치 경로를 매번 찾으므로 플러그인 버전이 올라가도 따라간다.
set -uo pipefail

ROOT=$(find "$HOME/.claude/plugins/cache/korean-style-guard" \
        -maxdepth 2 -mindepth 2 -type d 2>/dev/null | sort -V | tail -1)

# 캐시가 없으면 개발용 원본을 쓴다.
[ -z "$ROOT" ] && [ -d "$HOME/work/korean-style-guard" ] && ROOT="$HOME/work/korean-style-guard"
[ -z "$ROOT" ] && exit 0

HOOK="$ROOT/scripts/stop_hook.py"
[ -r "$HOOK" ] || exit 0
exec python3 "$HOOK"
