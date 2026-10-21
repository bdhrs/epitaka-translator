#!/usr/bin/env bash
#
# review_runner.sh — keep a translation review going across usage limits.
#
#   ./review_runner.sh [lang] [model] [extra verify_translation.py flags]
#
#   ./review_runner.sh kn claude:sonnet
#   ./review_runner.sh kn azure:DeepSeek-V4.1-Flash --book M-iii
#
# Same loop as runner.sh: when every key is exhausted (a Claude 5 h or weekly
# limit) it sleeps until the limit resets and starts verify_translation.py
# again. A restart skips the chunks that model already reviewed (the
# review_progress table), so nothing is repeated or duplicated. Exits when
# the review finishes.
#
set -u

SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
cd "$SCRIPT_DIR"

LANG_CODE="${1:-kn}"
MODEL_NAME="${2:-claude:sonnet}"
shift $(( $# < 2 ? $# : 2 ))

if ! command -v uv >/dev/null 2>&1; then
    echo "[PYTHON] ERROR: uv is required (https://docs.astral.sh/uv/getting-started/installation/)." >&2
    exit 1
fi
uv sync --project "$SCRIPT_DIR" || exit 1

# Waits and their reasons are the same as in runner.sh.
SLEEP_DURATION=10800   # 3 h, for providers without a known reset time
WINDOW_SECONDS=18000   # the Claude limit is a 5 h window opened by the first request
MIN_WORK_SECONDS=120   # a shorter run did no work, so it cannot have opened a window
RETRY_SECONDS=600      # shortest wait, so a still-limited retry does not spin
RESET_MARGIN=120       # the limit message rounds its reset time to the minute
MAX_RESET_WAIT=691200  # a reset further off than 8 days is read as a bad parse
WINDOW_START=0

echo "Starting review loop for lang='$LANG_CODE', model='$MODEL_NAME'..."

while true; do
    echo "=================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting review run..."
    echo "=================================================="

    TEMP_LOG=$(mktemp)
    RUN_START=$(date +%s)

    # -u: unbuffered, or tee holds the progress lines back in big batches.
    uv run python -u src/verify_translation.py --lang "$LANG_CODE" --model "$MODEL_NAME" "$@" 2>&1 | tee "$TEMP_LOG"
    EXIT_CODE=${PIPESTATUS[0]}

    if grep -q "All API keys exhausted" "$TEMP_LOG"; then
        echo ""
        echo "[WARNING] Detected API key exhaustion!"
        SLEEP_FOR=$SLEEP_DURATION
        RUN_END=$(date +%s)

        if [[ "$MODEL_NAME" == claude:* ]]; then
            if [ $((RUN_END - RUN_START)) -ge $MIN_WORK_SECONDS ]; then
                WINDOW_START=$RUN_START
            fi
            SLEEP_FOR=$((WINDOW_START + WINDOW_SECONDS - RUN_END))
            if [ "$SLEEP_FOR" -lt "$RETRY_SECONDS" ]; then
                SLEEP_FOR=$RETRY_SECONDS
            fi
            # The limit message names the exact reset time: use it when it is still ahead.
            RESET_AT=$(grep -o '\[RESET-AT\] [0-9]*' "$TEMP_LOG" | tail -1 | grep -o '[0-9]*$')
            if [ -n "$RESET_AT" ]; then
                UNTIL_RESET=$((RESET_AT + RESET_MARGIN - RUN_END))
                if [ "$UNTIL_RESET" -gt 0 ] && [ "$UNTIL_RESET" -lt "$MAX_RESET_WAIT" ]; then
                    SLEEP_FOR=$UNTIL_RESET
                fi
            fi
        fi

        echo "[SLEEP] Waiting $((SLEEP_FOR / 60)) min before retrying (will resume at $(date -d "+${SLEEP_FOR} seconds" '+%H:%M:%S' 2>/dev/null || date -v+${SLEEP_FOR}S '+%H:%M:%S'))..."
        rm -f "$TEMP_LOG"
        sleep "$SLEEP_FOR"
    else
        rm -f "$TEMP_LOG"
        if [ $EXIT_CODE -eq 0 ]; then
            echo "[SUCCESS] Review finished without key exhaustion."
            break
        else
            echo "[ERROR] Process exited with error code $EXIT_CODE (not API key exhaustion). Retrying in 60s..."
            sleep 60
        fi
    fi
done
