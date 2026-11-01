<p align="center"><img src="brand/logo/png/a2d-logo.png" alt="A2D" width="320"></p>

# A2D (Attack to Defense)

> **AI가 공격을 누구나 할 수 있게 만들었다면, A2D는 방어를 누구나 할 수 있게 만든다.**

보안팀 없이 서비스를 만드는 팀을 위한 외부 노출 점검 서비스. 도메인을 등록하면 공격자가 약한 고리를 찾는 순서 그대로, 침입 없이 읽기 요청만으로 점검하고, 점수 하나와 "오늘 할 일 3가지"를 알려 준다. 이름은 읽으면 aid(도움)다. 코디세이 AI 해커톤 2026 출품작.

## 기획 의도

A2D는 세 막짜리 이야기에서 출발했다. 근거는 [문제 정의 근거 사례](docs/research/A2D_문제정의_근거사례.md)에 모았다.

| 막 | 이야기 | 근거 |
| --- | --- | --- |
| **1막. 공격은 누구나** | AI 덕분에 누구나 서비스를 만들고, 누구나 공격한다 | AI 앱 빌더로 만든 170개 프로젝트에서 공개 키만으로 개인정보가 열렸다(CVE-2025-48757). IT 비전공자가 AI 침투 도구로 병원·학원·상조회사에서 개인정보 820만 건을 빼냈다(2026.10 송치) |
| **2막. 방어는 전문가만** | 그런데 지키는 사람은 예전 그대로다 | 종사자 10~249명 기업의 평균 정보보호 담당 인력은 1.3명, 침해를 알아차리기까지 평균 106.1일. 관리자 화면에 IP 제한 하나 없어 과징금 1억 6,800만 원을 받은 회사도 있다 |
| **3막. A2D** | 보안 지식이 없어도 찾고, 순서를 정하고, 고친 것을 확인할 수 있게 한다 | 아래 "A2D가 하는 일" |

**누구를 위한 서비스인가.** AI 코딩 도구와 Supabase 같은 BaaS로 개인정보를 다루는 서비스를 만들어 직접 운영하는 1~3명 팀이다. 코드와 도메인은 직접 쥐고 있지만 보안 교육은 받은 적 없고, 대표가 "우리 괜찮아?"라고 물으면 답하기 어려운 개발자다. 시연은 이런 팀이 만든 가상 채용 플랫폼 JobNest로 한다.

**A2D가 하는 일.** 모두 지금 저장소에서 동작한다.

| 하는 일 | 내용 |
| --- | --- |
| 찾는다 | 하위 도메인, 크롤러로 찾은 숨은 경로, 공개 파일, 화면 코드 속 비밀키, Supabase·Firebase 공개 접근, 열린 관리자 화면 |
| 순서를 정한다 | 공개된 계산식으로 위험 점수를 매기고, 고쳤을 때 안전 점수가 가장 많이 오르는 세 가지를 고른다. 순위에 LLM은 관여하지 않는다 |
| 쉬운 말로 설명한다 | AI가 이유와 예상 피해를 쓰고, 코드가 그 문장이 실제 발견과 맞는지 확인한 뒤에만 보여 준다. 맞지 않거나 LLM이 없으면 팀이 쓴 기본 가이드로 대신한다 |
| 고친 것을 확인한다 | 재점검을 직전 점검과 비교해 해결됨·새 자산·새 노출을 보여 준다 |
| 건드리지 않는다 | 소유를 증명한 도메인에만, 읽기 요청(GET·DNS·TLS)만, 호스트당 초당 2건 이하로 보낸다 |

시연에서는 첫 점검 20점 F가 오늘 할 일 세 가지(로그인 없이 지원자 연락처가 보이는 API, 웹에 남은 백업 파일, 외부에 열린 관리자 화면)를 차례로 고치자 30점, 49점, 100점 A가 된다.

**아직 계획인 것.** 정해진 시간에 자동으로 도는 매일 점검과 메일·메신저 알림, 배포 전 점검, Supabase 테이블별 접근 규칙 심층 점검, 로그인 뒤 권한 점검. 근거와 순서는 [기획서](docs/A2D_기획서.md)의 확장 로드맵에 있다.

## 저장소 구조

서비스, 모델 배포, 시연용 타깃 서버를 한 저장소에 둔다(모노레포).

