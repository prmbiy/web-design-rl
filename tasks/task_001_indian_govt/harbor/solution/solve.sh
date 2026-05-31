#!/bin/bash
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
