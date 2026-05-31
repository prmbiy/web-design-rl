def render_solve_sh() -> str:
    return """#!/bin/bash
# Oracle solver: copies the reference site into /app/site/.
# Only mounted and run during Oracle evaluation, never during regular agent runs.

set -euo pipefail

ORACLE_SITE="/solution/site"
AGENT_SITE="/app/site"

if [ ! -d "${ORACLE_SITE}" ]; then
  echo "ERROR: oracle site not found at ${ORACLE_SITE}" >&2
  exit 1
fi

mkdir -p "${AGENT_SITE}"
rm -rf "${AGENT_SITE:?}"/*
cp -R "${ORACLE_SITE}"/. "${AGENT_SITE}"/

echo "Oracle: copied $(find "${AGENT_SITE}" -maxdepth 1 -name '*.html' | wc -l) HTML file(s) to ${AGENT_SITE}"
"""


def render_test_sh() -> str:
    return """#!/bin/bash
# Verifier entry point. Runs as root.
# Renders the agent's output and runs the completeness checker.

set -euo pipefail

REWARD_JSON="/logs/verifier/reward.json"
CAPTURES_DIR="/logs/verifier/agent_screenshots"

mkdir -p /logs/verifier "${CAPTURES_DIR}"

node /opt/checker/run.js \\
  --agent-site /app/site \\
  --ground-truth-screenshots /task/screenshots \\
  --captures-out "${CAPTURES_DIR}" \\
  --reward-out "${REWARD_JSON}"

echo "Verifier complete."
"""
