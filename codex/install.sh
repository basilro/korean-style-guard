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
python3 - "$ROOT" "$HOOKS" <<'PY'
import json, os, sys

root, hooks_path = sys.argv[1], sys.argv[2]
inject = os.path.join(root, "hooks", "inject-rules.sh")
check = os.path.join(root, "scripts", "stop_hook.py")

cfg = {}
if os.path.exists(hooks_path):
    try:
        with open(hooks_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        print("  기존 hooks.json 을 읽지 못해 덮어쓰지 않았습니다. 수동으로 합쳐 주세요.")
        sys.exit(1)

hooks = cfg.setdefault("hooks", {})

def put(event, entry):
    lst = hooks.setdefault(event, [])
    # 같은 명령이 이미 있으면 갈아 끼운다
    cmd = entry["hooks"][0]["command"]
    for group in lst:
        for h in group.get("hooks", []):
            if "korean-style-guard" in h.get("command", "") or h.get("command") == cmd:
                h.update(entry["hooks"][0])
                return "updated"
    lst.append(entry)
    return "added"

r1 = put("SessionStart", {
    "matcher": "startup|clear|compact",
    "hooks": [{"type": "command", "command": f'bash "{inject}"', "timeoutSec": 10}],
})
r2 = put("Stop", {
    "hooks": [{"type": "command", "command": f'python3 "{check}"', "timeoutSec": 15}],
})

with open(hooks_path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
label = {"added": "추가", "updated": "갱신"}
print(f"  훅 {label[r1]}: SessionStart / 훅 {label[r2]}: Stop")
PY

echo "  훅 설정: ${HOOKS/#$HOME/\~}"
echo
echo "남은 단계가 하나 있습니다."
echo "  Codex 를 실행해 /hooks 에서 두 훅을 신뢰로 표시하세요. 승인 전에는 실행되지 않습니다."
