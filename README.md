<p align="center"><img src="brand/logo/png/a2d-logo.png" alt="A2D" width="320"></p>

# A2D (Attack to Defense)

보안팀이 없는 조직을 위한 외부 노출 점검 서비스. 공격자가 약한 고리를 찾는 방법으로 매일 침입 없이 점검하고, 점수 하나와 "오늘 할 일 3가지"를 알려준다. 코디세이 AI 해커톤 2026 출품작.

## 저장소 구조

서비스, 모델 배포, 시연용 피공격 서버를 한 저장소에 둔다(모노레포).

| 경로 | 내용 | 담당 |
| --- | --- | --- |
| [apps/web/](apps/web/README.md) | A2D 프론트엔드: 등록·대시보드·조치 가이드·기록 4개 화면 | 정인호 |
| [apps/api/](apps/api/README.md) | A2D 백엔드: 소유권 확인, 자산 발견·점검 엔진, 위험 점수, Attack·Defense 에이전트 | 김성원, 김강현(에이전트) |
| [model/](model/README.md) | AI 모델 배포 스크립트: GPU 서버에서 Qwen3-8B를 vLLM으로 서빙 | 김성원 |
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
| [docs/research/A2D_도메인선정_근거검증_사례28건.md](docs/research/A2D_도메인선정_근거검증_사례28건.md) | 채용·인재 매칭 플랫폼을 주 타깃으로 선정한 근거와 사고 사례 28건 |
| [docs/research/A2D_채용플랫폼_필요점검리스트.md](docs/research/A2D_채용플랫폼_필요점검리스트.md) | 채용 플랫폼 우선 점검 항목, 안전 조건, 구현 순서 |

## 브랜드

- [brand/logo/](brand/logo/README.md): 확정 로고(후보 7 "한붓 라인") SVG·PNG와 사용 규칙
- [brand/logo-candidates/](brand/logo-candidates/README.md): 로고 후보 7종 SVG와 콘셉트

## 실행 방법

각 디렉터리의 README에 적는다. 기술 스택이 정해지면 여기에 전체 시연 환경을 띄우는 순서를 정리한다.

## 외부 자원

사용한 외부 모델·오픈소스는 모두 이 표에 적는다. 새 라이브러리나 모델을 추가하는 PR은 이 표에도 한 줄을 더한다.

| 자원 | 용도 | 라이선스 |
| --- | --- | --- |
| Qwen3-8B | Attack·Defense 에이전트 LLM | Apache 2.0 |
| vLLM | 모델 서빙 (OpenAI 호환 엔드포인트) | Apache 2.0 |
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
