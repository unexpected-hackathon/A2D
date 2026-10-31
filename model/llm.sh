#!/usr/bin/env bash
# A2D LLM 서빙 스크립트. Qwen3-8B를 vLLM으로 띄운다. model/ 안의 파일을 기준으로 동작한다.
#
# GPU 서버에서
#   ./llm.sh deploy        한 번에: setup → download → up → check (이미 끝난 단계는 건너뛴다)
#   ./llm.sh preflight     서버 환경 점검 (외부 인터넷, sudo, Docker, Python, GPU, 디스크)
#   ./llm.sh setup         uv와 Python 가상 환경을 만들고 vLLM 설치 (sudo 불필요)
#   ./llm.sh download      모델 가중치를 MODEL_DIR에 내려받기 (약 16GB)
#   ./llm.sh up            vLLM을 백그라운드로 띄우고 준비될 때까지 기다리기
#   ./llm.sh down          vLLM 내리기
#   ./llm.sh status        프로세스, /health, GPU 메모리 확인
#   ./llm.sh logs          vLLM 로그 따라 보기
#   ./llm.sh check [옵션]  모델 목록·한국어 답변·도구 호출 확인 (check.py에 옵션 전달)
#
# 내 PC에서
#   ./llm.sh tunnel        SSH 터널 열기: 내 PC 127.0.0.1:LOCAL_PORT → GPU 서버 vLLM
#   ./llm.sh check --local 터널을 거쳐 확인
set -euo pipefail
cd "$(dirname "$0")"

VENV=.venv
RUN_DIR=run
LOG_DIR=logs
PID_FILE="$RUN_DIR/vllm.pid"
LOG_FILE="$LOG_DIR/vllm.log"

log() { printf '[llm] %s\n' "$*"; }
die() { printf '[llm] 오류: %s\n' "$*" >&2; exit 1; }

load_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    log ".env.example → .env 복사"
  fi
  # .env.example을 기본값으로 읽고 .env로 덮어쓴다. .env에는 바꿀 키만 적어도 된다
  # (내 PC에는 GPU_SSH_*와 VLLM_API_KEY만, 예전 .env에 없는 새 키는 기본값).
  set -a
  # shellcheck disable=SC1091
  . ./.env.example
  # shellcheck disable=SC1091
  . ./.env
  set +a
}

# BSD·GNU sed 차이를 피하려고 awk로 고친다 (target/demo.sh와 같은 방식).
set_var() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$val" 'BEGIN{done=0} $0 ~ "^"k"=" {print k"="v; done=1; next} {print} END{if(!done) print k"="v}' .env >"$tmp"
  cat "$tmp" >.env
  rm -f "$tmp"
}

