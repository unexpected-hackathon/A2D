<p align="center"><img src="brand/logo/png/a2d-logo.png" alt="A2D" width="320"></p>

# A2D (Attack to Defense)

보안팀이 없는 조직을 위한 외부 노출 점검 서비스. 공격자가 약한 고리를 찾는 방법으로 매일 침입 없이 점검하고, 점수 하나와 "오늘 할 일 3가지"를 알려준다. 코디세이 AI 해커톤 2026 출품작.

## 저장소 구조

서비스, 모델 배포, 시연용 피공격 서버를 한 저장소에 둔다(모노레포).

| 경로 | 내용 | 담당 |
| --- | --- | --- |
| [apps/web/](apps/web/README.md) | A2D 프론트엔드: 등록·대시보드·조치 가이드·기록 4개 화면 | 정인호 |
| [apps/api/](apps/api/README.md) | A2D 백엔드: 소유권 확인, 자산 발견·점검 엔진, 위험 점수, Attack·Defense 에이전트 | 김성원, 김강현(에이전트) |
| [model/](model/README.md) | AI 모델 배포 스크립트: GPU 서버에서 Qwen3-8B를 vLLM으로 서빙, GPU 서버 설정 순서 | 김강현 |
| [target/](target/README.md) | 피공격 서버: 결함을 일부러 심은 가상 채용·인재 매칭 플랫폼(시연 대상) | 김성원 |
| [docs/](docs/) | 기획서, 상세 설계, 점검·점수 설계, PRD, API 명세, 정보 구조도 | 김강현 |
| [brand/](brand/logo/README.md) | 로고와 색 | 김강현 |

작업 방식(GitHub flow, 브랜치·커밋·PR 규칙)은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따른다.

## 문서

| 파일 | 내용 |
| --- | --- |
| [docs/A2D_기획서.md](docs/A2D_기획서.md) | 문제, 타깃, 서비스, AI 활용, 차별점, 안전, MVP, 효과, 팀, 위험 |
| [docs/A2D_상세설계.md](docs/A2D_상세설계.md) | 점검 구현 범위·안전 제한 요약, LLM 선택, Python 함수 도구 호출 설계 |
| [docs/A2D_점검점수설계.md](docs/A2D_점검점수설계.md) | 비침습 점검 항목 34개(1차 29개), 위험·안전 점수 계산식, 항목별 기본값, 시나리오 검증 |
| [docs/A2D_PRD.md](docs/A2D_PRD.md) | 기능 FR-01~16, 화면, AI, 비기능, 범위 밖, 마일스톤 |
| [docs/A2D_API명세.md](docs/A2D_API명세.md) | 프런트엔드가 쓰는 백엔드 HTTP API: 엔드포인트 22개(세션 로그인 포함), 요청·응답 예시, 화면별 호출 순서 |
| [docs/A2D_정보구조도.md](docs/A2D_정보구조도.md) | 로그인과 화면 4개의 구역·이동 경로·구역별 API, 사용자 흐름, 화면 상태와 용어 |
| [docs/A2D_시연진행.md](docs/A2D_시연진행.md) | 시연을 반복해서 찍는 순서: 처음 한 번 준비, 테이크마다 할 일과 화면, 결과가 같게 나오는 조건, 실수했을 때 |
| [docs/research/A2D_도메인선정_근거검증_사례28건.md](docs/research/A2D_도메인선정_근거검증_사례28건.md) | 채용·인재 매칭 플랫폼을 대표 사례·시연 도메인으로 고른 근거와 사고 사례 28건 |
| [docs/research/A2D_채용플랫폼_필요점검리스트.md](docs/research/A2D_채용플랫폼_필요점검리스트.md) | 채용 플랫폼 우선 점검 항목, 안전 조건, 구현 순서 |

## 브랜드

- [brand/logo/](brand/logo/README.md): 확정 로고(후보 7 "한붓 라인") SVG·PNG와 사용 규칙
- [brand/logo-candidates/](brand/logo-candidates/README.md): 로고 후보 7종 SVG와 콘셉트

## 실행 방법

시연 환경은 한 노트북에서 피공격 서버(`target/`)와 A2D 백엔드(`apps/api/`)를 Docker로, 화면(`apps/web/`)을 Node로 띄운다. Docker와 Docker Compose v2, Node.js가 필요하고, 인터넷은 처음 이미지·패키지를 받을 때만 쓴다. 자세한 설정은 각 디렉터리의 README를 본다.

```bash
cp apps/api/.env.example apps/api/.env   # A2D_ADMIN_EMAIL, A2D_ADMIN_PASSWORD를 채운다
./a2d-demo.sh up        # 피공격 서버(시연 프로필 #16 #8 #18) → 백엔드 → 화면. http://localhost:4173
# 등록 화면에서 도메인 jobnest.test를 넣은 뒤
./a2d-demo.sh verify    # 백엔드에서 TXT 값을 읽어 시연 DNS에 넣는다. 화면에서 "확인"을 누른다
./a2d-demo.sh status    # 세 부분의 상태, LLM 연결(꺼져 있으면 붙이는 방법), 다음 점검 회차
./a2d-demo.sh down
```

