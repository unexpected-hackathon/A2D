# A2D API 명세

Oct 31, 2026 · 정인호

**이 문서는 프런트엔드(`apps/web`)가 백엔드(`apps/api`)에 요청하는 HTTP API를 정한다.** 화면 4개(PRD 5장)가 필요로 하는 데이터를 기준으로 만들었고, 점검 항목 번호와 점수 값은 [A2D_점검점수설계.md](A2D_점검점수설계.md)를, 기능 번호(FR)는 [A2D_PRD.md](A2D_PRD.md)를 따른다. LLM 에이전트가 쓰는 Python 함수 도구는 이 API와 별개이며 [A2D_상세설계.md](A2D_상세설계.md) 4절에 있다.

## 1. 공통 규칙

**제출 버전은 시연용 계정 하나로 로그인해 한 조직의 흐름을 다루고, 모든 응답은 JSON이다.** 로그인은 서버 세션 방식이다(3장). 회원가입과 여러 조직 관리는 PRD 8장에서 범위 밖이다.

| 항목 | 규칙 |
| --- | --- |
| 기본 주소 | `/api/v1` |
| 형식 | 요청·응답 모두 `application/json; charset=utf-8` |
| 인증 | 세션 쿠키 `a2d_session`. `/health`, `/auth/login`을 뺀 모든 API는 로그인이 필요하다 (3장) |
| 시각 | ISO 8601, 한국 시간(`2026-10-31T14:05:00+09:00`) |
| 필드 이름 | `snake_case` |
| 점수 | 정수. 점검·점수 설계 2.1의 반올림 규칙을 적용한 값 |
| 진행 상태 | 점검 진행은 2초 간격 폴링으로 받는다. 실시간 푸시는 쓰지 않는다 |
| 증거 | 응답 원문은 내려주지 않는다. 가린 발췌(200자 이내)만 내려준다 (NFR-05) |

### ID 형식

| 대상 | 형식 | 예시 |
| --- | --- | --- |
| 도메인 | `DOM-` + 숫자 | `DOM-1` |
| 점검 | `S-` + 4자리 | `S-0003` |
| 자산 | `A-` + 3자리. 같은 도메인 안에서 점검이 바뀌어도 유지 | `A-002` |
| 발견 | `F-` + 4자리. 같은 자산·같은 항목·같은 위치면 점검이 바뀌어도 유지 | `F-0012` |
| 점검 항목 | 점검·점수 설계의 번호(정수) | `16` |

발견 ID를 점검마다 유지해야 재점검에서 "해결됨"과 "새 발견"을 가릴 수 있다(FR-09, FR-15).

### 코드 값

API는 영문 코드를 쓰고, 화면은 오른쪽 한국어 표기를 쓴다.

| 필드 | 코드 → 화면 표기 |
| --- | --- |
| `grade` (조직) | `A` `B` `C` `D` `F` |
| `severity` (발견) | `critical` 긴급 · `high` 높음 · `medium` 중간 · `low` 낮음 · `info` 참고 정보 |
| `confidence` | `confirmed` 확인됨 · `likely` 가능성 · `needs_review` 확인 필요 |
| `finding_status` | `open` 열림 · `new` 새 발견 · `resolved` 해결됨 |
| `verify_status` | `pending` 확인 대기 · `verified` 확인됨 · `failed` 확인 실패 |
| `scan_status` | `queued` 대기 · `discovering` 자산 찾는 중 · `checking` 기본 점검 중 · `agent` 추가 점검 중 · `scoring` 점수 계산 중 · `reporting` 조치 가이드 작성 중 · `done` 완료 · `stopped` 중지됨 · `failed` 실패 |
| `report_source` | `llm` AI 설명 · `template` 기본 가이드 (FR-11) |

### 오류 응답

오류는 HTTP 상태 코드와 함께 아래 형식으로 내려준다. 화면은 `message`를 그대로 보여 줘도 되게 한국어로 쓴다.

```json
{
  "error": {
    "code": "DOMAIN_NOT_VERIFIED",
    "message": "도메인 소유권이 확인되지 않아 점검을 시작할 수 없습니다."
  }
}
```

