#!/usr/bin/env bash
# 피공격 서버 조작 스크립트. target/ 안에서 실행한다.
#
#   ./demo.sh up                 띄우기 (.env가 없으면 .env.example을 복사)
#   ./demo.sh down               내리기 (상태 볼륨은 남김. 지우려면 down -v)
#   ./demo.sh status             결함별 상태 보기
#   ./demo.sh fix 16 8 18        결함 고치기 (재점검 시연)
#   ./demo.sh break 16 | all     결함 되살리기
#   ./demo.sh fix all            모두 고치기
#   ./demo.sh verify <값>        FR-01 소유권 TXT 레코드 값 넣기
#   ./demo.sh ca                 시연 CA 인증서 출력 (점검 엔진이 믿게 할 때)
#   ./demo.sh check              주요 주소를 한 번씩 불러 상태 확인
#   ./demo.sh dns-on / dns-off   이 PC(리눅스)가 *.도메인을 시연 DNS로 찾게 하기 (sudo)
#   ./demo.sh preset demo        기본 시연 프로필: #16 #8 #18만 결함, 나머지 고침
#   ./demo.sh preset all         결함 21개 모두 켜기 (점검 엔진 검증용)
#   ./demo.sh test-server on|off 새 테스트 서버(test.) 열기·닫기 (감시 시연)
set -euo pipefail
cd "$(dirname "$0")"

FAULTS=(6 8 9 10 11 12 13 14 16 17 18 19 20 21 23 25 27 28 30 31 32)
DEMO_PRESET=(16 8 18)  # jobnest/config.py의 DEMO_PRESET과 같게 둔다

ensure_env() {
  [ -f .env ] || { cp .env.example .env; echo "[demo] .env.example → .env 복사"; }
}

# BSD·GNU sed 차이를 피하려고 awk로 고친다.
set_var() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  if grep -q "^${key}=" .env; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' .env >"$tmp"
  else
    cat .env >"$tmp"; echo "${key}=${val}" >>"$tmp"
  fi
  mv "$tmp" .env
}

get_var() { grep "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }

apply() {
  # app·init·browse가 같은 이미지(a2d-target-app:local)를 쓴다. up --build는 셋을 동시에 빌드하다
  # "image already exists"로 실패하므로, app 이미지만 먼저 한 번 빌드하고 나머지는 그 이미지를 쓴다.
  docker compose build app
  docker compose up -d
  # init(영역 파일·인증서)이 끝난 뒤 nginx가 새 인증서를 읽게 한다.
  local i
  for i in $(seq 1 30); do
    [ "$(docker compose ps -a --format '{{.State}}' init)" = "exited" ] && break
    sleep 1
  done
  [ "$(docker compose ps -a --format '{{.ExitCode}}' init)" = "0" ] || { docker compose logs init; exit 1; }
  docker compose exec -T proxy nginx -s reload >/dev/null 2>&1 || true
}

toggle() {
  local val="$1"; shift
  [ $# -gt 0 ] || { echo "번호를 적어 주세요. 예: ./demo.sh fix 16 8 18"; exit 1; }
  ensure_env
  local nums=("$@")
  [ "$1" = "all" ] && nums=("${FAULTS[@]}")
  for n in "${nums[@]}"; do
    [[ " ${FAULTS[*]} " == *" $n "* ]] || { echo "[demo] #$n 은(는) 심은 결함이 아닙니다"; exit 1; }
    set_var "FIX_$n" "$val"
  done
  apply
  echo "[demo] $( [ "$val" = 1 ] && echo 고침 || echo 되살림 ): ${nums[*]}"
}

preset() {
  ensure_env
  case "${1:-}" in
    demo) for n in "${FAULTS[@]}"; do
            if [[ " ${DEMO_PRESET[*]} " == *" $n "* ]]; then set_var "FIX_$n" 0; else set_var "FIX_$n" 1; fi
          done;;
    all)  for n in "${FAULTS[@]}"; do set_var "FIX_$n" 0; done;;
    *)    echo "preset demo | preset all"; exit 1;;
  esac
  set_var SHOW_TEST_SERVER 0
  apply
  echo "[demo] 프리셋 $1 적용"
}

