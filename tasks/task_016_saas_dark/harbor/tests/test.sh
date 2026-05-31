#!/bin/bash
# Verifier entry point. Runs as root.
# Renders the agent's output and runs the completeness checker.

set -euo pipefail

REWARD_JSON="/logs/verifier/reward.json"
REWARD_TXT="/logs/verifier/reward.txt"
CAPTURES_DIR="/logs/verifier/agent_screenshots"

mkdir -p /logs/verifier "${CAPTURES_DIR}"

python3 /opt/checker/run.py \
  --agent-site /app/site \
  --ground-truth-screenshots /task/screenshots \
  --captures-out "${CAPTURES_DIR}" \
  --reward-out "${REWARD_JSON}"

echo "Verifier complete. Score written to ${REWARD_TXT}"