| 상태 | `code` | 언제 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식이 틀림 (도메인 형식 오류, 중요도 범위 밖 등) |
| 401 | `UNAUTHENTICATED` | 로그인하지 않았거나 세션이 만료됨. 화면은 로그인 화면으로 보낸다 |
| 401 | `INVALID_CREDENTIALS` | 로그인 때 이메일 또는 비밀번호가 틀림 |
| 403 | `FORBIDDEN_ORIGIN` | POST·PATCH의 `Origin`이 A2D 화면 주소가 아님 |
| 404 | `NOT_FOUND` | ID에 해당하는 대상이 없음 |
| 409 | `DOMAIN_NOT_VERIFIED` | 소유권 확인 전에 점검을 요청함 (FR-01) |
| 409 | `SCAN_IN_PROGRESS` | 같은 도메인에 진행 중인 점검이 있음 |
| 409 | `SCAN_NOT_FINISHED` | 끝나지 않은 점검의 조치 가이드·변화를 요청함 |
| 429 | `TOO_MANY_ATTEMPTS` | 로그인을 5회 연속 실패함. 5분 뒤 다시 시도 |
| 503 | `LLM_UNAVAILABLE` | 질의응답(FR-12)에서 모델이 응답하지 않음. 조치 가이드는 이 오류 대신 기본 가이드를 내려준다 |

## 2. 엔드포인트 목록

| 메서드 | 경로 | 하는 일 | 화면 | 기능 | 우선순위 |
| --- | --- | --- | --- | --- | --- |
| POST | `/auth/login` | 로그인, 세션 쿠키 발급 | 0 로그인 | | P0 |
| POST | `/auth/logout` | 로그아웃, 세션 삭제 | 공통 | | P0 |
| GET | `/auth/me` | 현재 로그인한 사용자 | 공통 | | P0 |
| GET | `/health` | 서버·LLM 상태 | 공통 | FR-11 | P0 |
| GET | `/checks` | 점검 항목 34개 목록 | 공통 | FR-03 | P0 |
| GET | `/domains` | 등록한 도메인 목록 | 0 로그인 | FR-01 | P0 |
| POST | `/domains` | 도메인 등록, TXT 값 발급 | 1 등록 | FR-01 | P0 |
| GET | `/domains/{domain_id}` | 도메인과 소유권 상태 | 1 등록 | FR-01 | P0 |
| POST | `/domains/{domain_id}/verify` | TXT 레코드 확인 | 1 등록 | FR-01 | P0 |
| POST | `/domains/{domain_id}/scans` | 점검·재점검 시작 | 1, 2 | FR-09 | P0 |
| GET | `/scans/{scan_id}` | 점검 진행 상태 | 2 대시보드 | FR-09 | P0 |
| POST | `/scans/{scan_id}/stop` | 점검 중지 | 2 대시보드 | NFR-03 | P0 |
| GET | `/domains/{domain_id}/summary` | 대시보드 요약 (점수, 오늘 할 일, 알림) | 2 대시보드 | FR-05, 06, 15 | P0 |
| GET | `/scans/{scan_id}/assets` | 자산 목록 | 2 대시보드 | FR-02, 14 | P0 |
| PATCH | `/domains/{domain_id}/assets/{asset_id}` | 자산 중요도 수정 | 2 대시보드 | FR-05 | P0 |
| GET | `/scans/{scan_id}/findings` | 발견 목록 | 2, 3 | FR-03, 05 | P0 |
| GET | `/findings/{finding_id}` | 발견 상세 (점수 요소, 가린 증거) | 3 조치 가이드 | FR-05 | P0 |
| GET | `/scans/{scan_id}/report` | 조치 가이드 | 3 조치 가이드 | FR-07, 08, 11 | P0 |
| POST | `/scans/{scan_id}/questions` | 담당자 질문 | 3 조치 가이드 | FR-12 | P1 |
| GET | `/domains/{domain_id}/history` | 점검별 점수 추이 | 4 기록 | FR-10 | P0 |
| GET | `/scans/{scan_id}/changes` | 직전 점검과의 변화 | 2, 4 | FR-09, 15 | P0 |
| GET | `/scans/{scan_id}/audit` | 감사 기록 | 4 기록 | FR-16 | P0 |

한 장 요약 내보내기(FR-13)는 별도 API를 두지 않는다. 화면이 `summary`와 `history`로 인쇄용 페이지를 만들고 브라우저 인쇄로 PDF를 만든다.

## 3. 인증

**로그인은 서버 세션과 쿠키로 처리한다.** 서버가 세션 ID를 만들어 `HttpOnly` 쿠키로 내려주고, 브라우저는 이후 요청마다 그 쿠키를 자동으로 보낸다. 화면 코드는 토큰을 저장하거나 헤더에 붙이지 않는다.

