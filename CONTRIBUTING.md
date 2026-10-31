# 작업 규칙

A2D는 **GitHub flow**로 작업한다. `main` 브랜치 하나만 계속 유지하고, 모든 변경은 짧은 브랜치에서 만들어 Pull Request(PR)로 `main`에 합친다.

## 1. GitHub flow

```
main ──●────────────●────────────●──▶   (언제나 동작하는 상태)
        \          /  \          /
         feat/api-...    fix/web-...
```

1. **`main`은 언제나 동작한다.** `main`에 직접 커밋하거나 push하지 않는다.
2. **`origin/main`에서 브랜치를 딴다.** 작업을 시작하기 전에 항상 fetch하고, 로컬 `main`이 아니라 `origin/main`을 기준으로 삼는다. 워크트리를 만들 때도 같다.
   ```bash
   git fetch origin
   git switch -c feat/api-domain-verify origin/main
   ```
3. **작게 커밋하고 자주 push한다.** 커밋 메시지는 아래 [커밋 규칙](#3-커밋-규칙)을 따른다.
   ```bash
   git push -u origin feat/api-domain-verify
   ```
4. **PR을 연다.** 작업 중이면 Draft PR로 열어 진행 상황을 공유한다. 본문은 PR 템플릿을 채운다.
5. **리뷰를 받는다.** 다른 팀원 1명 이상이 승인해야 머지할 수 있다. 관리자도 예외가 없으니 급하면 디스코드에서 리뷰를 부탁한다. 다른 사람 담당 영역을 건드렸다면 그 담당자에게 요청한다.
6. **Squash merge로 합친다.** PR 하나가 `main`의 커밋 하나가 되고, PR 제목이 그 커밋 메시지가 된다.
7. **머지한 브랜치는 지운다.**

`main`이 앞서 나가 충돌이 나면 내 브랜치에서 `git pull --rebase origin main`으로 맞춘 뒤 다시 push한다(`--force-with-lease`). 다른 사람과 같이 쓰는 브랜치는 rebase하지 않는다.

### 워크트리는 필요할 때만

한 번에 한 작업만 하면 `git switch`로 충분하다. 아래 경우에만 `git worktree`로 폴더를 하나 더 만든다.

- 작업 도중 급한 수정이나 팀원 PR 확인 때문에 다른 브랜치를 열어야 할 때 (`stash` 대신)
- 두 브랜치를 동시에 실행해야 할 때 (예: `apps/api` 새 기능과 `target/` 결함을 함께 띄워 점검 시험)
- AI 에이전트 여러 개를 병렬로 돌릴 때 (에이전트마다 워크트리 하나)

워크트리는 저장소 바깥 `../A2D-worktrees/`에 브랜치 이름으로 만든다.

```bash
git fetch origin
git worktree add ../A2D-worktrees/fix-api-score -b fix/api-score origin/main
cd ../A2D-worktrees/fix-api-score
# 작업, 커밋, push, PR

# PR이 머지되면 정리
cd -
git worktree remove ../A2D-worktrees/fix-api-score
git branch -D fix/api-score
```

- `.env`, `node_modules`, `.venv`는 워크트리끼리 공유되지 않는다. 새 워크트리에서 다시 복사·설치한다.
- 같은 브랜치를 두 워크트리에서 동시에 열 수 없다.
- 여러 워크트리에서 서비스를 함께 띄우면 포트가 겹치지 않게 한다.
- 머지한 워크트리는 바로 지운다. `git worktree list`로 남은 것을 확인한다.

## 2. 브랜치 이름

```
<type>/<scope>-<짧은-설명>
```

- `type`과 `scope`는 커밋 규칙과 같은 값을 쓴다.
- 설명은 영어 소문자와 하이픈으로 짧게 쓴다.

| 예시 | 내용 |
| --- | --- |
| `feat/api-domain-verify` | 백엔드: DNS TXT 소유권 확인 |
| `feat/web-dashboard` | 프론트엔드: 대시보드 화면 |
| `feat/model-vllm-serve` | vLLM 서빙 스크립트 |
| `feat/target-backup-leak` | 피공격 서버에 백업 파일 노출 결함 심기 |
| `fix/api-score-overflow` | 점수 계산 버그 수정 |
| `docs/prd-milestone` | PRD 마일스톤 수정 |

## 3. 커밋 규칙

[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/)를 따른다.

```
<type>(<scope>): <요약>

<본문 (선택): 바꾼 이유나 자세한 설명>
```

- 요약은 한국어로 50자 안쪽, 끝에 마침표를 찍지 않는다.
- 한 커밋에는 한 가지 변경만 담는다.
- 여러 영역을 함께 바꾸면 scope를 비우거나 PR을 나눈다.

### type

| type | 용도 |
| --- | --- |
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서만 바꿈 |
| `refactor` | 동작은 그대로 두고 구조를 바꿈 |
| `test` | 테스트 추가·수정 |
| `style` | 포맷, 세미콜론 등 동작과 무관한 수정 |
| `perf` | 성능 개선 |
| `build` | 의존성, 빌드 설정, Dockerfile |
| `ci` | GitHub Actions 등 CI 설정 |
| `chore` | 그 밖의 잡일 (설정 파일, 저장소 정리) |

### scope

| scope | 경로 |
| --- | --- |
| `web` | `apps/web/` |
| `api` | `apps/api/` |
| `agent` | `apps/api/`의 Attack·Defense 에이전트, 프롬프트, 도구 정의 |
| `model` | `model/` |
| `target` | `target/` |
| `docs` | `docs/` |
| `brand` | `brand/` |
| `repo` | 루트 설정 (`.gitignore`, `README.md`, `.github/` 등) |

### 예시

```
feat(api): DNS TXT 레코드로 도메인 소유권 확인
fix(web): 점수가 100을 넘으면 게이지가 깨지는 문제 수정
feat(target): 인증 없는 회원 조회 API 결함 추가
build(model): vLLM 0.x 버전 고정
docs(docs): PRD에 재점검 흐름 추가
```

## 4. Pull Request

- **제목**은 squash 커밋 메시지가 되므로 커밋 규칙과 같은 형식으로 쓴다.
- **본문**은 [PR 템플릿](.github/pull_request_template.md)을 채운다. 관련 기능 번호(FR-xx)와 점검 번호(#xx)가 있으면 적는다.
- 이슈를 해결하는 PR은 본문에 `Closes #이슈번호`를 적는다. 머지되면 이슈가 자동으로 닫힌다.
- 화면을 바꿨으면 스크린샷을 붙인다.
- PR은 작게 연다. 하루 넘게 열려 있는 PR은 나눈다.

## 5. 지켜야 할 것

- **비밀값을 커밋하지 않는다.** API 키, GPU 서버 주소·계정, VPN 정보는 `.env`에 두고 `.env.example`에는 키 이름만 적는다.
- **`private/`는 git에서 제외된다.** 대회 가이드, 서버 매뉴얼, 멘토링·발표 준비, 내부 결정 기록처럼 공개하지 않는 자료는 이 폴더에 둔다.
- **피공격 서버(`target/`)는 시연 환경 밖에 띄우지 않는다.** 결함을 일부러 심은 서버다. 자세한 규칙은 [target/README.md](target/README.md)를 본다.
- **새 외부 자원은 README의 외부 자원 표에 적는다.** 라이브러리, 모델, 데이터셋, 외부 API 모두 해당한다.

## 6. 저장소 설정

아래 설정이 적용돼 있다. 바꿀 때는 팀에 먼저 알리고 이 절도 함께 고친다.

- **Settings → Rules → Rulesets → `protect-main`** (기본 브랜치 `main`에 적용, 예외 없음)
  - Require a pull request before merging: 승인 1명 이상, 머지 방식 Squash만
  - Block force pushes
  - Restrict deletions
- **Settings → General → Pull Requests**
  - Squash merging만 허용, 커밋 제목은 PR 제목
  - 머지한 브랜치 자동 삭제
- **디스코드 알림** (`.github/workflows/discord-notify.yml`)
  - 새 PR이나 이슈가 열릴 때만 팀 디스코드 채널에 알린다. 웹훅 주소는 Settings → Secrets and variables → Actions의 `DISCORD_WEBHOOK_URL`에 있다

## 7. 제출

제출할 커밋은 `main`에서 고르고 태그를 붙인다. 제출 뒤에는 `main`에 기능을 더하지 않는다.

```bash
git switch main && git pull
git tag -a v1.0.0 -m "해커톤 제출본"
git push origin v1.0.0
git rev-parse v1.0.0   # 제출할 커밋 해시
```