status() {
  ensure_env
  echo "도메인: $(get_var DEMO_DOMAIN)"
  docker compose --progress quiet run --rm --no-deps -T init python - <<'PY'
from jobnest import config as c
for n, desc in c.FAULTS.items():
    print(f"  #{n:<3} {'고침' if c.fixed(n) else '결함'}  {desc}")
print(f"  테스트 서버 test.{c.DOMAIN}: {'열림' if c.test_server() else '닫힘'}")
PY
}

check() {
  ensure_env
  local d; d="$(get_var DEMO_DOMAIN)"
  docker run --rm --network a2d-demo --dns "$(get_var DNS_IP)" curlimages/curl:8.11.1 sh -c "
    for u in https://$d/ https://www.$d/.env https://www.$d/backup.zip https://api.$d/api/v1/applicants/1 \
             https://www.$d/internal/reports/export https://api.$d/swagger https://admin.$d/ http://www.$d/; do
      printf '%-48s ' \"\$u\"; curl -sk -o /dev/null -w '%{http_code}\n' \"\$u\"
    done"
}

# 리눅스(systemd-resolved): *.DEMO_DOMAIN 질의만 시연 DNS로 보낸다. 다시 띄우면 다시 실행한다.
bridge() { echo "br-$(docker network inspect a2d-demo -f '{{.Id}}' | cut -c1-12)"; }

dns_on() {
  ensure_env
  command -v resolvectl >/dev/null || { echo "resolvectl이 없습니다. README의 /etc/hosts 방법을 쓰세요."; exit 1; }
  local br d; br="$(bridge)"; d="$(get_var DEMO_DOMAIN)"
  sudo resolvectl dns "$br" "$(get_var DNS_IP)"
  sudo resolvectl domain "$br" "~$d"
  sudo resolvectl flush-caches
  echo "[demo] *.$d → 시연 DNS $(get_var DNS_IP) ($br). 끄기: ./demo.sh dns-off"
}

dns_off() { sudo resolvectl revert "$(bridge)"; sudo resolvectl flush-caches; echo "[demo] 시연 DNS 연결 해제"; }

case "${1:-}" in
  preset)  shift; preset "${1:-}";;
  test-server) shift; ensure_env
           case "${1:-}" in on) set_var SHOW_TEST_SERVER 1;; off) set_var SHOW_TEST_SERVER 0;; *) echo "test-server on|off"; exit 1;; esac
           apply; echo "[demo] 테스트 서버 test.$(get_var DEMO_DOMAIN): $1";;
  dns-on)  dns_on;;
  dns-off) dns_off;;
  up)     ensure_env; apply
          docker pull -q curlimages/curl:8.11.1 >/dev/null || true  # check를 오프라인에서도 쓰려고 미리 받는다
          echo "[demo] 떴습니다. 도메인 $(get_var DEMO_DOMAIN), DNS 127.0.0.1:$(get_var DNS_PORT), HTTPS 127.0.0.1:$(get_var HTTPS_PORT)";;
  down)   shift; docker compose down "$@";;
  status) status;;
  fix)    shift; toggle 1 "$@";;
  break)  shift; toggle 0 "$@";;
  verify) shift; ensure_env; set_var A2D_VERIFY_VALUE "${1:?값을 적어 주세요}"; apply
          echo "[demo] $(get_var A2D_VERIFY_NAME).$(get_var DEMO_DOMAIN) TXT \"$1\"";;
  ca)     docker compose exec -T proxy cat /state/tls/ca.crt;;
  check)  check;;
  logs)   shift; docker compose logs -f "$@";;
  *)      sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//';;
esac
