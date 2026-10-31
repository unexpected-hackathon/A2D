# target · 피공격 서버 (가상 채용·인재 매칭 플랫폼)

담당: 김성원 · 커밋 scope: `target`

> **경고: 일부러 취약하게 만든 서버다.** 노트북의 시연 환경이나 격리된 네트워크에서만 띄우고, 공인 IP나 공개 도메인으로 노출하지 않는다. 심어 두는 개인정보는 모두 가짜 데이터로 만든다.

A2D가 점검하는 시연 대상. 보안 전담 인력이 부족한 소규모 채용 플랫폼·채용관리 SaaS(ATS) **JobNest**처럼 꾸미고, 설정이 잘못된 지점을 일부러 심는다. 지원자·기업회원·채용 공고 데이터는 모두 가짜로 만든다. 시연에서는 점검 → 세 가지 조치 → 재점검으로 안전 점수가 오르는 흐름을 보여 준다.

## 가상 서비스 구성

도메인은 `jobnest.test`다. `.test`는 테스트용으로 예약된 최상위 도메인(RFC 6761)이라 인터넷에서는 풀리지 않고, 시연 DNS를 쓰는 컨테이너와 기기 안에서만 이 서버를 가리킨다. `.env`의 `DEMO_DOMAIN`으로 바꿀 수 있지만 실제 공개 도메인은 쓰지 않는다.

