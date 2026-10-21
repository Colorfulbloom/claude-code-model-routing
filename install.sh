#!/usr/bin/env bash
# Shim: checks python3, then runs install.py next to this file with the same arguments.
set -euo pipefail

MSG_ERR_NO_PYTHON='Error: python3 is not on PATH. Install it and run this again.\n'
MSG_ERR_OLD_PYTHON='Error: python3 is older than 3.9 (%s). Install a newer one and run this again.\n'

# The format strings come from the two lines above, never from input.
# shellcheck disable=SC2059
die() { local fmt="$1"; shift; printf "$fmt" "$@" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "$MSG_ERR_NO_PYTHON"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || die "$MSG_ERR_OLD_PYTHON" "$(python3 --version 2>&1)"
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/install.py" "$@"
