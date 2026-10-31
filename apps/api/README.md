# apps/api · A2D 백엔드

담당: 김성원(화면이 붙는 HTTP API), 김강현(에이전트·GPU 서버) · 커밋 scope: `api`, `agent`

## 역할

- [API 명세](../../docs/A2D_API명세.md)의 HTTP API: 세션 로그인, 도메인 등록·DNS TXT 소유권 확인(FR-01), 점검 실행·진행·중지(FR-09, NFR-03)
- 발견 위험 점수, 조직 안전 점수·A~F 등급, 오늘 할 일 3가지 선정(FR-05, FR-06)
- 대시보드 요약, 자산·발견 목록, 조치 가이드(기본 가이드 FR-11), 점수 추이·변화·감사 기록(FR-10, FR-15, FR-16)
- 점검 엔진과 Attack·Defense 에이전트는 연결 지점으로 붙인다(아래 "구조")

점검 항목과 점수 공식은 [docs/A2D_점검점수설계.md](../../docs/A2D_점검점수설계.md)를, 도구 설계는 [docs/A2D_상세설계.md](../../docs/A2D_상세설계.md)를 따른다.

## 기술 스택

Python 3.12, FastAPI, SQLite(표준 라이브러리), dnspython(TXT 확인), bcrypt(비밀번호 해시), httpx(LLM 상태 확인).

## 실행

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env        # A2D_ADMIN_EMAIL, A2D_ADMIN_PASSWORD를 채운다
.venv/bin/uvicorn a2d.main:app --port 8000 --reload
.venv/bin/python -m pytest  # 테스트
```

- 화면 개발 서버는 `/api`를 `http://127.0.0.1:8000`으로 프록시해 같은 출처로 띄운다(API 명세 3장). CORS는 열지 않는다.
- POST·PATCH는 `Origin`이 `A2D_WEB_ORIGIN`에 있어야 한다. curl로 부를 때는 `-H "Origin: http://localhost:5173"`을 붙인다.
- 화면만 개발할 때는 `.env`에 `A2D_VERIFY_MODE=trust`를 두면 TXT 조회 없이 소유권 확인이 통과한다. 시연에서는 `dns`로 둔다.

### 시연 환경(target)과 함께

```bash
(cd ../../target && ./demo.sh up && ./demo.sh preset demo)
docker compose up -d --build       # a2d-demo 네트워크에 붙고 시연 DNS(10.253.53.53)를 쓴다
# 등록 화면의 TXT 값을 넣는다
(cd ../../target && ./demo.sh verify a2d-verify=<값>)
```

노트북에서 컨테이너 없이 띄울 때는 `A2D_DNS_SERVER=127.0.0.1:15353`으로 시연 DNS의 TXT를 확인할 수 있다.

## 구조

```
a2d/
├── main.py         라우트, 세션 확인, Origin·Content-Type 검사, 오류 형식
├── auth.py         시연용 단일 계정, 서버 세션(메모리), 로그인 5회 실패 잠금
├── service.py      도메인·점검 실행·점수 반영·요약·발견·조치 가이드·기록
├── scoring.py      위험·안전 점수, 등급, 오늘 할 일 선정 (LLM 관여 없음)
├── catalog.py      점검 항목 34개, 상황별 E·X·D·C·신뢰도, 표준 조치 시간, 기본 가이드 문장
├── store.py        SQLite 저장소. 자산 ID·발견 ID를 점검이 바뀌어도 유지
├── engine/
│   ├── base.py     엔진 연결 약속(Engine, EngineContext, RawAsset, RawFinding)
│   └── fixture.py  시연 시나리오를 돌려주는 가짜 엔진 (네트워크 요청 없음)
└── agents/         Attack·Defense 에이전트 연결 지점 (김강현)
```

### 점검 엔진 붙이기

엔진은 `engine.base.Engine`을 상속해 `run(ctx)`를 구현하고, `.env`의 `A2D_ENGINE=패키지.모듈:클래스`로 바꿔 끼운다(생성자는 `Settings`를 받는다). 엔진은 `ctx.add_asset`·`ctx.add_finding`으로 자산과 발견만 넘긴다. 발견 ID·점수·오늘 할 일·조치 가이드는 API가 만든다. 발견의 `situation`은 `catalog.SITUATIONS`의 키(예: `#16 "pii"`)이고, 증거는 가린 발췌(200자 이내)만 넘긴다.

기본값 `A2D_ENGINE=fixture`는 `fixtures/demo_engine.json`을 점검 순서대로 돌려준다. target README의 시연 순서와 같다.

| 회차 | 내용 | 안전 점수 |
| --- | --- | --- |
| 1 | #16 #8 #18 결함 | 20 F, 오늘 할 일 #16 → #8 → #18 (30 F → 49 D → 100 A) |
| 2 | 세 가지를 고친 뒤 재점검 | 100 A, 해결됨 3건 |
| 3 이후 | 새 테스트 서버 `test.` 열림 | `new_asset`·`new_finding` 알림, #19 새 발견 |

### LLM 붙이기

`.env`의 `A2D_LLM_BASE_URL`에 GPU 서버 vLLM 주소(`http://<서버>:8000/v1`)를 넣으면 `/health`의 `llm`이 `up`이 된다. 조치 설명·질의응답은 `a2d/agents/__init__.py`의 `write_report`, `answer_question`을 채우면 API가 바로 쓴다. 비어 있거나 실패하면 기본 가이드(`source: "template"`)로 나가고, 질의응답은 `503 LLM_UNAVAILABLE`이다.

## API 명세와 다른 점

- `GET /domains` 추가: 로그인 뒤 이동 규칙(명세 10장, 정보구조도 "진입")은 정해져 있지만, 그 판단에 쓸 도메인 유무와 `domain_id`를 알 API가 없어 넣었다. 다른 API는 모두 `domain_id`가 있어야 부를 수 있다. 응답은 `{ "items": [ POST /domains와 같은 형식 ] }`.
- 본문 없는 POST(`/verify`, `/scans`, `/stop`, `/logout`)는 `Content-Type`을 보지 않는다. 본문이 있으면 `application/json`만 받는다.
- `GET /scans/{scan_id}/findings`의 `resolved`(해결됨)는 이번 점검에 없고 직전 점검에 있던 발견이다. `status=resolved`로 요청할 때만 목록에 들어간다.
- 질의응답은 끝난 점검에만 받는다(`409 SCAN_NOT_FINISHED`).