| 자산 | 역할 | 중요도 예시 |
| --- | --- | --- |
| `jobnest.test`, `www` | 채용 공고와 지원서 작성 화면 | 4: 대표 홈페이지 (점검점수설계 2.2 자동 추정) |
| `api` | 지원자·지원 이력 조회 API | 5: 개인정보 응답 |
| `admin` | 채용 담당자 관리 화면 | 4: 관리자 도구 |
| `staging`, `dev` | 개발·테스트 채용 서비스 | 3: 테스트 자산 |
| `recruit` | 위탁 채용관리 SaaS로 가는 CNAME (#4, 식별만) | — |
| `promo` | 해지된 GitHub Pages로 가는 CNAME (#6) | 4 고정 |
| 파일 저장소 | `jobnest-resumes` S3 버킷: 가상 이력서·증빙 파일 (#14) | 5 고정 |
| `test` | 평소에는 없고, 감시 시연 때 새로 열리는 테스트 서버 | 3: 테스트 자산 |

Docker Compose로 띄우고, 컨테이너는 전용 네트워크 `a2d-demo`(10.253.53.0/24)에 붙는다.

| 서비스 | 내용 |
| --- | --- |
| `app` | 결함을 심은 JobNest 앱(Python, FastAPI). 호스트 이름으로 자산을 나누고, 결함 토글을 모두 여기서 처리한다 |
| `proxy` | nginx. TLS를 끝내고 Host를 그대로 앱에 넘긴다. 고정 IP `10.253.53.80` |
| `dns` | CoreDNS. 시연 도메인 영역(하위 도메인, CNAME, SPF·DMARC, 소유권 TXT)을 응답한다. 고정 IP `10.253.53.53` |
| `init` | 영역 파일과 인증서를 만들고 끝나는 일회성 작업 |
| `browse` | 브라우저용 HTTP 프록시. 원격·macOS·Windows에서 시연 화면을 볼 때 쓴다 |

## 기본 시연 결함

[docs/A2D_점검점수설계.md](../docs/A2D_점검점수설계.md)와 [채용 플랫폼 필요 점검리스트](../docs/research/A2D_채용플랫폼_필요점검리스트.md)를 기준으로 결함을 맞춘다. 번호는 공식 설계의 #1\~#34를 쓴다. A2D가 시연용으로 심어 둔 결함을 100% 찾는 것이 목표다(PRD 성공 지표).

기본 시연 프로필(`./demo.sh preset demo`)에서는 아래 세 결함만 활성화한다. 세 결함을 모두 찾은 뒤 `#16 API 인증 적용 → #8 백업 제거 → #18 관리자 접근 제한`을 수행하면 발견이 모두 해결되어 안전 등급이 F에서 D 이상으로 오른다. 실제 "오늘 할 일" 순서는 안전 점수 상승 폭을 계산한 코드가 정한다.

| 점검 번호 | 기본 활성 결함 | 위치 | 예상 위험 점수 |
| --- | --- | --- | --- |
| #8 | 웹 공개 경로에 남은 가상 지원자·이력서 백업 파일 | `www` `/backup.zip`, `/db.sql` | 93 (C=4) |
| #16 | 인증 없이 가상 지원자 이메일·전화번호를 반환하는 더미 API | `api` `/api/v1/applicants`, `/api/v1/applicants/{id}` | 100 |
| #16 (숨은 경로) | 사내 보고서용 지원자 내보내기. `robots.txt`가 숨긴 `/internal/reports/` 목록 페이지의 링크와 소스맵 주석에만 나온다 | `www` `/internal/reports/` → `/internal/reports/export` | 100 (추가 점검이 찾았을 때만) |
| #18 | 외부에서 열리는 채용 담당자 관리자 로그인 화면 | `admin` 루트, `www` `/admin` | 73 |

숨은 내보내기 경로는 화면 코드·API 문서에 나오지 않아 기본 점검(`LiveEngine`)은 찾지 않는다. 추가 점검(Attack 에이전트)이 `robots.txt`의 `Disallow: /internal/reports/` → 목록 페이지의 내보내기 링크 순서로 단서를 따라가야 찾는 결함이다. 이름을 추측하지 않고 닿도록 목록 페이지를 둔다. 그래서 LLM이 없거나 추가 점검을 건너뛰면 아래 예상 점수가 그대로이고, 에이전트가 찾으면 1회차 점수가 더 낮아진다. `#16`을 고치면 두 경로가 함께 401이 되므로 세 가지 조치 뒤 100 A는 같다.

점검점수설계 2.3 기본값으로 계산한 예상 안전 점수는 **20 F → (#16) 30 F → (#8) 49 D → (#18) 100 A**다. `www`는 대표 도메인이라 C=4로 계산했다. 점검 엔진이 `www`를 C=5로 추정하면 #8도 100점이 되어 #16과 동점이 되고, 조치 시간이 짧은 #8이 먼저 온다(20 F → 26 F → 49 D → 100 A).

## 항목별 검증 결함

아래 결함은 각 점검의 탐지와 해결 처리를 검증할 때 하나씩 켠다(`./demo.sh break <번호>`, 전부는 `./demo.sh preset all`). 기본 시연에서는 비활성화해 세 가지 조치 뒤에도 긴급·높음 발견이 남는 상황을 막는다. 결함마다 `FIX_<번호>=1`이면 고친 상태가 된다.

| # | 결함 상태 | 고친 상태 (`FIX_<번호>=1`) |
| --- | --- | --- |
| 6 | `promo` CNAME → `jobnest-promo.github.io`, "There isn't a GitHub Pages site here." | CNAME 레코드 삭제 |
| 8 | `www`의 `/backup.zip`, `/db.sql` (가짜 지원자 40명) | 404 |
| 9 | `www`의 `/.env`, `/.git/HEAD`, `/.git/config` | 404 |
| 10 | `www`의 `/uploads/`에 "Index of /uploads" (이력서 파일 이름) | 403 |
| 11 | 없는 주소 요청 시 500과 스택 트레이스(서버 경로·DB 주소) | 평범한 404 |
| 12 | `/static/js/app.js`에 가짜 AWS 키(`AKIA…`)와 Stripe 키(`sk_live_…`) | 키 제거 |
| 13 | `/static/js/app.js.map` 공개, 안에 같은 키 | 404, `sourceMappingURL` 제거 |
| 14 | `jobnest-resumes.s3.ap-northeast-2.amazonaws.com` 버킷 목록 | 403 AccessDenied |
| 16 | `api`가 인증 없이 지원자 이메일·전화번호 반환. 숨은 `www` `/internal/reports/`(목록)·`/internal/reports/export`도 열림 | 모두 401 |
| 17 | `api`의 `/swagger`, `/openapi.json` | 404 |
| 18 | `admin` 루트와 `www/admin`에 채용 담당자 로그인 화면 | 403 |
| 19 | `staging`, `dev`에 `DEBUG=True` 배너 | 두 호스트 전체 403 |
| 20 | `www`의 `/server-status`, `/actuator/env` | 404 |
| 21 | `api`가 아무 `Origin`(`null` 포함)을 그대로 돌려주고 `Allow-Credentials: true` | `www`·대표 도메인만 허용 |
| 23 | `Server: Apache/2.4.49 (Unix)` (CVE-2021-41773, KEV 등재) | `Server: Apache` |
| 25 | `X-Powered-By: PHP/8.1.2` (2025년 12월 지원 종료) | 헤더 제거 |
| 27 | HTTP로 접속해도 HTTPS로 옮기지 않음 | 301 → HTTPS |
| 28 | 자체 서명, 7일 뒤 만료 | 시연 CA가 발급, 1년 유효 |
| 30 | HSTS·CSP·X-Frame-Options 등 없음 | 5개 헤더 추가 |
| 31 | 쿠키 `jn_session`에 `Secure`·`HttpOnly`·`SameSite` 없음 | 세 속성 추가 |
| 32 | SPF `v=spf1 +all`, DMARC 없음 | SPF `-all`, DMARC `p=reject` |

결함 없이 찾기만 하는 항목: #1(하위 도메인), #2(홈페이지 링크), #3(`robots.txt`·사이트맵), #4(`recruit` CNAME), #24(jQuery 1.12.4, `generator` 메타 태그). `#16`의 API는 화면 코드(`app.js`)도 부르므로 `#17`을 꺼도 찾을 수 있다.

아직 없는 항목: #34(Supabase·Firebase)는 만들지 않았다. #5 인증서 발급 기록과 #33 도메인 등록 정보는 대상 서버가 아니라 외부 조회라서 `apps/api`의 시연용 가짜 응답으로 처리한다. #26(HTTPS 미사용)은 HTTPS를 제공하므로 해당하지 않는다.

## 파일 배치

`.gitignore`에 걸리는 결함 파일(`.env` 등)은 `target/planted/` 아래에 둔다. 이 경로만 예외로 추적한다. git은 `.git`이라는 폴더를 추적하지 못하므로 `/.git/*`로 내보낼 파일은 `planted/git/`에 둔다. `backup.zip`은 이미지를 빌드할 때 `planted/`에서 만든다. #12의 가짜 키는 커밋하지 않고 실행할 때 만든다(GitHub 비밀키 검사를 피하려고).

```
target/
├── compose.yml        서비스 5개와 네트워크
├── .env.example       도메인·포트·결함 토글
├── demo.sh            띄우기·토글·프리셋·상태 확인
├── app/               JobNest 앱 (Dockerfile, jobnest/)
├── proxy/default.conf nginx 설정
├── dns/Corefile       CoreDNS 설정 (바꾸면 docker compose restart dns)
└── planted/           방치된 결함 파일 (모두 가짜)
```

## 실행

Docker와 Docker Compose v2만 있으면 된다. 인터넷은 처음 이미지를 받을 때만 쓴다.

```bash
cd target
./demo.sh up            # .env가 없으면 .env.example을 복사해서 띄운다
./demo.sh preset demo   # 기본 시연 프로필 (#16 #8 #18만 결함)
./demo.sh status        # 결함별 상태
./demo.sh check         # 주요 주소 응답 코드
./demo.sh fix 16 8 18   # 세 가지를 고친 상태로 (재점검 시연)
./demo.sh preset all    # 결함 21개 모두 켜기 (점검 엔진 검증용)
./demo.sh down          # 내리기 (인증서·CA를 지우려면 ./demo.sh down -v)
```

토글은 `.env`의 `FIX_<번호>`를 바꾸고 `app`·`init`만 다시 만든다. DNS는 2초 안에, 인증서는 nginx reload로 바로 바뀐다.

### 시연 순서

A2D 서비스(`apps/web`·`apps/api`)와 타겟은 같은 노트북에서 띄운다. GPU 서버(VPN)는 LLM 추론만 하고 타겟에는 닿지 않는다. 점검 요청은 `apps/api`의 도구가 보낸다.

| 단계 | 명령 | 예상 안전 점수 |
| --- | --- | --- |
| 준비 (테이크마다) | `./demo.sh preset demo` — #16 #8 #18만 결함, 테스트 서버 닫힘 | |
| 1. 등록·소유권 확인 | 등록 화면의 TXT 값으로 `./demo.sh verify a2d-verify=<값>` | |
| 2. 점검 (Attack) | — | 20 F, 오늘 할 일 #16 → #8 → #18 |
| 3. 조치 (Defense) | `./demo.sh fix 16 8 18` | |
| 4. 재점검 | — | 100 A (하나씩 고치면 30 F → 49 D → 100 A) |
| 5. 감시 | `./demo.sh test-server on` — `test.jobnest.test`가 디버그 표시와 함께 새로 열린다 | `new_asset` 알림, #19 새 발견 |

- 전날 시연 노트북에서 인터넷이 될 때 `./demo.sh up`을 한 번 해 이미지를 받아 둔다. 두 번째 노트북도 같다.
- 프리셋은 #28을 고친 상태(시연 CA 인증서)로 둔다. 점검 엔진이 시연 CA를 믿지 않으면 #28이 자체 서명으로 하나 더 잡혀 점수가 달라진다.
- 테스트 서버는 수탁사가 새로 연 서버라는 설정이라 #19 조치(`staging`·`dev` 제한)와 상관없이 열린다.

### A2D 점검 엔진에서 붙기

`apps/api`는 같은 Docker 네트워크에 붙이고 시연 DNS를 쓰게 한다. 그러면 표준 포트(80·443)와 실제 이름 그대로 점검한다. macOS·Windows에서는 컨테이너 IP에 바로 닿지 않으므로 이 방법이 필수다.

```yaml
# apps/api 쪽 compose 예시
services:
  api:
    dns: [10.253.53.53]
    networks: [a2d-demo]
networks:
  a2d-demo:
    external: true
```

- **소유권 확인(FR-01):** API 명세(PR #12)의 `POST /domains`가 주는 `txt_record`(이름 `_a2d-verify.<도메인>`, 값 `a2d-verify=<16자리>`)를 그대로 넣는다. `./demo.sh verify a2d-verify=7f3c9e21b4d84a6c` → `_a2d-verify.jobnest.test TXT "a2d-verify=7f3c9e21b4d84a6c"`. 이름이 바뀌면 `.env`의 `A2D_VERIFY_NAME`을 고친다.
- **결함 상태의 TLS:** #28이 켜져 있으면 인증서가 자체 서명이다. 엔진이 인증서 검증을 켠 채 내용을 받으면 HTTPS 점검이 모두 실패하고 #28만 나온다. 내용 조회는 검증을 끄고(또는 실패해도 계속) 하고, 인증서는 #28에서 따로 평가한다.
- **인증서(#28):** 점검 엔진이 시연 CA를 믿게 해야 고친 상태가 "정상"으로 보인다. `./demo.sh ca > a2d-demo-ca.crt`로 받아 엔진의 CA 묶음에 더한다(예: Python `ssl`·`httpx`의 `verify=`).
- **고친 상태의 판정:** 고친 상태의 응답 코드(401·403·404)는 위 표와 같다. 점검 엔진의 판정 기준을 이 표에 맞춘다.
- VPN 대역이 `10.253.53.0/24`와 겹치면 `.env`의 `DEMO_SUBNET`·`PROXY_IP`·`DNS_IP`를 함께 바꾼다.

### 브라우저로 보기

`jobnest.test`는 인터넷 DNS에 없는 이름이라, 시연 DNS를 보게 하지 않으면 열리지 않는다.

- **리눅스:** `./demo.sh dns-on`(sudo). `*.jobnest.test` 질의만 시연 DNS로 보낸다. 스택을 다시 띄우면 다시 실행하고, 끌 때는 `./demo.sh dns-off`.
- **macOS·Windows·원격:** 브라우저용 프록시 `browse`(`127.0.0.1:18888`)를 쓴다. 시연 DNS로 이름을 풀어 주므로 hosts 수정도 sudo도 필요 없고, 시연 도메인만 통과시킨다. 원격이면 먼저 `ssh -L 18888:127.0.0.1:18888 <사용자>@<서버>`로 터널을 연다.
  ```bash
  # 시연 전용 크롬 창 (macOS)
  open -na "Google Chrome" --args --proxy-server=http://127.0.0.1:18888 --user-data-dir=/tmp/a2d-chrome
  # Windows: chrome.exe --proxy-server=http://127.0.0.1:18888 --user-data-dir=%TEMP%\a2d-chrome
  ```
- 결함 상태의 인증서는 자체 서명이라 브라우저가 경고를 띄운다(#28 그대로다).

### 알아 둘 것

- 호스트 포트는 `127.0.0.1`에만 연다(`HTTP_PORT` 18080, `HTTPS_PORT` 18443, `DNS_PORT` 15353, `BROWSE_PORT` 18888). `0.0.0.0`으로 바꾸지 않는다.
- `/swagger` 화면은 Swagger UI 스크립트를 CDN에서 받으므로 오프라인에서는 빈 화면이다. HTML과 `/openapi.json`은 그대로 열리므로 #17 점검에는 영향이 없다.
- `dns/Corefile`을 바꾸면 `docker compose restart dns`로 다시 읽게 한다(영역 파일은 자동으로 다시 읽는다).