| 경로 | 내용 | 담당 |
| --- | --- | --- |
| [apps/web/](apps/web/README.md) | A2D 프론트엔드: 등록·대시보드·조치 가이드·기록 4개 화면 | 정인호 |
| [apps/api/](apps/api/README.md) | A2D 백엔드: 소유권 확인, 자산 발견·점검 엔진, 위험 점수, Attack·Defense 에이전트 | 김성원, 김강현(에이전트) |
| [model/](model/README.md) | AI 모델 배포 스크립트: GPU 서버에서 Qwen3-8B를 vLLM으로 서빙, GPU 서버 설정 순서 | 김강현 |
| [target/](target/README.md) | 타깃 서버: 결함을 일부러 심은 가상 채용·인재 매칭 플랫폼(시연 대상) | 김성원 |
| [docs/](docs/) | 기획서, 상세 설계, 점검·점수 설계, PRD, API 명세, 정보 구조도 | 김강현 |
| [brand/](brand/logo/README.md) | 로고와 색 | 김강현 |

작업 방식(GitHub flow, 브랜치·커밋·PR 규칙)은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따른다.

## 문서

| 파일 | 내용 |
| --- | --- |
| [docs/A2D_기획서.md](docs/A2D_기획서.md) | 핵심 문장과 3막 이야기, 핵심 타깃, 서비스, AI 활용, 차별점, 안전, MVP, 효과와 확장 로드맵, 팀, 위험 |
| [docs/A2D_상세설계.md](docs/A2D_상세설계.md) | 점검 구현 범위·안전 제한 요약, LLM 선택, Python 함수 도구 호출 설계 |
| [docs/A2D_점검점수설계.md](docs/A2D_점검점수설계.md) | 비파괴 점검 항목 34개(1차 29개), 위험·안전 점수 계산식, 항목별 기본값, 시나리오 검증 |
| [docs/A2D_PRD.md](docs/A2D_PRD.md) | 기능 FR-01~16, 화면, AI, 비기능, 범위 밖, 마일스톤 |
| [docs/A2D_API명세.md](docs/A2D_API명세.md) | 프런트엔드가 쓰는 백엔드 HTTP API: 엔드포인트 22개(세션 로그인 포함), 요청·응답 예시, 화면별 호출 순서 |
| [docs/A2D_정보구조도.md](docs/A2D_정보구조도.md) | 로그인과 화면 4개의 구역·이동 경로·구역별 API, 사용자 흐름, 화면 상태와 용어 |
| [docs/A2D_시연진행.md](docs/A2D_시연진행.md) | 시연을 반복해서 찍는 순서: 처음 한 번 준비, 테이크마다 할 일과 화면, 결과가 같게 나오는 조건, 실수했을 때 |
| [docs/research/A2D_문제정의_근거사례.md](docs/research/A2D_문제정의_근거사례.md) | 핵심 문장과 3막 이야기(공격은 누구나, 방어는 전문가만, A2D)를 받치는 실제 사례·수치와 출처, 쓰면 안 되는 표현 |
| [docs/research/A2D_도메인선정_근거검증_사례28건.md](docs/research/A2D_도메인선정_근거검증_사례28건.md) | 채용·인재 매칭 플랫폼을 대표 사례·시연 도메인으로 고른 근거와 사고 사례 28건 |
| [docs/research/A2D_채용플랫폼_필요점검리스트.md](docs/research/A2D_채용플랫폼_필요점검리스트.md) | 채용 플랫폼 우선 점검 항목, 안전 조건, 구현 순서 |

## 브랜드

- [brand/logo/](brand/logo/README.md): 확정 로고(후보 7 "한붓 라인") SVG·PNG와 사용 규칙
- [brand/logo-candidates/](brand/logo-candidates/README.md): 로고 후보 7종 SVG와 콘셉트

## 실행 방법

시연 환경은 한 노트북에서 타깃 서버(`target/`)와 A2D 백엔드(`apps/api/`)를 Docker로, 화면(`apps/web/`)을 Node로 띄운다. Docker와 Docker Compose v2, Node.js가 필요하고, 인터넷은 처음 이미지·패키지를 받을 때만 쓴다. 자세한 설정은 각 디렉터리의 README를 본다.

```bash
cp apps/api/.env.example apps/api/.env   # A2D_ADMIN_EMAIL, A2D_ADMIN_PASSWORD를 채운다
./a2d-demo.sh up        # 타깃 서버(시연 프로필 #16 #8 #18) → 백엔드 → 화면. http://localhost:4173
# 등록 화면에서 도메인 jobnest.test를 넣은 뒤
./a2d-demo.sh verify    # 백엔드에서 TXT 값을 읽어 시연 DNS에 넣는다. 화면에서 "확인"을 누른다
./a2d-demo.sh status    # 세 부분의 상태, LLM 연결(꺼져 있으면 붙이는 방법), 끝난 점검 수
./a2d-demo.sh down
```

