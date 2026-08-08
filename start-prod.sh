#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/market_analyzer/webapp"

exec gunicorn -c gunicorn.conf.py app:app
