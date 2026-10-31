#!/usr/bin/env bash
# A2D 시연 환경을 한 번에 띄우고 내리는 스크립트. 저장소 루트에서 실행한다.
#
#   ./a2d-demo.sh up              피공격 서버(target) → 백엔드(apps/api, Docker) → 화면(apps/web) 순서로 띄우기
#   ./a2d-demo.sh down            화면·백엔드·피공격 서버 내리기 (점검 기록은 남김)
#   ./a2d-demo.sh status          세 부분의 상태와 LLM 연결 보기
#   ./a2d-demo.sh reset           새 테이크 준비: 결함을 시연 프로필로 되돌리고 점검 기록을 지운다
#   ./a2d-demo.sh verify [값]     등록 화면의 TXT 값을 시연 DNS에 넣기 (값을 비우면 백엔드에서 읽어 온다)
#   ./a2d-demo.sh logs api|web|target
#
#   피공격 서버 조작은 target/demo.sh로 그대로 넘긴다:
#   ./a2d-demo.sh fix 16 8 18 | break 16 | preset demo | test-server on | check | dns-on | dns-off
#
# 환경 변수: A2D_WEB_PORT (화면 포트, 기본 4173)
# LLM(GPU 서버 vLLM) 터널은 VPN과 SSH가 필요해 이 스크립트가 열지 않는다. status가 안내한다.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
RUN="$ROOT/.demo"                 # 화면 프로세스 번호와 로그 (커밋하지 않는다)
API_ENV="$ROOT/apps/api/.env"
WEB_PORT="${A2D_WEB_PORT:-4173}"
WEB_URL="http://localhost:$WEB_PORT"

say()  { printf '[a2d] %s\n' "$*"; }
die()  { printf '[a2d] %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 이(가) 필요합니다. $2"; }

# KEY=VALUE 파일에서 값 하나를 읽는다. 따옴표는 벗긴다(apps/api/a2d/config.py와 같게).
env_get() {
  [ -f "$1" ] || return 0
  grep -E "^$2=" "$1" | head -1 | cut -d= -f2- | sed -e "s/^[\"']//" -e "s/[\"']\$//" || true
}
api_get()    { env_get "$API_ENV" "$1"; }
target_get() { env_get "$ROOT/target/.env" "$1"; }
api_port()   { local p; p="$(api_get A2D_API_PORT)"; echo "${p:-8000}"; }
api_url()    { echo "http://127.0.0.1:$(api_port)/api/v1"; }
# 터미널에서 백엔드를 부를 때 붙이는 Origin. A2D_WEB_ORIGIN의 첫 값은 항상 허용된다.
api_origin() { local o; o="$(api_get A2D_WEB_ORIGIN)"; o="${o%%,*}"; echo "${o:-http://localhost:5173}"; }

target() { "$ROOT/target/demo.sh" "$@"; }
api_compose() { (cd "$ROOT/apps/api" && docker compose "$@"); }

# ------------------------------------------------------------------ 준비 검사

preflight() {
  need docker "Docker Desktop 또는 Docker Engine을 설치하세요."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2(docker compose)가 필요합니다."
  docker info >/dev/null 2>&1 || die "Docker가 실행 중이 아닙니다."
  need node "Node.js 22 이상을 설치하세요."
  need npm "Node.js와 함께 설치됩니다."
  need curl "curl을 설치하세요."

  if [ ! -f "$API_ENV" ]; then
    cp "$ROOT/apps/api/.env.example" "$API_ENV"
    die "apps/api/.env를 만들었습니다. A2D_ADMIN_EMAIL·A2D_ADMIN_PASSWORD를 채우고 다시 실행하세요."
  fi
  [ -n "$(api_get A2D_ADMIN_EMAIL)" ] && [ -n "$(api_get A2D_ADMIN_PASSWORD)" ] \
    || die "apps/api/.env의 A2D_ADMIN_EMAIL·A2D_ADMIN_PASSWORD를 채우세요."

  # 화면 주소가 A2D_WEB_ORIGIN에 없으면 로그인부터 403 FORBIDDEN_ORIGIN이다. 띄우기 전에 막는다.
  local origins
  origins="$(api_get A2D_WEB_ORIGIN)"
  origins="${origins:-http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173}"
  case ",$origins," in
    *",$WEB_URL,"*) ;;
    *) die "화면 주소 $WEB_URL 이(가) apps/api/.env의 A2D_WEB_ORIGIN에 없습니다. 넣고 다시 실행하세요." ;;
  esac

  if [ "$(api_get A2D_VERIFY_MODE)" = "trust" ]; then
    say "주의: A2D_VERIFY_MODE=trust라 TXT 조회 없이 소유권 확인이 통과합니다. 시연에서는 dns로 두세요."
  fi
}