pid_alive() {
  [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

health_ok() {
  curl -fsS -m 3 "http://$VLLM_HOST:$VLLM_PORT/health" >/dev/null 2>&1
}

python_bin() {
  if [ -x "$VENV/bin/python" ]; then echo "$VENV/bin/python"; else command -v python3 || die "python3가 없다"; fi
}

# ── GPU 서버 ────────────────────────────────────────────────────────

cmd_preflight() {
  local ok="  [O]" no="  [X]" warn="  [!]"
  log "서버 환경 점검"

  echo "외부 인터넷 (모델·패키지 내려받기에 필요)"
  for url in https://huggingface.co https://pypi.org https://astral.sh; do
    if curl -fsSI -m 8 "$url" >/dev/null 2>&1; then echo "$ok $url"; else echo "$no $url  → README '외부 인터넷이 막혀 있을 때' 참고"; fi
  done

  echo "권한·도구"
  if sudo -n true 2>/dev/null; then echo "$ok sudo (비밀번호 없이 가능)"; else echo "$warn sudo 없음 (괜찮다. 스크립트는 sudo를 쓰지 않는다)"; fi
  if command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1; then echo "$ok docker"; else echo "$warn docker 사용 불가 (괜찮다. venv로 설치한다)"; fi
  if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then echo "$ok uv"; else echo "$warn uv 없음 (setup이 ~/.local/bin에 설치한다)"; fi
  if command -v python3 >/dev/null 2>&1; then echo "$ok $(python3 --version 2>&1)"; else echo "$warn python3 없음 (uv가 Python $PYTHON_VERSION을 받는다)"; fi
  for t in tmux curl gcc nvcc; do
    if command -v "$t" >/dev/null 2>&1; then echo "$ok $t"; else echo "$warn $t 없음"; fi
  done

  echo "GPU"
  local gpu
  if gpu="$(nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total --format=csv,noheader 2>&1)"; then
    echo "$ok $gpu"
    nvidia-smi | awk '/CUDA Version/ {print "  드라이버가 지원하는 CUDA " $(NF-1)}' || true
    echo "  vLLM $VLLM_VERSION은 CUDA 13.0 런타임을 쓴다. 드라이버가 CUDA 13.0 이상을 지원해야 한다."
  else
    echo "$no GPU를 찾지 못했다 ($(echo "$gpu" | head -n 1 | cut -c1-80)) → nvidia-smi 결과와 서버명을 운영진에게 전달"
  fi

  echo "디스크 (가중치 약 16GB + 가상 환경 약 10GB, 여유 40GB 이상 권장)"
  df -h "$HOME" | sed 's/^/  /'

  echo "포트"
  if health_ok; then echo "$ok $VLLM_HOST:$VLLM_PORT에서 vLLM이 이미 돌고 있다"
  elif (exec 3<>"/dev/tcp/$VLLM_HOST/$VLLM_PORT") 2>/dev/null; then echo "$no $VLLM_PORT 포트를 다른 프로세스가 쓰고 있다 → .env의 VLLM_PORT를 바꾼다"
  else echo "$ok $VLLM_PORT 포트 비어 있음"; fi
}

ensure_uv() {
  local want="${UV_VERSION:?}" cand
  for cand in "$(command -v uv 2>/dev/null || true)" "$HOME/.local/bin/uv"; do
    if [ -n "$cand" ] && [ -x "$cand" ] && [ "$("$cand" --version 2>/dev/null | awk '{print $2}')" = "$want" ]; then
      UV="$cand"; return
    fi
  done
  log "uv $want 설치 (~/.local/bin, sudo 불필요)"
  curl -LsSf "https://astral.sh/uv/$want/install.sh" | env UV_NO_MODIFY_PATH=1 sh
  UV="$HOME/.local/bin/uv"
}

# vLLM이 죽었을 때 원인 줄을 보여 준다. 진짜 원인은 EngineCore 쪽에 먼저 찍히고,
# 마지막 줄은 APIServer의 "Engine core initialization failed"뿐이라 tail만으로는 안 보인다.
show_failure() {
  echo "----- 원인으로 보이는 줄 (처음 나온 오류부터) -----"
  grep -n -E 'Error|Exception|error:|out of memory|No available memory|Traceback' "$LOG_FILE" \
    | grep -v -E 'Engine core initialization failed|^[0-9]+:\s+File ' | head -n 25 || true
  echo "----- 첫 EngineCore 오류가 난 위치 (패키지 파일만) -----"
  awk '/EngineCore.*Traceback/ {on=1} on && /File "/ {print} on && /EngineCore.*(Error|Exception):/ {exit}' "$LOG_FILE" \
    | sed -E 's/.*File "([^"]*site-packages\/)?([^"]*)", line ([0-9]+), in (.*)/  \2:\3 \4/' | tail -n 12 || true
  echo "----- 로그 마지막 10줄 -----"
  tail -n 10 "$LOG_FILE"
  echo "----- 전체 로그: $PWD/$LOG_FILE -----"
}

# Triton(torch 컴파일)이 실행 중에 gcc로 C 코드를 빌드하므로 Python 헤더(Python.h)가 있어야 한다.
venv_has_headers() {
  "$VENV/bin/python" -I -c 'import os, sys, sysconfig; sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_paths()["include"], "Python.h")) else 1)' 2>/dev/null
}

cmd_setup() {
  ensure_uv
  if [ -x "$VENV/bin/python" ] && ! venv_has_headers; then
    log "가상 환경의 Python에 헤더(Python.h)가 없다. uv가 관리하는 Python으로 다시 만든다"
    rm -rf "$VENV"
  fi
  if [ ! -x "$VENV/bin/python" ]; then
    # 시스템 Python에는 헤더(python3-dev)가 없을 수 있고, 서버 구성은 바꾸지 않는다.
    # uv가 관리하는 Python은 헤더를 포함해 사용자 홈(~/.local/share/uv)에 설치된다.
    log "Python $PYTHON_VERSION 가상 환경 만들기 ($VENV, uv 관리 Python)"
    "$UV" venv --python "$PYTHON_VERSION" --managed-python "$VENV"
  fi
  log "vLLM $VLLM_VERSION 설치 (torch·CUDA 런타임 포함, 몇 분 걸린다)"
  VIRTUAL_ENV="$PWD/$VENV" "$UV" pip install "vllm==$VLLM_VERSION"
  log "설치 확인"
  "$VENV/bin/python" - <<'EOF'
import torch, vllm
print(f"  vllm {vllm.__version__}, torch {torch.__version__}, CUDA 런타임 {torch.version.cuda}")
ok = torch.cuda.is_available()
print(f"  GPU 인식: {ok}" + (f" ({torch.cuda.get_device_name(0)})" if ok else ""))
raise SystemExit(0 if ok else 1)
EOF
  log "다음: ./llm.sh download"
}

cmd_download() {
  [ -x "$VENV/bin/hf" ] || die "hf 명령이 없다. 먼저 ./llm.sh setup"
  mkdir -p "$MODEL_DIR"
  log "$MODEL_ID@${MODEL_REVISION:0:12} → $MODEL_DIR"
  "$VENV/bin/hf" download "$MODEL_ID" --revision "$MODEL_REVISION" --local-dir "$MODEL_DIR"
  [ -f "$MODEL_DIR/config.json" ] || die "config.json이 없다. 내려받기가 끝나지 않았다"
  du -sh "$MODEL_DIR" | sed 's/^/  /'
  log "다음: ./llm.sh up"
}

cmd_up() {
  [ -x "$VENV/bin/vllm" ] || die "vllm이 없다. 먼저 ./llm.sh setup"
  [ -f "$MODEL_DIR/config.json" ] || die "$MODEL_DIR에 모델이 없다. 먼저 ./llm.sh download"
  if pid_alive; then log "이미 실행 중 (pid $(cat "$PID_FILE"))"; return; fi
  health_ok && die "$VLLM_PORT 포트에 다른 vLLM이 떠 있다. ./llm.sh status로 확인"

  if [ -z "${VLLM_API_KEY:-}" ]; then
    VLLM_API_KEY="a2d-$("$(python_bin)" -c 'import secrets; print(secrets.token_urlsafe(24))')"
    set_var VLLM_API_KEY "$VLLM_API_KEY"
    log "API 키를 새로 만들어 .env에 적었다 (백엔드 LLM_API_KEY에 같은 값을 넣는다)"
  fi
  export VLLM_API_KEY  # --api-key 대신 환경 변수로 넘겨 ps 출력에 키가 보이지 않게 한다

  local thinking="${ENABLE_THINKING:-false}"
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  [ -f "$LOG_FILE" ] && mv "$LOG_FILE" "$LOG_FILE.prev"

  log "vLLM 시작: $SERVED_MODEL_NAME, 문맥 $MAX_MODEL_LEN, GPU 메모리 $GPU_MEMORY_UTILIZATION, 생각 모드 $thinking"
  # vLLM은 실행 중에 ninja·gcc 같은 도구를 하위 프로세스로 부른다. 가상 환경을 활성화한 것처럼
  # .venv/bin을 PATH 앞에 둬야 의존성으로 설치된 ninja를 찾는다.
  export VIRTUAL_ENV="$PWD/$VENV" PATH="$PWD/$VENV/bin:$PATH"
  # setsid + nohup: SSH 접속을 끊어도 계속 돈다.
  setsid nohup "$VENV/bin/vllm" serve "$MODEL_DIR" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --host "$VLLM_HOST" --port "$VLLM_PORT" \
    --dtype bfloat16 \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --max-num-seqs "${MAX_NUM_SEQS:-8}" \
    --enable-auto-tool-choice --tool-call-parser hermes \
    --reasoning-parser qwen3 \
    --default-chat-template-kwargs "{\"enable_thinking\": $thinking}" \
    >"$LOG_FILE" 2>&1 </dev/null &
  echo $! >"$PID_FILE"

  log "준비될 때까지 기다린다 (첫 실행은 컴파일 때문에 3~10분). 로그: ./llm.sh logs"
  local waited=0
  until health_ok; do
    if ! pid_alive; then
      show_failure
      rm -f "$PID_FILE"
      die "vLLM이 종료됐다. README '문제 해결'을 본다"
    fi
    sleep 5; waited=$((waited + 5))
    [ $((waited % 30)) -eq 0 ] && log "  ${waited}초… $(tail -n 1 "$LOG_FILE" | cut -c1-120)"
    [ "$waited" -ge 1200 ] && die "20분이 지나도 준비되지 않았다. ./llm.sh logs로 확인"
  done
  log "준비 완료 (${waited}초): http://$VLLM_HOST:$VLLM_PORT/v1"
  log "다음: ./llm.sh check"
}

cmd_down() {
  if ! pid_alive; then rm -f "$PID_FILE"; log "실행 중이 아니다"; return; fi
  local pid; pid="$(cat "$PID_FILE")"
  log "vLLM 종료 (pid $pid)"
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid"
  for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid"; fi
  rm -f "$PID_FILE"
  log "종료됨"
}

cmd_status() {
  if pid_alive; then log "프로세스: 실행 중 (pid $(cat "$PID_FILE"))"; else log "프로세스: 없음"; fi
  if health_ok; then log "/health: 정상 (http://$VLLM_HOST:$VLLM_PORT)"; else log "/health: 응답 없음"; fi
  local gpu
  if gpu="$(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null)"; then
    log "GPU: $gpu"
  fi
}

cmd_logs() {
  [ -f "$LOG_FILE" ] || die "로그가 없다"
  tail -n 100 -f "$LOG_FILE"
}

# ── 내 PC ───────────────────────────────────────────────────────────

cmd_tunnel() {
  [ -n "${GPU_SSH_HOST:-}" ] && [ -n "${GPU_SSH_USER:-}" ] || die ".env에 GPU_SSH_HOST(서버 사설 IP)와 GPU_SSH_USER(계정)를 적는다. VPN이 연결돼 있어야 한다"
  local lport="${LOCAL_PORT:-8000}"
  log "터널: 127.0.0.1:$lport → $GPU_SSH_USER@$GPU_SSH_HOST:${GPU_SSH_PORT:-22} → 127.0.0.1:$VLLM_PORT"
  log "이 창을 열어 두는 동안만 연결된다. 끊으려면 Ctrl+C"
  log "백엔드: LLM_BASE_URL=http://127.0.0.1:$lport/v1"
  exec ssh -N \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
    -L "127.0.0.1:$lport:127.0.0.1:$VLLM_PORT" \
    -p "${GPU_SSH_PORT:-22}" "$GPU_SSH_USER@$GPU_SSH_HOST"
}

cmd_check() {
  local base="http://$VLLM_HOST:$VLLM_PORT/v1" args=()
  for a in "$@"; do
    if [ "$a" = "--local" ]; then base="http://127.0.0.1:${LOCAL_PORT:-8000}/v1"; else args+=("$a"); fi
  done
  [ -n "${VLLM_API_KEY:-}" ] || die ".env의 VLLM_API_KEY가 비어 있다 (GPU 서버 .env의 값을 복사한다)"
  LLM_BASE_URL="$base" LLM_API_KEY="$VLLM_API_KEY" LLM_MODEL="$SERVED_MODEL_NAME" \
    "$(python_bin)" check.py ${args[@]+"${args[@]}"}
}

# GPU 서버에서 처음부터 확인까지 한 번에 한다. 중간에 실패하면 거기서 멈추고, 다시 실행하면 끝난 단계는 건너뛴다.
cmd_deploy() {
  local evidence="$LOG_DIR/evidence"
  log "[1/4] 설치"
  if [ -x "$VENV/bin/vllm" ] && venv_has_headers \
    && [ "$("$VENV/bin/python" -c 'import vllm; print(vllm.__version__)' 2>/dev/null)" = "$VLLM_VERSION" ]; then
    log "  vLLM $VLLM_VERSION 이미 설치됨. 건너뛴다"
  else
    cmd_setup
  fi
  log "[2/4] 모델 내려받기 (이미 받은 파일은 건너뛴다)"
  cmd_download
  log "[3/4] 실행"
  cmd_up
  log "[4/4] 확인 (결과 저장: $evidence)"
  cmd_check --thinking --save "$evidence"
  log "끝. 내 PC에서 ./llm.sh tunnel → ./llm.sh check --local"
}

main() {
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    deploy|preflight|setup|download|up|down|status|logs|tunnel|check) load_env; "cmd_$cmd" "$@" ;;
    *) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 1 ;;
  esac
}

main "$@"
