#!/usr/bin/env bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export PYTHON_TEMPLATE_DEV=1
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 -B "$PROJECT_DIR/6aus45.py" "$@"
