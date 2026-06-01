#!/bin/bash
# Verifier entry point. Runs as root.
# Renders the agent's output and runs the completeness checker.

set -euo pipefail

REWARD_JSON="/logs/verifier/reward.json"
CAPTURES_DIR="/logs/verifier/agent_screenshots"

mkdir -p /logs/verifier "${CAPTURES_DIR}"

node /opt/checker/run.js \
  --agent-site /app/site \
  --ground-truth-screenshots /task/screenshots \
  --captures-out "${CAPTURES_DIR}" \
  --reward-out "${REWARD_JSON}"

echo "Verifier complete."