# ------------------------------------------------------------------ 화면 (apps/web)

web_pid() {
  local pid
  [ -f "$RUN/web.pid" ] || return 1
  pid="$(cat "$RUN/web.pid")"
  kill -0 "$pid" 2>/dev/null && echo "$pid"
}

web_up() {
  if web_pid >/dev/null; then
    say "화면은 이미 떠 있습니다: $WEB_URL"
    return
  fi
  if curl -s -o /dev/null --max-time 2 "$WEB_URL/"; then
    die "$WEB_PORT 포트를 다른 프로그램이 쓰고 있습니다. A2D_WEB_PORT=<다른 포트>로 실행하고 그 주소를 A2D_WEB_ORIGIN에 넣으세요."
  fi
  mkdir -p "$RUN"
  cd "$ROOT/apps/web"
  [ -d node_modules ] || { say "화면 의존성 설치 (npm ci)"; npm ci --no-audit --no-fund; }
  # VITE_USE_MOCK은 빌드할 때 화면에 들어간다. 가짜 응답이 아니라 apps/api를 부르게 false로 빌드한다.
  say "화면 빌드 (실제 백엔드 연결)"
  VITE_USE_MOCK=false npm run build >"$RUN/web-build.log" 2>&1 \
    || { tail -n 30 "$RUN/web-build.log"; die "화면 빌드 실패. 전체 로그: .demo/web-build.log"; }
  # preview도 vite.config.ts의 /api 프록시를 쓴다. 같은 출처라 세션 쿠키가 그대로 오간다.
  A2D_API_TARGET="http://127.0.0.1:$(api_port)" nohup ./node_modules/.bin/vite preview \
    --port "$WEB_PORT" --strictPort >"$RUN/web.log" 2>&1 &
  echo $! >"$RUN/web.pid"
  cd "$ROOT"
  local i
  for i in $(seq 1 30); do
    curl -s -o /dev/null --max-time 2 "$WEB_URL/" && return
    web_pid >/dev/null || break
    sleep 1
  done
  tail -n 20 "$RUN/web.log"
  die "화면이 뜨지 않았습니다. 로그: .demo/web.log"
}

web_down() {
  local pid
  if pid="$(web_pid)"; then
    kill "$pid" 2>/dev/null || true
    say "화면 내림"
  fi
  rm -f "$RUN/web.pid"
}

# ------------------------------------------------------------------ 백엔드 (apps/api)

api_up() {
  say "백엔드 띄우기 (처음에는 이미지 빌드로 몇 분 걸립니다)"
  api_compose up -d --build
  wait_api
}

wait_api() {
  local i
  for i in $(seq 1 90); do
    curl -s -o /dev/null --max-time 2 "$(api_url)/health" && return
    sleep 2
  done
  api_compose logs --tail 50 api
  die "백엔드가 응답하지 않습니다($(api_url)/health)."
}

# ------------------------------------------------------------------ LLM 안내

llm_report() {
  local health llm base
  health="$(curl -s --max-time 5 "$(api_url)/health" || true)"
  case "$health" in
    *'"llm":"up"'*) llm=up ;;
    *'"llm":"down"'*) llm=down ;;
    *) llm="알 수 없음 (백엔드 응답 없음)" ;;
  esac
  base="$(api_get A2D_LLM_BASE_URL)"
  say "LLM: $llm${base:+ ($base, 모델 $(api_get A2D_LLM_MODEL))}"
  [ "$llm" = up ] && return
  if [ -z "$base" ]; then
    say "  A2D_LLM_BASE_URL이 비어 있어 조치 가이드는 기본 가이드로, 질문하기는 503으로 동작합니다."
  fi
  # 백엔드는 컨테이너 안에서 터널에 닿아야 한다. OS마다 주소가 다르다(model/README.md "백엔드에서 부르기").
  local url bind gateway
  if [ "$(uname -s)" = Linux ]; then
    gateway="$(docker network inspect a2d-demo -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)"
    case "$gateway" in ""|*"<no value>"*) gateway=10.253.53.1 ;; esac
    url="http://$gateway:18000/v1"; bind="TUNNEL_BIND=$gateway"
  else
    url="http://host.docker.internal:18000/v1"; bind="TUNNEL_BIND는 기본값(127.0.0.1)"
  fi
  say "  LLM을 붙이려면:"
  say "   1) VPN 연결 뒤 다른 터미널에서 model/llm.sh tunnel  (model/.env: $bind)"
  say "   2) apps/api/.env: A2D_LLM_BASE_URL=$url, A2D_LLM_API_KEY=<GPU 서버 VLLM_API_KEY>, A2D_LLM_MODEL=qwen3-8b"
  # up을 다시 하면 preset demo로 고친 결함이 되살아나므로 백엔드만 다시 띄운다
  say "   3) (cd apps/api && docker compose up -d) 로 백엔드만 다시 띄운다"
}

