# korean-style-guard

한국어 출력에서 AI 티가 나는 서식과 구조를 막고, 지켜졌는지 기계로 검사하는 Claude Code 플러그인이다.
[fluent-korean](https://github.com/snflkd/fluent-korean) output style 을 대체하지 않고 보완한다.

## 왜 만들었나

한국어 LLM 출력의 대표 후보로 늘 거명되는 것들은 정작 나타나지 않았다.
실제 출력 21,046자를 전수로 세어 본 결과다.

| 후보 | 실측 |
|---|---|
| 번역투 12종("~에 대한", "~을 통해", "~에 있어서", "~에 의해" 등) | 0회 |
| 이중피동("되어지다", "보여지다") | 0회 |
| 상투 어휘(핵심, 최적화, 고도화, 시너지, 인사이트) | 0회 |
| 엠대시(—) | **58회** |
| 볼드 쌍 | **90건** |

fluent-korean 이 어휘와 문법 층위를 이미 누르고 있기 때문이다.
남은 것은 문장부호와 마크다운 서식, 그리고 서로 다른 메시지가 같은 헤딩 슬롯과 같은 표를
다시 만들어 내는 골격의 재생산이었다. fluent-korean 조항 10개 어디에도 마크다운, 강조,
서식이라는 말이 없다.

사람이 쓴 대조군 6,317자에서는 엠대시 1회에 볼드 0건이었다.

## 무엇이 들어 있나

| 구성 | 역할 |
|---|---|
| `rules/ko-style-rules.md` | 보칙 본문 8항목. 단일 출처 |
| `hooks/inject-rules.sh` | SessionStart 훅. 보칙을 세션 컨텍스트에 주입 |
| `hooks/check-output.sh` | Stop 훅. 위반 시 exit 2 로 막고 재작성을 요구 |
| `scripts/ko_style_check.py` | 계수기. 단독으로도 쓴다 |
| `skills/ko-style/` | 이미 쓰인 글을 점검하고 고치는 스킬 |
| `commands/ko-check.md` | `/ko-check [파일]` 슬래시 명령 |

## 보칙 8항목

서식 셋, 구조 넷, 보호 단서 하나다.

1. 엠대시와 엔대시를 쓰지 않는다. 국립국어원 규정이 인정하는 줄표 용법은 한 쌍으로 쓰는 두 경우뿐이다.
2. 볼드를 아껴 쓴다. 완결 문장을 감싸지 않고, 줄머리에서 문단을 열지 않고, `**라벨**:` 로 서술어를 대신하지 않는다.
3. 이모지와 느낌표와 인사말과 선택지 메뉴를 쓰지 않는다.
4. 헤딩에 개수를 예고하는 틀을 되풀이하지 않는다.
5. 무엇을 했는지 밝히지 않은 채 완료 선언으로 보고를 열지 않는다.
6. 묻지 않은 후속 제안으로 글을 닫지 않는다.
7. 같은 작업의 두 번째 보고에서 앞서 낸 표와 문단을 다시 만들지 않는다.
8. 기술 문서에서 관용으로 굳은 비유는 그대로 둔다. 뜻만 남기고 읽는 맛을 없애지 않는다.

## 설계 근거

**왜 output style 이 아닌가.** output style 은 설계상 메인 대화에만 적용된다.
서브에이전트 20개 전수와 cron 세션에 리마인더가 0건인 것을 실측으로 확인했다.
3항이 겨냥한 것이 정확히 그 경로다.

**왜 SessionStart 훅으로 주입하는가.** 플러그인은 CLAUDE.md 동등물을 배포할 구조가 없다.
`additionalContext` 가 그 자리를 대신하는 유일한 경로다.
matcher 에 `clear` 와 `compact` 를 넣어 두어 `/clear` 뒤에도 다시 주입된다.

**왜 Stop 훅이 필요한가.** 조항만 적어 두면 지켜지지 않는다.
fluent-korean 구 단위 4조가 엠대시를 금지하는데도 표본에 58회가 나왔다.

## 설치

```bash
/plugin marketplace add <이 저장소>
/plugin install korean-style-guard@korean-style-guard
```

로컬 디렉터리에서 바로 쓸 수도 있다.

```bash
/plugin marketplace add /path/to/korean-style-guard
```

설치 후 새 세션부터 적용된다.

### Stop 훅은 한 줄을 더 걸어야 한다

이 플러그인의 `SessionStart` 훅은 설치만으로 동작한다. 그런데 `Stop` 훅은 플러그인에서
선언해도 등록되지 않는다. 문서에는 플러그인이 모든 훅 이벤트를 지원한다고 적혀 있으나,
실측으로는 다음이 확인됐다.

| 등록 경로 | SessionStart | Stop |
|---|---|---|
| 플러그인 `hooks/hooks.json` | 발동 | **발동하지 않음** |
| `~/.claude/settings.json` | 발동 | 발동 |

같은 스크립트를 두 경로에 각각 걸어 비교했고, matcher 유무와 `shell`·`statusMessage`
필드 제거, 기록 줄을 첫 줄로 옮기기까지 시도했으나 결과는 같았다.

그래서 `~/.claude/settings.json` 에 연결자 한 줄을 건다. 실제 로직은 플러그인 안에 남는다.

```bash
mkdir -p ~/.claude/hooks
cp hooks/settings-bridge.sh ~/.claude/hooks/ko-style-stop.sh
chmod +x ~/.claude/hooks/ko-style-stop.sh
```

그리고 `~/.claude/settings.json` 에 이렇게 넣는다.

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/ko-style-stop.sh", "timeout": 15 } ] }
    ]
  }
}
```

연결자는 설치된 플러그인 캐시에서 가장 높은 버전을 매번 찾으므로, 플러그인을 업데이트해도
따로 손댈 필요가 없다.

Stop 훅 없이 `SessionStart` 주입만으로도 상당 부분 지켜진다. 실측에서 모델이 주입된 보칙을
읽고 스스로 엠대시를 콜론으로 바꿨다. 다만 조항만으로는 새는 경우가 있다는 것이
이 플러그인을 만든 이유이므로, 연결자를 거는 편을 권한다.

## 단독 사용

```bash
python3 scripts/ko_style_check.py 파일.md
cat 파일.md | python3 scripts/ko_style_check.py --json
```

위반이 없으면 0, 있으면 1 로 끝난다.

## 전제

Python 3.8 이상. 표준 라이브러리만 쓴다.

## 라이선스

MIT
