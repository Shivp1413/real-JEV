#!/usr/bin/env bash
# JevLocal launcher for macOS / Linux.  Usage:  ./start.sh
set -e
cd "$(dirname "$0")"

# Find a Python 3 interpreter
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
  echo "Python 3 is required. Install it from https://www.python.org/downloads/ and re-run."
  exit 1
fi

exec "$PY" run.py "$@"