| 명령 | 하는 일 |
| --- | --- |
| `up` | `target/demo.sh up`·`preset demo` → `apps/api`에서 `docker compose up -d --build` → `VITE_USE_MOCK=false`로 화면을 빌드해 `vite preview`로 띄운다. 화면 주소가 `A2D_WEB_ORIGIN`에 없으면 띄우기 전에 멈춘다 |
| `reset` | 새 테이크 준비. 결함을 시연 프로필로 되돌리고 백엔드 데이터(점검 기록·등록 도메인)를 지운다. 도메인을 다시 등록하고 `verify`부터 한다 |
| `verify [값]` | 값을 비우면 `apps/api/.env` 계정으로 백엔드에 로그인해 시연 도메인의 TXT 값을 읽어 `target/demo.sh verify`에 넘긴다 |
| `fix`·`break`·`preset`·`test-server`·`check`·`dns-on`·`dns-off` | `target/demo.sh`에 그대로 넘긴다 |
| `logs api\|web\|target` | 로그 보기. 화면 로그와 프로세스 번호는 `.demo/`에 둔다 |

- 화면 포트는 `A2D_WEB_PORT`(기본 4173)로 바꾼다. 바꾼 주소는 `apps/api/.env`의 `A2D_WEB_ORIGIN`에도 넣는다.
- LLM은 GPU 서버에 VPN과 SSH 터널로 붙어야 해서 스크립트가 터널을 열지 않는다. `status`가 OS에 맞는 `A2D_LLM_BASE_URL`과 `model/.env`의 `TUNNEL_BIND`를 알려 준다([model/README.md](model/README.md#백엔드에서-부르기)). LLM이 없으면 조치 가이드는 기본 가이드로 나간다.
- 기본 점검 엔진(`A2D_ENGINE=fixture`)은 시연 시나리오를 돌려주는 가짜 엔진이라 피공격 서버에 점검 요청을 보내지 않는다.

테이크를 반복하는 순서와 단계별 화면·명령은 [docs/A2D_시연진행.md](docs/A2D_시연진행.md)에, 피공격 서버의 결함별 세부는 [target/README.md](target/README.md) "시연 순서"에 있다. 그 표의 결함 조작(`preset`·`fix`·`test-server`)은 루트에서 `./a2d-demo.sh`로도 쓸 수 있다.

## 외부 자원

사용한 외부 모델·오픈소스는 모두 이 표에 적는다. 새 라이브러리나 모델을 추가하는 PR은 이 표에도 한 줄을 더한다.

| 자원 | 용도 | 라이선스 |
| --- | --- | --- |
| Qwen3-8B | Attack·Defense 에이전트 LLM | Apache 2.0 |
| vLLM 0.31.0 | 모델 서빙 (OpenAI 호환 엔드포인트) | Apache 2.0 |
| PyTorch 2.13.0 (vLLM 의존성) | 모델 실행 | BSD-3-Clause |
| Hugging Face Hub CLI (`hf`, vLLM 의존성) | 모델 가중치 내려받기 | Apache 2.0 |
| uv 0.13.6 | GPU 서버 Python 가상 환경·패키지 설치 | Apache 2.0 · MIT |
| FastAPI 0.115.6 · Uvicorn 0.34.0 | 피공격 서버 앱 | MIT · BSD-3-Clause |
| cryptography 44.0.0 | 피공격 서버 시연 인증서 생성 | Apache 2.0 · BSD |
| nginx 1.27.4 (Docker 이미지) | 피공격 서버 TLS 프록시 | BSD-2-Clause |
| CoreDNS 1.11.3 (Docker 이미지) | 피공격 서버 시연 DNS | Apache 2.0 |
| Python 3.12 slim (Docker 이미지) | 피공격 서버 실행 환경 | PSF |
| curl 8.11.1 (Docker 이미지) | 피공격 서버 응답 확인(`demo.sh check`) | curl 라이선스(MIT 계열) |
| FastAPI 0.115.6 · Uvicorn 0.34.0 | A2D 백엔드 API | MIT · BSD-3-Clause |
| httpx 0.28.1 | A2D 백엔드 LLM 상태 확인 | BSD-3-Clause |
| dnspython 2.7.0 | A2D 백엔드 DNS TXT 소유권 확인 | ISC |
| bcrypt 4.2.1 | A2D 백엔드 비밀번호 해시 | Apache 2.0 |
| pytest 8.3.4 | A2D 백엔드 테스트 | MIT |
| React 19.3.1 · Vite 8.3.5 · TypeScript 7.0.2 | 프런트엔드 화면과 개발 서버 | MIT · MIT · Apache 2.0 |
| [SEED Design](https://github.com/daangn/seed-design) (@seed-design/react 3.1.0 · css 3.1.0 · vite-plugin 2.1.1 · cli 1.7.3) | 프런트엔드 디자인 시스템(주식회사 당근마켓). UI 스니펫을 `apps/web/seed-design/`에 복사해 쓰고 LICENSE·NOTICE를 함께 둠. 브랜드 색은 A2D 색으로 덮어쓰고 당근 브랜드 리소스는 쓰지 않음 | Apache 2.0 |
| @karrotmarket/react-monochrome-icon 1.32.0 | 프런트엔드 아이콘(SEED 아이콘 세트) | Apache 2.0 |
| React Router 7.18.5 | 프런트엔드 화면 이동 | MIT |
| Motion 14.9.0 | 프런트엔드 화면 전환·숫자 애니메이션 | MIT |
| Pretendard 1.3.9 | 프런트엔드 글꼴(오프라인용으로 패키지에 포함) | OFL-1.1 |
| Vitest 5.0.5 · jsdom 30.1.3 · Testing Library | 프런트엔드 테스트(개발용) | MIT |
