#!/usr/bin/env bash
# 훅 래퍼가 source 하는 파이썬 찾기.
#
# Windows 에서는 python3 이 없거나, 있어도 스토어 설치를 권하는 빈 껍데기일 때가 많다.
# 그러면 훅이 아무 말 없이 실패하고 검사가 통째로 빠진다. 그래서 이름만 보지 않고
# 실제로 한 줄을 돌려 보고 되는 것을 고른다. 찾으면 PY 배열에 담고, 못 찾으면 비워 둔다.
# 한글 보고가 cp949 로 깨지지 않게 입출력을 UTF-8 로 고정한다.
export PYTHONIOENCODING=utf-8
PY=()
for cand in "python3" "python" "py -3"; do
  # shellcheck disable=SC2086
  if $cand -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
    read -r -a PY <<< "$cand"
    break
  fi
done
