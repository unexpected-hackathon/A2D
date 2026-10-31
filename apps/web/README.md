# apps/web · A2D 프론트엔드

담당: 정인호 · 커밋 scope: `web`

IT 담당자가 쓰는 A2D 화면. 백엔드(`apps/api`)의 API만 호출한다.

## 화면 (PRD 5장)

| 화면 | 내용 | 관련 기능 |
| --- | --- | --- |
| 1. 등록 | 도메인 입력, TXT 레코드 값, 소유권 확인 상태, 점검 범위·안전 원칙 안내 | FR-01 |
| 2. 대시보드 | 조직 점수와 등급, 오늘 할 일 3가지, 자산 목록, 점검 진행 상태, 새 노출 알림 | FR-02~06, FR-09, FR-14, FR-15 |
| 3. 조치 가이드 | 항목별 쉬운 설명·예상 피해·조치 방법·예상 시간, 근거 검증 표시, 접힌 기술 근거, 질문 입력란 | FR-07, FR-08, FR-11, FR-12 |
| 4. 기록 | 점수 추이 그래프, 점검별 변화, 감사 기록, 내보내기 | FR-10, FR-13, FR-16 |

세부 요구사항은 [docs/A2D_PRD.md](../../docs/A2D_PRD.md)를 따른다.

## 기술 스택

React 19 + TypeScript + Vite 8, 디자인 시스템은 [SEED](https://seed-design.io)(당근, Apache-2.0).

- SEED 컴포넌트는 CLI로 `seed-design/`에 복사해 두고 `seed-design/ui/...`로 불러온다. 추가: `npx @seed-design/cli@latest add ui:<이름>`
- SEED 기본 브랜드 색(당근 주황)은 `src/theme/brand.css`에서 A2D 청록으로 덮어쓴다. 당근 로고·캐릭터·매너온도 컴포넌트는 쓰지 않는다(SEED NOTICE).
- 등급·상태의 색과 글자는 `src/theme/severity.ts` 한 곳에서만 정한다.

## 폴더

| 경로 | 내용 |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | 앱 시작, 주소 → 화면 연결 |
| `src/theme/` | 브랜드 색 덮어쓰기, 전역 스타일·모션, 등급 색 |
| `src/api/` | `client.ts`(모든 요청이 지나는 곳), `endpoints.ts`(API 21개), `types.ts`(응답 모양) |
| `src/api/mock/` | 백엔드 없이 개발할 때 쓰는 가짜 응답(시연 프로필 #16 · #8 · #18) |
| `src/hooks/` | 데이터 불러오기(`useApi`), 2초 폴링(`usePolling`), 점검 진행 상태 공유(`useScan`) |
| `src/layout/` | 공통 틀(왼쪽 메뉴), 로그인·등록 틀, 화면 전환 모션 |
| `src/pages/`, `src/components/`, `src/panels/` | 화면, 화면 조각, 오른쪽 상세 패널(발견·자산) |
| `src/lib/` | 시각·시간 표기, 로그인 뒤 갈 곳 정하기 |
| `src/**/*.test.ts(x)`, `src/test/` | 테스트와 테스트 준비 파일 |

## 실행

```bash
cd apps/web
npm install
cp .env.example .env.local   # VITE_USE_MOCK=true면 가짜 응답, false면 apps/api로 보낸다
npm run dev                  # http://localhost:5173
```

- 실제 백엔드에 붙일 때는 `.env.local`의 `VITE_USE_MOCK=false`로 바꾼다. `/api` 요청은 개발 서버가 `http://localhost:8000`(환경 변수 `A2D_API_TARGET`)으로 넘긴다.
- 가짜 응답 시연 흐름: 대시보드에서 "재점검"을 누를 때마다 오늘 할 일 1번을 고친 것으로 보고 안전 점수가 20 → 30 → 49 → 100으로 오른다. 그다음 재점검에서는 새 테스트 서버(`test.`)가 열려 새 노출 알림이 뜬다. 상태는 메모리에만 있어 새로고침하면 처음으로 돌아간다.
- 가짜 응답 계정: `admin@jobnest.test` / `a2d-demo`
- API 확인 화면: http://localhost:5173/dev/api (개발 모드에서만 열림)
- 검사: `npm test`(Vitest), `npm run build`(타입 검사 + 빌드), `npm run lint`