### 계정

- 회원가입은 없다. 시연용 계정 하나를 서버가 시작할 때 환경 변수 `A2D_ADMIN_EMAIL`, `A2D_ADMIN_PASSWORD`로 만든다. 값은 `.env`에 두고 커밋하지 않는다.
- 비밀번호는 해시(bcrypt 또는 argon2)로만 저장한다.
- 계정이 하나이므로 도메인·점검은 그 계정의 것이다. 여러 조직 관리는 계속 범위 밖이다.

### 세션 규칙

| 항목 | 규칙 |
| --- | --- |
| 쿠키 | `a2d_session=<세션 ID>; HttpOnly; SameSite=Lax; Path=/`. HTTPS로 띄우면 `Secure`도 붙인다 |
| 세션 ID | 추측할 수 없는 난수(128비트 이상). 로그인할 때마다 새로 만든다 |
| 저장 | 서버 쪽(메모리 또는 DB). 서버를 다시 띄우면 다시 로그인해야 해도 된다 |
| 만료 | 마지막 요청 후 2시간, 로그인 후 최대 8시간 |
| 로그인 필요 | `/health`, `/auth/login`을 뺀 모든 API. 세션이 없거나 만료되면 `401 UNAUTHENTICATED` |
| 로그인 시도 제한 | 같은 IP에서 5회 연속 실패하면 5분 동안 `429 TOO_MANY_ATTEMPTS` |
| 상태를 바꾸는 요청 | POST·PATCH는 `Content-Type: application/json`만 받고, `Origin` 헤더가 A2D 화면 주소가 아니면 `403 FORBIDDEN_ORIGIN`. 다른 사이트가 사용자 몰래 요청을 보내는 것(CSRF)을 막는다 |

**화면과 API는 같은 출처(origin)로 띄운다.** 개발 중에는 프런트엔드 개발 서버의 프록시로 `/api`를 백엔드에 넘긴다. 출처가 다르면 쿠키를 보내기 위해 CORS에서 자격 증명을 허용해야 하는데, 이 설정을 잘못하면 A2D가 점검하는 #21(CORS 과다 허용)을 A2D 스스로 만들게 된다.

### POST `/auth/login`

요청

```json
{ "email": "admin@triply.example", "password": "********" }
```

응답 `200 OK`. 헤더에 `Set-Cookie: a2d_session=...`가 붙는다.

```json
{
  "user": { "user_id": "U-1", "email": "admin@triply.example", "name": "IT 담당자" },
  "expires_at": "2026-10-31T22:00:00+09:00"
}
```

- 이메일이나 비밀번호가 틀리면 `401 INVALID_CREDENTIALS`. 어느 쪽이 틀렸는지는 알려 주지 않는다.
- 이미 로그인한 상태에서 다시 로그인하면 이전 세션을 지우고 새 세션을 만든다.

### POST `/auth/logout`

세션을 지우고 쿠키를 만료시킨다. 요청 본문은 없다. 응답 `204 No Content`. 세션이 없어도 `204`다.

### GET `/auth/me`

현재 로그인한 사용자를 돌려준다. 화면은 처음 열릴 때 이것으로 로그인 여부를 확인한다.

응답 `200 OK`

```json
{
  "user": { "user_id": "U-1", "email": "admin@triply.example", "name": "IT 담당자" },
  "expires_at": "2026-10-31T22:00:00+09:00"
}
```

로그인하지 않았으면 `401 UNAUTHENTICATED`.

## 4. 공통·도메인

### GET `/health`

서버와 LLM 상태를 확인한다. 화면은 `llm`이 `down`이면 조치 가이드 화면에 "기본 가이드로 표시 중"을 띄운다.

```json
{ "status": "ok", "llm": "up", "time": "2026-10-31T14:05:00+09:00" }
```

### GET `/checks`

점검 항목 이름과 분류를 내려준다. 화면은 발견의 `check_id`를 이름으로 바꿀 때 이 목록을 쓴다.

```json
{
  "items": [
    { "check_id": 16, "name": "인증 없는 API", "category": "C", "category_name": "접근 통제", "phase": "1차", "scored": true },
    { "check_id": 24, "name": "홈페이지 부품 버전", "category": "D", "category_name": "소프트웨어 버전", "phase": "1차·식별", "scored": false },
    { "check_id": 29, "name": "오래된 암호화 방식", "category": "E", "category_name": "전송·브라우저 설정", "phase": "2차", "scored": false }
  ]
}
```

