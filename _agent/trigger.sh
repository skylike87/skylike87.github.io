#!/bin/zsh

# 프로젝트 절대 경로 추출
AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 🎯 가상환경 내부의 파이썬 실행 파일을 직접 지칭
# 이 경로는 가상환경을 활성화(source)하지 않아도 해당 패키지들을 다 물고 있습니다.
VENV_PYTHON="$AGENT_DIR/.venv/bin/python3"

# 🔍 파이썬 바이너리 존재 여부 확인 (Fail-fast)
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[$(date)] ❌ Error: Python Venv not found at $VENV_PYTHON" >> "$AGENT_DIR/logs/trigger.log"
    exit 1
fi

# 실행
$VENV_PYTHON "$AGENT_DIR/main.py" --mode process >> "$AGENT_DIR/logs/trigger.log" 2>&1

# ============================================================================
# 1. 환경 설정 및 경로 정의
# ============================================================================
AGENT_DIR="${0:A:h}"
REPO_ROOT="${AGENT_DIR:h}"

# rbenv 및 시스템 경로 최적화 (shims 경로를 최우선으로)
export PATH="$HOME/.rbenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

LOG_DIR="$AGENT_DIR/logs"
LOG_FILE="$LOG_DIR/trigger.log"
LOCK_DIR="$AGENT_DIR/blog_agent.lock"
ENV_FILE="$AGENT_DIR/.env"
PYTHON_SCRIPT="$AGENT_DIR/main.py"

mkdir -p "$LOG_DIR"

# 로그 출력 래퍼 함수
log_info() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $1" >> "$LOG_FILE"; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$LOG_FILE"; }

# ============================================================================
# 2. 로그 로테이션 (10MB 초과 시 백업)
# ============================================================================
if [[ -f "$LOG_FILE" ]]; then
    LOG_SIZE=$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
    if (( LOG_SIZE > 10485760 )); then
        mv "$LOG_FILE" "$LOG_FILE.$(date +%Y%m%d_%H%M%S).old"
        log_info "Log rotated due to size limit (10MB)."
    fi
fi

# ============================================================================
# 3. 원자적 Lock 및 Stale Lock 방어
# ============================================================================
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    if [[ -f "$LOCK_DIR/pid" ]]; then
        OLD_PID=$(cat "$LOCK_DIR/pid" 2>/dev/null)
        if ! kill -0 "$OLD_PID" 2>/dev/null; then
            log_info "Removing stale lock (PID $OLD_PID is not running)."
            rm -rf "$LOCK_DIR"
            mkdir "$LOCK_DIR"
        else
            log_info "⚠️ Agent already running (PID: $OLD_PID). Exiting."
            exit 0
        fi
    else
        rm -rf "$LOCK_DIR"
        mkdir "$LOCK_DIR"
    fi
fi
echo $$ > "$LOCK_DIR/pid"

# 개선된 trap: EXIT 시점에 락 디렉토리만 안전하게 제거
trap "rm -rf '$LOCK_DIR'" EXIT INT TERM

# ============================================================================
# 4. 환경 변수 로드 (공백, 따옴표 및 마지막 줄 처리 강화)
# ============================================================================
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        [[ "$key" =~ ^[[:space:]]*# || -z "$key" ]] && continue
        value="${value%\"}"
        value="${value#\"}"
        export "$key=$value"
    done < "$ENV_FILE"
    log_info "✅ Environment variables loaded safely."
else
    log_error ".env file not found. Termination."
    exit 1
fi

# ============================================================================
# 5. 실행 환경 사전 검증 (Venv Python 추가)
# ============================================================================
if [[ ! -f "$VENV_PYTHON" ]]; then
    log_error "Python Virtual Environment not found at $VENV_PYTHON. Run 'python3 -m venv .venv' first."
    exit 1
fi

if ! gh auth status &>/dev/null; then
    log_error "GitHub CLI authentication failed. Please check GH_TOKEN."
    exit 1
fi

# ============================================================================
# 6. 메인 로직 실행 (VENV_PYTHON 사용)
# ============================================================================
if [[ -n "${NEW_SIGNALS// /}" ]]; then
    log_info "🔔 Signal detected: Issue #$NEW_SIGNALS. Starting PROCESS mode."
    # 🎯 여기를 $VENV_PYTHON으로 교체!
    if ! "$VENV_PYTHON" "$PYTHON_SCRIPT" --mode process >> "$LOG_FILE" 2>&1; then
        log_error "Python PROCESS mode failed with exit code $?"
        exit 1
    fi
else
    log_info "ℹ️ No comments found. Starting WATCHDOG mode."
    # 🎯 여기도 $VENV_PYTHON으로 교체!
    if ! "$VENV_PYTHON" "$PYTHON_SCRIPT" --mode watchdog >> "$LOG_FILE" 2>&1; then
        log_error "Python WATCHDOG mode failed with exit code $?"
        exit 1
    fi
fi

# 신규 신호 확인
NEW_SIGNALS=$(gh issue list --label "to-blog" --state open --json number,comments --jq '.[] | select(.comments | length > 0) | .number' | tr '\n' ' ')

if [[ -n "${NEW_SIGNALS// /}" ]]; then
    log_info "🔔 Signal detected: Issue #$NEW_SIGNALS. Starting PROCESS mode."
    # Python 실행 실패 시 로그를 남기고 종료 코드 1 반환
    if ! python3 "$PYTHON_SCRIPT" --mode process >> "$LOG_FILE" 2>&1; then
        log_error "Python PROCESS mode failed with exit code $?"
        exit 1
    fi
else
    log_info "ℹ️ No comments found. Starting WATCHDOG mode."
    if ! python3 "$PYTHON_SCRIPT" --mode watchdog >> "$LOG_FILE" 2>&1; then
        log_error "Python WATCHDOG mode failed with exit code $?"
        exit 1
    fi
fi

log_info "--- Task Finished Successfully ---"