# ------------------------------------------------------------------ 소유권 TXT

# 값을 주지 않으면 백엔드에 로그인해 시연 도메인의 TXT 값을 읽는다.
txt_from_api() {
  need python3 "아니면 값을 직접 주세요: ./a2d-demo.sh verify a2d-verify=<값>"
  local jar domain
  jar="$(mktemp)"
  domain="$(target_get DEMO_DOMAIN)"
  # 로그인 요청에는 허용된 화면 주소를 Origin으로 붙여야 한다(API 명세 3장).
  # A2D_WEB_PORT를 up 때와 다르게 줘도 되도록 화면 포트가 아니라 A2D_WEB_ORIGIN에서 고른다.
  A2D_EMAIL="$(api_get A2D_ADMIN_EMAIL)" A2D_PASSWORD="$(api_get A2D_ADMIN_PASSWORD)" python3 -c '
import json, os
print(json.dumps({"email": os.environ["A2D_EMAIL"], "password": os.environ["A2D_PASSWORD"]}))' \
    | curl -s -f -o /dev/null -c "$jar" -H "Origin: $(api_origin)" -H "Content-Type: application/json" \
        --data-binary @- "$(api_url)/auth/login" \
    || { rm -f "$jar"; die "백엔드 로그인 실패. apps/api/.env의 계정과 A2D_WEB_ORIGIN을 확인하세요."; }
  curl -s -f -b "$jar" "$(api_url)/domains" | DOMAIN="$domain" python3 -c '
import json, os, sys
items = json.load(sys.stdin)["items"]
match = [d for d in items if d["domain"] == os.environ["DOMAIN"]]
if match:
    print(match[0]["txt_record"]["value"])' || true
  rm -f "$jar"
}

verify() {
  local value="${1:-}"
  if [ -z "$value" ]; then
    value="$(txt_from_api)"
    [ -n "$value" ] || die "백엔드에 $(target_get DEMO_DOMAIN) 등록이 없습니다. 화면에서 도메인을 먼저 등록하세요."
  fi
  target verify "$value"
  say "화면에서 \"확인\"을 누르세요."
}

# ------------------------------------------------------------------ 명령

up() {
  preflight
  say "피공격 서버 띄우기 (target, 시연 프로필 #16 #8 #18)"
  target up
  target preset demo
  api_up
  web_up
  status_line
  say "화면: $WEB_URL  (계정은 apps/api/.env의 A2D_ADMIN_EMAIL)"
  say "등록 화면에서 도메인 $(target_get DEMO_DOMAIN)을 넣은 뒤 ./a2d-demo.sh verify"
}

down() {
  web_down
  [ -f "$API_ENV" ] && api_compose down
  target down
}

reset() {
  preflight
  say "새 테이크 준비: 결함을 시연 프로필로, 점검 기록·등록 도메인을 지웁니다"
  target preset demo
  api_compose down -v
  api_compose up -d
  wait_api
  web_up
  say "도메인을 다시 등록해야 합니다. TXT 값이 새로 나오므로 등록 뒤 ./a2d-demo.sh verify"
}

status_line() {
  local engine
  engine="$(api_get A2D_ENGINE)"
  engine="${engine:-fixture}"
  if [ "$engine" = fixture ]; then
    say "점검 엔진: fixture (시연 시나리오를 돌려주는 가짜 엔진. 피공격 서버에 점검 요청을 보내지 않음)"
  else
    say "점검 엔진: $engine"
  fi
  llm_report
}

status() {
  say "피공격 서버:"
  (cd "$ROOT/target" && docker compose ps --format '  {{.Service}}  {{.State}}') || true
  if curl -s -o /dev/null --max-time 2 "$(api_url)/health"; then
    say "백엔드: 동작 중 ($(api_url))"
    status_line
  else
    say "백엔드: 꺼짐"
  fi
  if web_pid >/dev/null; then say "화면: 동작 중 ($WEB_URL)"; else say "화면: 꺼짐"; fi
}

logs() {
  case "${1:-}" in
    api)    api_compose logs -f api ;;
    web)    tail -f "$RUN/web.log" ;;
    target) shift; target logs "$@" ;;
    *)      die "logs api | web | target" ;;
  esac
}

case "${1:-}" in
  up)      up ;;
  down)    down ;;
  status)  status ;;
  reset)   reset ;;
  verify)  shift; verify "${1:-}" ;;
  logs)    shift; logs "$@" ;;
  fix|break|preset|test-server|check|dns-on|dns-off) target "$@" ;;
  *)       sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