`phase`는 `1차`, `1차·식별`, `2차` 중 하나다. 2차 항목도 목록에는 나오지만 점검은 하지 않는다.

### POST `/domains`

도메인을 등록하고 DNS에 넣을 TXT 레코드 값을 발급한다. 같은 도메인을 다시 등록하면 기존 도메인을 그대로 돌려준다(201 대신 200).

요청

```json
{ "domain": "triply.example" }
```

응답 `201 Created`

```json
{
  "domain_id": "DOM-1",
  "domain": "triply.example",
  "verify_status": "pending",
  "txt_record": {
    "name": "_a2d-verify.triply.example",
    "value": "a2d-verify=7f3c9e21b4d84a6c"
  },
  "verified_at": null,
  "created_at": "2026-10-31T14:00:00+09:00"
}
```

### GET `/domains`

등록한 도메인 목록이다. 로그인 직후 등록 화면과 대시보드 중 어디로 갈지 고를 때 쓴다. 항목은 `POST /domains`의 응답과 같은 형식이고, 없으면 빈 배열이다.

```json
{ "items": [ { "domain_id": "DOM-1", "domain": "triply.example", "verify_status": "verified", "...": "..." } ] }
```

### GET `/domains/{domain_id}`

`POST /domains`의 응답과 같은 형식이다. 등록 화면을 새로 고쳤을 때 쓴다.

### POST `/domains/{domain_id}/verify`

DNS TXT 레코드를 조회해 소유권을 확인한다. 확인이 끝날 때까지 기다렸다가 응답한다(최대 10초).

응답 `200 OK`

```json
{
  "domain_id": "DOM-1",
  "verify_status": "verified",
  "verified_at": "2026-10-31T14:02:10+09:00",
  "reason": null
}
```

개발·시연 설정(`A2D_VERIFY_MODE=trust`)에서는 예약 최상위 도메인(`.test`·`.example`·`.invalid`·`.localhost`)만 조회 없이 `verified`가 된다. 실제 도메인은 이 설정에서도 TXT를 조회한다.

실패하면 `verify_status`가 `failed`이고 `reason`에 이유가 온다. 예: `"TXT 레코드를 찾지 못했습니다. DNS 반영에 몇 분이 걸릴 수 있습니다."` 실패해도 HTTP 상태는 200이다.

## 5. 점검

### POST `/domains/{domain_id}/scans`

점검을 시작한다. 첫 점검과 재점검(FR-09)이 같은 API다. 바로 응답하고 점검은 뒤에서 돈다.

요청 본문은 없다.

응답 `202 Accepted`

```json
{ "scan_id": "S-0002", "status": "queued", "previous_scan_id": "S-0001" }
```

- 소유권이 확인되지 않았으면 `409 DOMAIN_NOT_VERIFIED`.
- 진행 중인 점검이 있으면 `409 SCAN_IN_PROGRESS`, `error`에 진행 중인 `scan_id`를 함께 준다.

### GET `/scans/{scan_id}`

점검 진행 상태를 내려준다. 화면은 `status`가 `done`·`stopped`·`failed`가 될 때까지 2초마다 부른다.

```json
{
  "scan_id": "S-0002",
  "domain_id": "DOM-1",
  "status": "checking",
  "stage": { "name": "기본 점검", "done": 14, "total": 24 },
  "budget": {
    "requests_used": 132, "requests_limit": 300,
    "tool_calls_used": 0, "tool_calls_limit": 20,
    "elapsed_sec": 71, "time_limit_sec": 300
  },
  "started_at": "2026-10-31T14:03:00+09:00",
  "finished_at": null,
  "safety_score": null,
  "grade": null,
  "error_message": null,
  "attack": { "status": "pending", "reason": null, "message": null }
}
```

- `stage.name`은 화면에 그대로 보여 줄 한국어다.
- `safety_score`와 `grade`는 `scoring` 단계가 끝나면 채워진다.
- `failed`이면 `error_message`에 이유가 온다.
- `attack`은 추가 점검(Attack 에이전트, FR-04)의 상태다. 이 필드가 생기기 전의 점검은 `null`이다.
  - `status`: `pending`(기본 점검 중) · `running` · `done` · `skipped`(건너뜀) · `failed` · `stopped`
  - `reason`: 건너뛰었거나 일부만 했을 때의 원인. `llm_not_configured`(LLM 주소 없음) · `llm_unavailable`(첫 LLM 요청부터 실패) · `fixture_engine`(시연용 가짜 엔진) · `no_handlers` · `llm_interrupted`(도구를 부르다 LLM이 끊김, `status`는 `done`) · `error`(`status`는 `failed`). 기본 점검을 끝내지 못해 추가 점검까지 가지 못했으면 `skipped`이고 `reason`은 `null`이다.
  - `message`: 화면에 그대로 보여 줄 한국어. `reason`이 없으면 `null`. 시연 화면에 나가므로 `fixture_engine`이어도 원인을 쓰지 않는다.

