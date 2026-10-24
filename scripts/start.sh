#!/bin/sh
set -eu
if [ "${ROLE:-app}" = migrate ]; then
  alembic -c backend/alembic.ini upgrade head
  python -c 'from backend.app.bootstrap import bootstrap; bootstrap()'
elif [ "${ROLE:-app}" = worker ]; then
  exec python -m backend.app.worker
else
  exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --no-proxy-headers
fi
