#!/usr/bin/env bash
set -o errexit
set -o pipefail

export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

uv sync --frozen --no-dev
uv run --frozen python manage.py collectstatic --noinput
uv run --frozen python manage.py migrate
