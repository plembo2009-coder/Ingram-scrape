#!/usr/bin/env bash
# One-time setup for a Linux box (headless is fine).
# Usage: ./setup.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Python virtual environment"
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "    created .venv"
else
    echo "    .venv already exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip

echo "==> Python packages"
pip install --quiet -r requirements.txt
echo "    $(pip show playwright | awk '/^Version/{print "playwright " $2}')"

echo "==> Chromium"
# --with-deps installs the system libraries Chromium needs even when headless.
# It needs root; without it, install the browser alone and report what is missing.
if [ "$(id -u)" -eq 0 ]; then
    playwright install --with-deps chromium
elif command -v sudo >/dev/null 2>&1; then
    sudo "$(command -v playwright)" install-deps chromium || {
        echo "    !! could not install system deps; see the message above"
        echo "       (on Debian/Ubuntu: sudo playwright install-deps chromium)"
    }
    playwright install chromium
else
    echo "    no sudo available - installing the browser without system deps"
    playwright install chromium
fi

echo "==> Verifying the browser actually launches"
python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()          # headless
    pg = b.new_page()
    pg.set_content("<h1>ok</h1>")
    assert pg.inner_text("h1") == "ok"
    print(f"    Chromium {b.version} launched and rendered a page")
    b.close()
PY

mkdir -p out data
cat <<'MSG'

Setup complete. Next:

    source .venv/bin/activate
    export INGRAM_USER='plembo@cyberdata.net'
    read -rsp 'Ingram password: ' INGRAM_PASS && export INGRAM_PASS && echo
    python probe.py

Output lands in ./out/ - start with out/00_run_log.txt and out/08_verdict.json.
MSG
