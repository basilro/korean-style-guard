#!/usr/bin/env bash
# Codex CLI 에 한국어 보칙을 설치한다.
#
# Codex 플러그인은 훅을 담지 못한다(codex features list 에서 plugin_hooks 가 removed).
# 그래서 스킬은 스킬 경로에 두고 훅은 ~/.codex/hooks.json 에 따로 넣는다.
# 설치 뒤 Codex 안에서 /hooks 로 신뢰를 승인해야 훅이 실제로 돈다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SKILL_DST="$CODEX_HOME/skills/ko-style"
HOOKS="$CODEX_HOME/hooks.json"

[ -d "$CODEX_HOME" ] || { echo "Codex 홈을 찾을 수 없습니다: $CODEX_HOME"; exit 1; }

echo "대상: $CODEX_HOME"

# 1) 스킬
mkdir -p "$(dirname "$SKILL_DST")"
rm -rf "$SKILL_DST"
cp -r "$ROOT/skills/ko-style" "$SKILL_DST"
echo "  스킬 설치: ${SKILL_DST/#$HOME/\~}"

# 2) 훅
# python3 이 없거나 스토어 껍데기인 Windows 에서도 돌도록 실제로 도는 파이썬을 찾는다.
. "$ROOT/hooks/find-python.sh"
[ ${#PY[@]} -gt 0 ] || { echo "파이썬 3.8 이상을 찾을 수 없습니다."; exit 1; }
"${PY[@]}" - "$ROOT" "$HOOKS" "${PY[*]}" <<'PY'
import json, os, sys

root, hooks_path, pycmd = sys.argv[1], sys.argv[2], sys.argv[3]
inject = os.path.join(root, "hooks", "inject-rules.sh")
check = os.path.join(root, "scripts", "stop_hook.py")
postwrite = os.path.join(root, "scripts", "post_write_hook.py")

cfg = {}
if os.path.exists(hooks_path):
    try:
        with open(hooks_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        print("  기존 hooks.json 을 읽지 못해 덮어쓰지 않았습니다. 수동으로 합쳐 주세요.")
        sys.exit(1)

hooks = cfg.setdefault("hooks", {})

def put(event, entry, key):
    """같은 스크립트와 인자를 부르는 훅이 이미 있으면 갈아 끼운다.

    key 는 명령에서 스크립트 이름과 인자를 가리는 꼬리다. 예전 판이 python3 으로 등록한 것도
    꼬리가 같으면 갱신한다. 본문과 부록 주입은 꼬리가 달라 따로 들어간다.
    """
    lst = hooks.setdefault(event, [])
    for group in lst:
        for h in group.get("hooks", []):
            if h.get("command", "").rstrip().endswith(key):
                h.update(entry["hooks"][0])
                return "updated"
    lst.append(entry)
    return "added"

r1 = put("SessionStart", {
    "matcher": "startup|clear|compact",
    "hooks": [{"type": "command", "command": f'bash "{inject}"', "timeoutSec": 10}],
}, 'inject-rules.sh"')
put("SessionStart", {
    "matcher": "startup|clear|compact",
    "hooks": [{"type": "command", "command": f'bash "{inject}" ko-style-examples.md', "timeoutSec": 10}],
}, 'inject-rules.sh" ko-style-examples.md')
r2 = put("Stop", {
    "hooks": [{"type": "command", "command": f'{pycmd} "{check}"', "timeoutSec": 15}],
}, 'stop_hook.py"')
r3 = put("PostToolUse", {
    "matcher": "Write|Edit",
    "hooks": [{"type": "command", "command": f'{pycmd} "{postwrite}"', "timeoutSec": 15}],
}, 'post_write_hook.py"')

with open(hooks_path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
label = {"added": "추가", "updated": "갱신"}
print(f"  훅 {label[r1]}: SessionStart / {label[r2]}: Stop / {label[r3]}: PostToolUse")
PY

echo "  훅 설정: ${HOOKS/#$HOME/\~}"
echo
echo "남은 단계가 하나 있습니다."
echo "  Codex 를 실행해 /hooks 에서 두 훅을 신뢰로 표시하세요. 승인 전에는 실행되지 않습니다."
