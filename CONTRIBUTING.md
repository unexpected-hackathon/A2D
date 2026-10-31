# 작업 규칙

A2D는 **GitHub flow**로 작업한다. `main` 하나만 길게 살아 있고, 모든 변경은 짧은 브랜치에서 만들어 Pull Request(PR)로 `main`에 합친다.

## 1. GitHub flow

```
main ──●────────────●────────────●──▶   (언제나 동작하는 상태)
        \          /  \          /
         feat/api-...    fix/web-...
```

1. **`main`은 언제나 동작한다.** `main`에 직접 커밋하거나 push하지 않는다.
2. **최신 `main`에서 브랜치를 딴다.**
   ```bash
   git switch main && git pull
   git switch -c feat/api-domain-verify
   ```
3. **작게 커밋하고 자주 push한다.** 커밋 메시지는 아래 [커밋 규칙](#3-커밋-규칙)을 따른다.
   ```bash
   git push -u origin feat/api-domain-verify
   ```
4. **PR을 연다.** 작업 중이면 Draft PR로 열어 진행 상황을 공유한다. 본문은 PR 템플릿을 채운다.
5. **리뷰를 받는다.** 다른 팀원 1명의 승인을 받는다. 리뷰어가 30분 안에 답하지 못하면 작성자가 머지하고, PR에 그 사실을 한 줄 남긴다.
6. **Squash merge로 합친다.** PR 하나가 `main`의 커밋 하나가 되고, PR 제목이 그 커밋 메시지가 된다.
7. **머지한 브랜치는 지운다.**

`main`이 앞서 나가 충돌이 나면 내 브랜치에서 `git pull --rebase origin main`으로 맞춘 뒤 다시 push한다(`--force-with-lease`). 남과 같이 쓰는 브랜치는 rebase하지 않는다.

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

<본문: 무엇을, 왜 바꿨는지 (선택)>
```

- 요약은 한국어로 50자 안쪽, 끝에 마침표를 찍지 않는다.
- 한 커밋에는 한 가지 변경만 담는다.
- 여러 영역을 함께 바꾸면 scope를 비우거나 PR을 나눈다.

### type

| type | 쓰는 때 |
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
- **본문**은 [PR 템플릿](.github/pull_request_template.md)을 채운다. 관련 기능 번호(FR-xx, C-xx)를 적는다.
- 화면을 바꿨으면 스크린샷을 붙인다.
- PR은 작게 연다. 하루 넘게 열려 있는 PR은 나눈다.

## 5. 지켜야 할 것

- **비밀값을 커밋하지 않는다.** API 키, GPU 서버 주소·계정, VPN 정보는 `.env`에 두고 `.env.example`에는 키 이름만 적는다.
- **`private/`는 git에서 제외된다.** 대회 가이드, 서버 매뉴얼, 멘토링·발표 준비처럼 공개하지 않는 자료는 이 폴더에 둔다.
- **피공격 서버(`target/`)는 시연 환경 밖에 띄우지 않는다.** 결함을 일부러 심은 서버다. 자세한 규칙은 [target/README.md](target/README.md)를 본다.
- **새 외부 자원은 README의 외부 자원 표에 적는다.** 라이브러리, 모델, 데이터셋, 외부 API 모두 해당한다.

## 6. 저장소 설정 (관리자 1회)

GitHub 저장소 Settings에서 아래를 켠다.

- **Branches → Branch protection rule (`main`)**
  - Require a pull request before merging, Required approvals: 1
  - Do not allow bypassing the above settings 해제 (30분 규칙으로 작성자 머지를 허용하려면 관리자 우회를 남겨 둔다)
  - Allow force pushes, Allow deletions 끄기
- **General → Pull Requests**
  - Allow squash merging만 켜고, Default commit message는 "Pull request title"
  - Automatically delete head branches 켜기

## 7. 제출

제출할 커밋은 `main`에서 고르고 태그를 붙인다. 제출 뒤에는 `main`에 기능을 더하지 않는다.

```bash
git switch main && git pull
git tag -a v1.0.0 -m "해커톤 제출본"
git push origin v1.0.0
git rev-parse v1.0.0   # 제출할 커밋 해시
```
