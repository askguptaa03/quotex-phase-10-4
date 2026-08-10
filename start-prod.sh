#!/usr/bin/env bash
# Production startup script for Quotex Flask Signal Dashboard.
#
# Fixed from the earlier version: no hardcoded /home/runner/workspace
# paths. Those only worked on the specific Replit runner that produced
# them and would silently break on a brand-new project with a different
# path. Everything below resolves relative to this script's own location
# and relies on `python3`/`gunicorn` being on PATH once dependencies are
# installed — the standard, portable way to do this.
set -euo pipefail

# 1. Resolve this script's own location safely (works no matter where the
#    project root actually is on this particular Replit instance).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 2. cd to the Flask app's own directory (app.py bootstraps its own
#    sys.path from here; gunicorn.conf.py and preflight_check.py also
#    live here).
WEBAPP_DIR="${SCRIPT_DIR}/Quotex/market_analyzer/webapp"
cd "$WEBAPP_DIR"

PORT="${PORT:-5000}"
export PORT

# 3. Verify the files this script depends on actually exist before doing
#    anything else — fail fast with a clear message instead of a
#    confusing gunicorn import error.
for required in app.py gunicorn.conf.py; do
    if [ ! -f "$required" ]; then
        echo "FATAL: expected file '$required' not found in $WEBAPP_DIR — is the project structure intact?" >&2
        exit 1
    fi
done

# 4. Run the existing pre-flight check, if present. Verifies Python env,
#    dependency imports, Playwright/Chromium, config, and required files
#    before we bind to a port. Aborts startup only on CRITICAL failures
#    (e.g. a required package won't import). Missing Quotex session /
#    Chromium are reported as warnings, not startup blockers, since the
#    dashboard can still serve and a session can be added afterward via
#    the QUOTEX_SSID secret or the app's own session UI.
if [ -f "preflight_check.py" ]; then
    echo "Running pre-flight health check..."
    if ! python3 preflight_check.py; then
        echo "Pre-flight health check FAILED — aborting startup." >&2
        exit 1
    fi
else
    echo "preflight_check.py not found — skipping pre-flight check."
fi

# 5. Launch. gunicorn.conf.py pins workers = 1 — this application keeps
#    in-process shared state (Quotex session, scanner, backtest/
#    validation engines) that is NOT safe across multiple worker
#    processes or multiple deployment instances. See DEPLOYMENT_README.md.
echo "Starting Quotex Signal Dashboard on port $PORT..."
exec gunicorn -c gunicorn.conf.py app:app