| 명령 | 하는 일 |
| --- | --- |
| `up` | `target/demo.sh up`·`preset demo` → `apps/api`에서 `docker compose up -d --build` → `VITE_USE_MOCK=false`로 화면을 빌드해 `vite preview`로 띄운다. 화면 주소가 `A2D_WEB_ORIGIN`에 없으면 띄우기 전에 멈춘다 |
| `reset` | 새 테이크 준비. 결함을 시연 프로필로 되돌리고 백엔드 데이터(점검 기록·등록 도메인)를 지운다. 도메인을 다시 등록하고 `verify`부터 한다 |
| `verify [값]` | 값을 비우면 `apps/api/.env` 계정으로 백엔드에 로그인해 시연 도메인의 TXT 값을 읽어 `target/demo.sh verify`에 넘긴다 |
| `restart-api` | `apps/api/.env`(LLM 주소 등)나 백엔드 코드를 고친 뒤 백엔드만 다시 빌드해 띄운다(`docker compose up -d --build --force-recreate api`). 점검 기록과 결함 상태는 그대로 둔다 |
| `fix`·`break`·`preset`·`test-server`·`check`·`dns-on`·`dns-off` | `target/demo.sh`에 그대로 넘긴다 |
| `logs api\|web\|target` | 로그 보기. 화면 로그와 프로세스 번호는 `.demo/`에 둔다 |

- 화면 포트는 `A2D_WEB_PORT`(기본 4173)로 바꾼다. 바꾼 주소는 `apps/api/.env`의 `A2D_WEB_ORIGIN`에도 넣는다.
- LLM은 GPU 서버에 VPN과 SSH 터널로 붙어야 해서 스크립트가 터널을 열지 않는다. `status`가 OS에 맞는 `A2D_LLM_BASE_URL`과 `model/.env`의 `TUNNEL_BIND`를 알려 준다([model/README.md](model/README.md#백엔드에서-부르기)). LLM이 없으면 조치 가이드는 기본 가이드로 나간다.
- 점검 엔진은 `LiveEngine`이다. 타깃 서버에 읽기 요청만 보내 실제로 점검하고, 결과는 결함 상태대로 나온다. 소유권은 언제나 TXT 레코드로 확인한다(`verify`가 시연 DNS에 넣는다).

테이크를 반복하는 순서와 단계별 화면·명령은 [docs/A2D_시연진행.md](docs/A2D_시연진행.md)에, 타깃 서버의 결함별 세부는 [target/README.md](target/README.md) "시연 순서"에 있다. 그 표의 결함 조작(`preset`·`fix`·`test-server`)은 루트에서 `./a2d-demo.sh`로도 쓸 수 있다.

## 외부 자원

사용한 외부 모델·오픈소스는 모두 이 표에 적는다. 새 라이브러리나 모델을 추가하는 PR은 이 표에도 한 줄을 더한다.

| 자원 | 용도 | 라이선스 |
| --- | --- | --- |
| Qwen3-8B | Attack·Defense 에이전트 LLM | Apache 2.0 |
| vLLM 0.31.0 | 모델 서빙 (OpenAI 호환 엔드포인트) | Apache 2.0 |
| PyTorch 2.13.0 (vLLM 의존성) | 모델 실행 | BSD-3-Clause |
| Hugging Face Hub CLI (`hf`, vLLM 의존성) | 모델 가중치 내려받기 | Apache 2.0 |
| uv 0.13.6 | GPU 서버 Python 가상 환경·패키지 설치 | Apache 2.0 · MIT |
| FastAPI 0.115.6 · Uvicorn 0.34.0 | 타깃 서버 앱 | MIT · BSD-3-Clause |
| cryptography 44.0.0 | 타깃 서버 시연 인증서 생성 | Apache 2.0 · BSD |
| nginx 1.27.4 (Docker 이미지) | 타깃 서버 TLS 프록시 | BSD-2-Clause |
| CoreDNS 1.11.3 (Docker 이미지) | 타깃 서버 시연 DNS | Apache 2.0 |
| Python 3.12 slim (Docker 이미지) | 타깃 서버 실행 환경 | PSF |
| curl 8.11.1 (Docker 이미지) | 타깃 서버 응답 확인(`demo.sh check`) | curl 라이선스(MIT 계열) |
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
