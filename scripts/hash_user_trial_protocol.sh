#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

# Bind a rehearsal record to the exact participant prompts and facilitator
# scoring rules. Including this script also binds the digest construction.
printf '%s\0' \
  docs/user-trials/participant-task-card.md \
  docs/user-trials/facilitator-protocol.md \
  scripts/hash_user_trial_protocol.sh \
  | LC_ALL=C sort -z \
  | xargs -0 sha256sum \
  | sha256sum \
  | awk '{print $1}'
