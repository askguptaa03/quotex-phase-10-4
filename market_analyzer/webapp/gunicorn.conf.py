"""Gunicorn production configuration for the Quotex Signal Dashboard.
Usage: gunicorn -c gunicorn.conf.py app:app
(Run from inside Quotex/market_analyzer/webapp/, or via start-prod.sh)
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# P0 fix — Multi-worker/deployment state consistency.
# app.py's scanner/backtest/validation/session state (_shared_fetcher,
# _scanner, _backtest_engine, _validation_engine, _BG_LOOP) is process-
# global, in-memory, single-instance state — not shared across OS
# processes. The previous default (WEB_CONCURRENCY, defaulting to 2) would
# spawn multiple independent gunicorn worker PROCESSES, each with its own
# separate copy of every one of those globals: a Quotex session opened in
# one worker is invisible to another, and a backtest/validation/scanner
# job started via a request that lands on worker A would appear stalled
# or "not found" to a status poll that lands on worker B. This is a real,
# concrete contributor to the reported session/stall symptoms, not merely
# a theoretical risk.
#
# Minimal fix: pin to exactly 1 worker process, unconditionally — this
# does not touch app.py's architecture at all (no rewrite to shared/
# external state), it just stops multiple independent copies of that
# state from being spawned in the first place. WEB_CONCURRENCY is
# intentionally no longer read here; if concurrency is ever needed, the
# shared state itself must first move out of process-globals (e.g. into
# Redis/a DB) — that is out of scope for this P0 fix.
workers = 1
worker_class = "sync"
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
