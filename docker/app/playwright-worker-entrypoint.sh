#!/bin/sh
set -eu
exec xvfb-run -a uvicorn worker.main:app --host 0.0.0.0 --port 8090