```json
{ "status": "skipped", "reason": "llm_not_configured",
  "message": "AI 서버가 연결되지 않아 추가 점검을 건너뛰었습니다. 기본 점검 결과로 점수를 냈습니다." }
```

### POST `/scans/{scan_id}/stop`

진행 중인 점검을 멈춘다(NFR-03). 멈추기 전까지 모은 발견으로 점수를 계산하고 `status`를 `stopped`로 바꾼다. 응답은 `GET /scans/{scan_id}`와 같다.

- 응답은 최대 1초만 기다린다. 그 안에 멈추지 않으면 진행 중 상태가 오고, 화면은 폴링을 이어 가 `stopped`를 받는다.
- 기본 점검을 끝내지 못한 점검(중지, 제한 시간 초과)은 이번에 다시 보지 못한 직전 점검의 자산·발견을 그대로 이어받는다. 확인하지 못한 것을 해결됨·사라짐으로 보지 않기 위해서다. 새로 찾은 자산·발견은 반영한다.
- 제한 시간 초과로 기본 점검을 끝내지 못해도 `stopped`이고, `stage.name`은 "중지됨 (제한 시간 초과)"다.

## 6. 대시보드

### GET `/domains/{domain_id}/summary`

대시보드 첫 화면에 필요한 것을 한 번에 내려준다. 가장 최근에 끝난 점검 기준이다. 아직 끝난 점검이 없으면 `latest_scan`이 `null`이다.
`latest_scan.attack`은 그 점검의 `GET /scans/{scan_id}` `attack`과 같다. 화면은 `status`가 `skipped`이거나 `message`가 있으면 그 문장을 한 줄로 보여 준다.

```json
{
  "domain_id": "DOM-1",
  "domain": "triply.example",
  "latest_scan": {
    "scan_id": "S-0001",
    "finished_at": "2026-10-31T14:07:40+09:00",
    "status": "done",
    "attack": { "status": "done", "reason": null, "message": null }
  },
  "running_scan_id": null,
  "safety_score": 12,
  "grade": "F",
  "org_risk_score": 88,
  "score_formula": "0.7 × 100 + 0.3 × (85 + 73 + 65 + 52 + 30) ÷ 5 = 88",
  "counts": { "critical": 2, "high": 2, "medium": 1, "low": 1, "info": 0 },
  "asset_count": 6,
  "today_tasks": [
    {
      "rank": 1,
      "finding_id": "F-0012",
      "check_id": 16,
      "title": "로그인 없이 회원 정보가 조회되는 API",
      "asset_alias": "api",
      "risk_score": 100,
      "severity": "critical",
      "fix_minutes": 60,
      "safety_score_after": 27,
      "grade_after": "F"
    },
    {
      "rank": 2,
      "finding_id": "F-0007",
      "check_id": 8,
      "title": "누구나 내려받을 수 있는 백업 파일",
      "asset_alias": "staging",
      "risk_score": 85,
      "severity": "critical",
      "fix_minutes": 10,
      "safety_score_after": 40,
      "grade_after": "F"
    },
    {
      "rank": 3,
      "finding_id": "F-0015",
      "check_id": 18,
      "title": "외부에서 열리는 관리자 로그인 화면",
      "asset_alias": "admin",
      "risk_score": 73,
      "severity": "high",
      "fix_minutes": 30,
      "safety_score_after": 50,
      "grade_after": "D"
    }
  ],
  "alerts": []
}
```

- `today_tasks`는 코드가 고른 순서 그대로다(FR-06). `safety_score_after`는 1번부터 그 항목까지 고쳤을 때의 안전 점수다.
- `title`은 기본 가이드(템플릿) 제목이다. LLM 설명은 `GET /scans/{scan_id}/report`에서 받는다.
- `alerts`는 직전 점검 대비 새 자산·새 발견이다(FR-15). `type`은 `new_asset` 또는 `new_finding`이다. 첫 점검이면 빈 배열이다. 예: `{ "type": "new_asset", "message": "새 하위 도메인 test.triply.example이 발견됐습니다.", "asset_id": "A-007", "finding_id": null }`
- 점검이 진행 중이면 `running_scan_id`에 그 ID가 오고, 나머지 값은 직전에 끝난 점검 기준이다.

