#!/bin/zsh

# ============================================================================
# 1. 상수 및 경로 정의 (Magic Number 제거)
# ============================================================================
readonly AGENT_DIR="${0:A:h}"
readonly REPO_ROOT="${AGENT_DIR:h}"
readonly VENV_PYTHON="$AGENT_DIR/.venv/bin/python3"
readonly MAX_LOG_SIZE=$((10 * 1024 * 1024)) # 10MB
readonly TIMEOUT_LIMIT=300                 # 5분 타임아웃

export PATH="$HOME/.rbenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

LOG_DIR="$AGENT_DIR/logs"
LOG_FILE="$LOG_DIR/trigger.log"
LOCK_DIR="$AGENT_DIR/blog_agent.lock"
ENV_FILE="$AGENT_DIR/.env"
PYTHON_SCRIPT="$AGENT_DIR/main.py"

mkdir -p "$LOG_DIR"

# 로그 레벨 확장
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO:  $1" >> "$LOG_FILE"; }
log_warn()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN:  $1" >> "$LOG_FILE"; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$LOG_FILE"; }

# ============================================================================
# 2. Cleanup 및 Trap 설정
# ============================================================================
cleanup() {
    rm -rf "$LOCK_DIR"
    log_info "Cleanup completed (PID: $$)"
}
trap cleanup EXIT INT TERM

# ============================================================================
# 3. 원자적 Lock 및 Stale Lock 방어
# ============================================================================
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    OLD_PID=$(cat "$LOCK_DIR/pid" 2>/dev/null)
    if [[ -n "$OLD_PID" ]] && ! kill -0 "$OLD_PID" 2>/dev/null; then
        log_warn "Removing stale lock (PID $OLD_PID is not running)."
        rm -rf "$LOCK_DIR" && mkdir "$LOCK_DIR"
    else
        # 이미 실행 중인 경우 조용히 종료하지 않고 기록을 남김
        log_info "Another instance already running (PID: ${OLD_PID:-unknown}). Exiting."
        exit 0
    fi
fi
echo $$ > "$LOCK_DIR/pid"

# ============================================================================
# 4. 환경 변수 로드 및 필수 값 검증
# ============================================================================
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        [[ "$key" =~ ^[[:space:]]*# || -z "$key" ]] && continue
        # Quote 처리 버그 수정
        value="${value%\"}"
        value="${value#\"}"
        export "$key"="$value"
    done < "$ENV_FILE"
    log_info "✅ Environment variables loaded safely."
else
    log_error ".env file missing." && exit 1
fi

# 필수 환경변수 사전 검증 (QA 철학 적용)
for var in CLAUDE_MODEL PERSONA_PATH GH_TOKEN; do
    if [[ -z "${(P)var}" ]]; then
        log_error "Required env var missing: $var"
        exit 1
    fi
done

# ============================================================================
# 5. 실행 환경 사전 검증
# ============================================================================
[[ ! -f "$VENV_PYTHON" ]] && { log_error "Venv Python missing at $VENV_PYTHON."; exit 1; }
[[ ! -f "$PYTHON_SCRIPT" ]] && { log_error "main.py missing at $PYTHON_SCRIPT"; exit 1; }

if ! gh auth status &>/dev/null; then
    log_error "GitHub CLI authentication failed."
    exit 1
fi

# ============================================================================
# 6. Git 동기화 (보안 강화)
# ============================================================================
cd "$REPO_ROOT" || exit 1
CURRENT_BRANCH=$(git branch --show-current)

log_info "--- Task Started (Branch: $CURRENT_BRANCH) ---"

# Credential 노출 방지 처리
if ! GIT_TERMINAL_PROMPT=0 git pull --rebase origin "$CURRENT_BRANCH" >> "$LOG_FILE" 2>&1; then
    log_error "Git pull failed. Credential or Conflict issue."
    exit 1
fi

# ============================================================================
# 7. 메인 로직 실행 (Timeout 및 Error Handling)
# ============================================================================
NEW_SIGNALS=$(gh issue list --label "to-blog" --state open --json number,comments --jq '.[] | select(.comments | length > 0) | .number' 2>> "$LOG_FILE" | tr '\n' ' ')

if [[ -n "${NEW_SIGNALS// /}" ]]; then
    log_info "🔔 Signal detected: Issue #$NEW_SIGNALS. Mode: PROCESS"
    # Timeout 추가하여 무한 대기 방지
    if ! timeout $TIMEOUT_LIMIT "$VENV_PYTHON" "$PYTHON_SCRIPT" --mode process >> "$LOG_FILE" 2>&1; then
        RET_CODE=$?
        (( RET_CODE == 124 )) && log_error "Python script timed out (Limit: ${TIMEOUT_LIMIT}s)." || log_error "Process failed (Code: $RET_CODE)"
        exit 1
    fi
else
    log_info "ℹ️ No signals. Mode: WATCHDOG"
    if ! timeout $TIMEOUT_LIMIT "$VENV_PYTHON" "$PYTHON_SCRIPT" --mode watchdog >> "$LOG_FILE" 2>&1; then
        log_error "Watchdog failed (Code: $?)"
        exit 1
    fi
fi

log_info "--- Task Finished Successfully ---"