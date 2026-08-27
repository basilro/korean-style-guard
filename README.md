# korean-style-guard

한국어 출력에서 AI 티가 나는 서식과 구조를 막고, 지켜졌는지 기계로 검사하는 에이전트 플러그인이다.
어휘와 문법이 아니라 문장부호와 마크다운 서식과 문서 구조를 다룬다. Claude Code 와
Codex 에서 쓴다.

## 무엇이 들어 있나

| 구성 | 역할 |
|---|---|
| `rules/ko-style-rules.md` | 보칙 본문 9항목. 단일 출처 |
| `hooks/inject-rules.sh` | SessionStart 훅. 보칙을 세션 컨텍스트에 주입 |
| `hooks/check-output.sh` | Stop 훅. 대화 답변을 검사해 위반 시 재작성을 요구 |
| `hooks/check-written-file.sh` | PostToolUse 훅. 방금 쓴 산문 파일을 검사 |
| `scripts/ko_style_check.py` | 계수기. 단독으로도 쓴다 |
| `skills/ko-style/` | 이미 쓰인 글을 점검하고 고치는 스킬 |
| `commands/ko-check.md` | `/ko-check [파일]` 슬래시 명령 |

## 보칙 9항목

서식 셋, 문장 하나, 구조 넷, 과잉 교정 방지 하나다.

1. 엠대시와 엔대시를 쓰지 않는다. 국립국어원 규정이 인정하는 줄표 용법은 한 쌍으로 쓰는 두 경우뿐이다.
2. 볼드를 아껴 쓴다. 완결 문장을 감싸지 않고, 줄머리에서 문단을 열지 않고, `**라벨**:` 로 서술어를 대신하지 않는다.
3. 이모지와 느낌표와 인사말과 선택지 메뉴를 쓰지 않는다.
4. 본문 산문은 서술어와 종결어미를 갖춘 완성된 문장으로 끝맺는다. 헤딩과 목록과 표의 칸은 대상이 아니다.
5. 헤딩에 개수를 예고하는 틀을 되풀이하지 않는다.
6. 무엇을 했는지 밝히지 않은 채 완료 선언으로 보고를 열지 않는다.
7. 묻지 않은 후속 제안으로 글을 닫지 않는다.
8. 같은 작업의 두 번째 보고에서 앞서 낸 표와 문단을 다시 만들지 않는다.
9. 규칙을 지키느라 글을 평평하게 만들지 않는다. 기술 문서에서 관용으로 굳은 비유는 그대로 둔다.

1번부터 8번까지가 모두 금지 규칙이므로 9번을 함께 둔다. 지울 대상은 과장과 광고체이지
구체성이 아니다.

## 설계 근거

### output style 이 아닌 이유

output style 은 설계상 메인 대화에만 적용된다. 서브에이전트와 헤드리스 실행과 cron 에는
걸리지 않는다. 3항이 겨냥한 것이 정확히 그 경로다.

### SessionStart 훅으로 주입하는 이유

플러그인은 CLAUDE.md 동등물을 배포할 구조가 없다.
`additionalContext` 가 그 자리를 대신하는 유일한 경로다.
matcher 에 `clear` 와 `compact` 를 넣어 두어 `/clear` 뒤에도 다시 주입된다.

### Stop 훅이 필요한 이유

규칙만 적어 두면 지켜지지 않는다. 엠대시를 금지하는 지침이 이미 있어도 계속 나온다.

### 검사 범위

Stop 훅은 대화 답변만 본다. 도구로 쓴 파일은 그 시야 밖이므로 PostToolUse 훅이 맡는다.
`Write` 와 `Edit` 뒤에 방금 쓴 파일을 검사한다.

파일 쪽은 대상을 좁게 잡는다. 코드에 서식 규칙을 들이대면 오탐이 쏟아지기 때문이다.

- 확장자가 `.md` `.markdown` `.mdx` `.txt` `.rst` 인 것만 본다
- 한글 비율이 15% 를 넘고 100자 이상인 파일만 본다
- `.git` `node_modules` `vendor` `dist` `build` 같은 트리는 건너뛴다

파일 검사를 끄려면 `KO_STYLE_SKIP_FILES=1` 을 환경 변수로 둔다.

## Claude Code 에서 쓰기

세션 안에서 슬래시 명령으로 설치한다.

```
/plugin marketplace add basilro/korean-style-guard
/plugin install korean-style-guard@korean-style-guard
```

터미널에서 CLI 로 해도 된다.

```bash
claude plugin marketplace add basilro/korean-style-guard
claude plugin install korean-style-guard@korean-style-guard
```

갱신할 때는 마켓플레이스를 먼저 새로 받아야 새 버전이 보인다.

```bash
claude plugin marketplace update korean-style-guard
claude plugin update korean-style-guard
```

설치 후 새 세션부터 적용된다.

### 원격 소스로 설치한다

로컬 디렉터리를 마켓플레이스 소스로 등록하면 `Stop` 훅이 등록되지 않는다. 원격에
올린 뒤 그쪽을 소스로 설치한다.

로컬 소스로 개발하는 동안에는 동봉된 `hooks/settings-bridge.sh` 를 쓴다.
`~/.claude/settings.json` 의 `hooks.Stop` 에 걸면 검사가 돈다. 원격 설치라면 필요 없다.

## Codex CLI 에서 쓰기

```bash
codex/install.sh
```

스킬을 `$CODEX_HOME/skills/ko-style/` 에 복사하고 `$CODEX_HOME/hooks.json` 에
`SessionStart` 와 `Stop` 훅을 넣는다. 여러 번 돌려도 중복되지 않는다.
`CODEX_HOME` 을 지정하면 그쪽에 설치한다.

설치 뒤에 한 단계가 남는다. Codex 를 실행해 `/hooks` 에서 두 훅을 신뢰로 표시해야 한다.
승인 전에는 실행되지 않는다.

훅을 직접 넣고 싶으면 `codex/hooks.example.json` 을 참고해 `$CODEX_HOME/hooks.json` 이나
`<repo>/.codex/hooks.json` 에 적는다. 경로는 절대 경로로 쓴다.

`skills/ko-style/agents/openai.yaml` 은 Codex 표면 메타데이터다. 표시 이름과 시작
프롬프트를 담는다.

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
