#!/zsh

# ============================================================================
# 1. 환경 설정 및 경로 정의 (최상단 배치 필수)
# ============================================================================
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# 스크립트 위치 기준 경로 설정 (가장 먼저 정의되어야 함)
AGENT_DIR="${0:A:h}"
REPO_ROOT="${AGENT_DIR:h}"
LOG_DIR="$AGENT_DIR/logs"
LOG_FILE="$LOG_DIR/trigger.log"
LOCK_FILE="$AGENT_DIR/.trigger.lock"
ENV_FILE="$AGENT_DIR/.env"

mkdir -p "$LOG_DIR"

# ============================================================================
# 2. 환경 변수 로드 (.env)
# ============================================================================
if [[ -f "$ENV_FILE" ]]; then
    # 주석 제외, 빈 줄 제외하고 export 실행
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "✅ GH_TOKEN loaded from .env" >> "$LOG_FILE"
else
    echo "❌ Error: .env file not found at $ENV_FILE" >> "$LOG_FILE"
    # 토큰이 없으면 이후 gh 명령어가 실패하므로 여기서 종료하거나 예외처리 필요
fi

# 디버깅용 (보안을 위해 앞 4자리만 출력)
if [[ -n "$GH_TOKEN" ]]; then
    echo "Debug: GH_TOKEN starts with ${GH_TOKEN:0:4}..." >> "$LOG_FILE"
fi

# ============================================================================
# 3. 중복 실행 방지 및 사전 체크
# ============================================================================
if [[ -f "$LOCK_FILE" ]]; then
    echo "[$(date)] ⚠️ Agent already running. Exiting." >> "$LOG_FILE"
    exit 0
fi

touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

# ============================================================================
# 4. Git 동기화 및 에이전트 실행
# ============================================================================
cd "$REPO_ROOT" || exit 1
CURRENT_BRANCH=$(git branch --show-current)

echo "--- Run: $(date '+%Y-%m-%d %H:%M:%S') (Branch: $CURRENT_BRANCH) ---" >> "$LOG_FILE"

# Git Pull (인증된 GH_TOKEN 활용)
git pull --rebase origin "$CURRENT_BRANCH" >> "$LOG_FILE" 2>&1

# 신규 신호 확인 및 에이전트 호출
NEW_SIGNALS=$(gh issue list --label "to-blog" --state open --json number,comments --jq '.[] | select(.comments | length > 0) | .number')

if [[ -n "$NEW_SIGNALS" ]]; then
    echo "🔔 Signal detected ($NEW_SIGNALS). Running PROCESS mode..." >> "$LOG_FILE"
    python3 "$AGENT_DIR/main.py" --mode process >> "$LOG_FILE" 2>&1
else
    echo "ℹ️ No signals. Running WATCHDOG mode..." >> "$LOG_FILE"
    python3 "$AGENT_DIR/main.py" --mode watchdog >> "$LOG_FILE" 2>&1
fi

echo "--- Finished ---" >> "$LOG_FILE"