### GET `/scans/{scan_id}/assets`

자산 목록이다. 자산 지도(FR-14)도 이 응답으로 그린다.

```json
{
  "items": [
    {
      "asset_id": "A-002",
      "alias": "api",
      "host": "api.triply.example",
      "url": "https://api.triply.example",
      "found_by": [1, 5],
      "tags": ["api", "login"],
      "importance": { "value": 5, "source": "auto", "rule": "개인정보 형태 응답" },
      "components": [
        { "name": "nginx", "version": "1.18.0", "eol": true },
        { "name": "Next.js", "version": "14.1.0", "eol": false }
      ],
      "tls_version": "TLS 1.3",
      "is_new": false,
      "finding_count": 1,
      "max_severity": "critical"
    }
  ]
}
```

- `found_by`는 이 자산을 찾은 자산 찾기 항목 번호(#1~#5)다.
- `importance.source`는 `auto`(자동 추정) 또는 `manual`(담당자 수정)이다. `rule`은 자동 추정 근거로, 점검·점수 설계 2.2의 규칙 이름이다.
- `components`는 #24 부품 식별 결과다. 점수에는 들어가지 않는다.
- `importance` 고정 항목(#6, #12, #14, #32, #33, #34)은 자산 중요도와 무관하게 고정값으로 계산한다.

### PATCH `/domains/{domain_id}/assets/{asset_id}`

담당자가 자산 중요도를 고친다. 가장 최근 점검의 점수와 오늘 할 일을 다시 계산한다. 점검은 다시 하지 않는다.

요청

```json
{ "importance": 4 }
```

응답 `200 OK`는 바뀐 자산과 다시 계산한 요약이다.

```json
{
  "asset": { "asset_id": "A-002", "importance": { "value": 4, "source": "manual", "rule": null } },
  "summary": { "safety_score": 16, "grade": "F" }
}
```

`importance`가 1~5 밖이면 `400 VALIDATION_ERROR`. 다음 점검부터도 수정한 값을 쓴다.

## 7. 발견

### GET `/scans/{scan_id}/findings`

발견 목록이다. 위험 점수가 높은 순서로 내려준다.

쿼리(모두 선택): `asset_id`, `severity`(쉼표로 여러 개), `status`, `check_id`

```json
{
  "items": [
    {
      "finding_id": "F-0012",
      "check_id": 16,
      "check_name": "인증 없는 API",
      "asset_id": "A-002",
      "asset_alias": "api",
      "situation": "개인정보 형태 데이터 반환",
      "risk_score": 100,
      "severity": "critical",
      "confidence": "confirmed",
      "status": "open",
      "first_seen_scan_id": "S-0001"
    }
  ]
}
```

`situation`은 점검·점수 설계 2.3 표의 "상황" 열과 같은 문구다.

### GET `/findings/{finding_id}`

발견 하나의 상세다. 조치 가이드의 "접힌 기술 근거"에 쓴다.

```json
{
  "finding_id": "F-0012",
  "scan_id": "S-0001",
  "check_id": 16,
  "check_name": "인증 없는 API",
  "asset_id": "A-002",
  "asset_alias": "api",
  "location": "GET https://api.triply.example/v1/members/1024",
  "situation": "개인정보 형태 데이터 반환",
  "severity": "critical",
  "confidence": "confirmed",
  "status": "open",
  "score": {
    "exposure": 5,
    "exploitability": 5,
    "data_sensitivity": 5,
    "asset_importance": 5,
    "asset_importance_fixed": false,
    "confidence_factor": 1.0,
    "risk_score": 100,
    "formula": "100 × ((5 × 5 × 5 × 5)^(1/4) − 1) ÷ 4 × 1.0 = 100"
  },
  "evidence": "200 응답, 이메일 형식 3건(j***@***.com 등), 전화번호 형식 3건 포함",
  "cves": [],
  "detected_at": "2026-10-31T14:05:12+09:00"
}
```

- `score`의 네 요소는 점검·점수 설계 2.2의 E·X·D·C다.
- `evidence`는 가린 발췌로 200자 이내다. 원문은 어떤 API로도 내려주지 않는다.
- `cves`는 #23에서만 채운다. 예: `[{ "id": "CVE-2021-41773", "cvss": 7.5, "kev": true }]`.

## 8. 조치 가이드

### GET `/scans/{scan_id}/report`

오늘 할 일 3가지의 쉬운 설명이다. 점검이 끝나기 전이면 `409 SCAN_NOT_FINISHED`.

```json
{
  "scan_id": "S-0001",
  "source": "llm",
  "verification": { "passed": 3, "total": 3 },
  "generated_at": "2026-10-31T14:07:40+09:00",
  "items": [
    {
      "rank": 1,
      "finding_ids": ["F-0012"],
      "title": "회원 정보가 로그인 없이 보입니다",
      "why_risky": "회원 조회 주소를 아는 사람은 누구나 다른 회원의 이메일과 전화번호를 볼 수 있습니다.",
      "expected_damage": "번호만 바꿔 가며 전체 회원 정보를 모을 수 있어 대량 유출로 이어질 수 있습니다.",
      "fix_steps": [
        "회원 조회 API에 로그인 확인을 추가합니다.",
        "응답에서 화면에 필요 없는 전화번호를 뺍니다."
      ],
      "fix_minutes": 60,
      "safety_score_after": 27,
      "verified": true
    }
  ]
}
```

- `source`가 `template`이면 LLM이 응답하지 않았거나 근거 검증에 두 번 실패해 기본 가이드로 바꾼 것이다(FR-11). 화면은 "기본 가이드"라고 표시한다. 형식은 같다.
- `verification`은 화면의 "근거 검증 통과 n/n"이다(FR-08). 검증에 실패한 문장은 응답에 오지 않는다.
- 항목마다 `finding_ids`가 1개 이상 있다. 화면은 이 ID로 `GET /findings/{finding_id}`를 불러 근거를 펼친다.
- 조치 가이드는 점검이 끝날 때 한 번 만들어 저장한다. 다시 불러도 LLM을 다시 부르지 않는다.

### POST `/scans/{scan_id}/questions` (P1)

담당자 질문에 근거가 붙은 답을 준다(FR-12). 점검은 실행하지 않는다. 최대 30초 걸릴 수 있다.

요청

```json
{ "question": "백업 파일은 왜 위험해요?" }
```

응답 `200 OK`

```json
{
  "answer": "staging 서버의 backup.zip은 주소만 알면 누구나 내려받을 수 있습니다. 안에 회원 DB가 들어 있으면 한 번에 전체가 유출됩니다.",
  "finding_ids": ["F-0007"],
  "verification": { "passed": true }
}
```

- 근거 발견과 연결되지 않는 질문이면 `finding_ids`가 빈 배열이고, `answer`는 "이번 점검 결과로는 답할 근거가 없습니다."다.
- 질문은 500자 이내. 넘으면 `400 VALIDATION_ERROR`.
- 모델이 응답하지 않으면 `503 LLM_UNAVAILABLE`.

## 9. 기록

### GET `/domains/{domain_id}/history`

점검별 안전 점수 추이다(FR-10). 오래된 순서로 내려준다. 끝난 점검(`done`, `stopped`)만 들어간다.

```json
{
  "items": [
    { "scan_id": "S-0001", "finished_at": "2026-10-31T14:07:40+09:00", "status": "done", "safety_score": 12, "grade": "F", "new_count": 6, "resolved_count": 0 },
    { "scan_id": "S-0002", "finished_at": "2026-10-31T14:31:05+09:00", "status": "done", "safety_score": 50, "grade": "D", "new_count": 0, "resolved_count": 3 }
  ]
}
```

### GET `/scans/{scan_id}/changes`

직전 점검과 비교한 변화다. 재점검 뒤 "해결됨"·"새 발견"을 보여 줄 때 쓴다(FR-09, FR-15). 첫 점검이면 `previous_scan_id`가 `null`이고 모든 발견이 `new_findings`에 들어간다.

중지된 점검은 확인하지 못한 직전 발견을 이어받으므로(5장) `resolved_findings`·`removed_assets`가 생기지 않는다.

```json
{
  "scan_id": "S-0002",
  "previous_scan_id": "S-0001",
  "safety_score": { "before": 12, "after": 50 },
  "grade": { "before": "F", "after": "D" },
  "resolved_findings": [
    { "finding_id": "F-0012", "check_id": 16, "asset_alias": "api", "risk_score": 100 },
    { "finding_id": "F-0007", "check_id": 8, "asset_alias": "staging", "risk_score": 85 },
    { "finding_id": "F-0015", "check_id": 18, "asset_alias": "admin", "risk_score": 73 }
  ],
  "new_findings": [],
  "new_assets": [],
  "removed_assets": []
}
```

### GET `/scans/{scan_id}/audit`

점검 하나의 감사 기록이다(FR-16, NFR-09). 시각 순서로 내려준다.

쿼리(모두 선택): `actor`(`system`·`attack`·`defense`), `rejected`(`true`면 거부된 호출만)

```json
{
  "items": [
    {
      "at": "2026-10-31T14:05:10+09:00",
      "actor": "attack",
      "tool": "check_unauth_api",
      "args": { "asset_id": "A-002", "endpoint_id": "E-004" },
      "result_summary": "발견 F-0012 기록",
      "rejected": false,
      "reject_reason": null
    },
    {
      "at": "2026-10-31T14:05:31+09:00",
      "actor": "attack",
      "tool": "check_paths",
      "args": { "asset_id": "A-099", "category": "backup" },
      "result_summary": null,
      "rejected": true,
      "reject_reason": "소유권이 확인된 자산이 아님"
    }
  ]
}
```

- `actor`가 `system`이면 LLM 없이 코드가 돌린 기본 점검이다.
- `args`에는 자산 ID와 엔드포인트 ID만 있고 URL이나 응답 원문은 없다.

## 10. 화면별 호출 순서

### 0. 로그인

1. 화면이 처음 열리면 `GET /auth/me`. `401`이면 로그인 화면으로 간다.
2. 이메일·비밀번호를 받아 `POST /auth/login`. 성공하면 `GET /domains`로 도메인이 없을 때 등록, 있을 때 대시보드로 간다.
3. 어느 API든 `401 UNAUTHENTICATED`가 오면 로그인 화면으로 보내고 "다시 로그인해 주세요"를 보여 준다.
4. 머리글의 "로그아웃"은 `POST /auth/logout` 뒤 로그인 화면으로 간다.

### 1. 등록

1. `POST /domains`로 TXT 값을 받아 보여 준다.
2. 담당자가 DNS에 넣고 "확인" 버튼을 누르면 `POST /domains/{id}/verify`.
3. `verified`가 되면 "점검 시작" 버튼으로 `POST /domains/{id}/scans`, 대시보드로 이동한다.

### 2. 대시보드

1. `GET /domains/{id}/summary`로 점수, 등급, 오늘 할 일, 알림을 그린다.
2. `running_scan_id`가 있으면 `GET /scans/{scan_id}`를 2초마다 불러 진행 상태를 보여 주고, 끝나면 1을 다시 부른다.
3. `GET /scans/{latest_scan_id}/assets`로 자산 목록(또는 지도)을 그린다.
4. "재점검" 버튼은 `POST /domains/{id}/scans`.

### 3. 조치 가이드

1. `GET /scans/{scan_id}/report`로 항목을 그린다.
2. 근거를 펼치면 `GET /findings/{finding_id}`.
3. 질문 입력란(P1)은 `POST /scans/{scan_id}/questions`.

### 4. 기록

1. `GET /domains/{id}/history`로 점수 추이 그래프를 그린다.
2. 점검을 고르면 `GET /scans/{scan_id}/changes`와 `GET /scans/{scan_id}/audit`.
3. "내보내기"는 `summary`와 `history`로 인쇄용 페이지를 만들어 브라우저 인쇄로 저장한다.

## 11. 정해야 할 것

- [ ] 웹 프레임워크가 정해지면 이 문서와 같은 OpenAPI 스키마를 자동 생성해 `/api/v1/openapi.json`으로 열고, 차이가 나면 이 문서를 고친다. 이 경로는 A2D 자체에서 #17(API 설명서 공개)에 걸리므로 시연 환경 밖에 열지 않는다
- [ ] 프런트엔드 개발 서버의 `/api` 프록시 설정 (같은 출처로 띄우기)
- [ ] 세션 저장 위치(메모리 또는 DB)와 시연용 계정 이메일
- [ ] PRD 8장 "범위 밖"의 로그인 문구를 "시연용 단일 계정 로그인"으로 고치기
- [ ] 점검 항목별 표준 조치 시간(`fix_minutes`) 값 (PRD 미결 사항)
- [ ] 기본 가이드의 항목별 제목·설명 문장
