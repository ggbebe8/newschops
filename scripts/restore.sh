#!/bin/sh
set -eu
[ "$#" -eq 1 ] || { echo 'Usage: sh scripts/restore.sh backups/file.dump'; exit 1; }
[ -f "$1" ] || exit 1
docker compose stop app worker
docker compose exec -T db pg_restore -U newschops -d newschops --clean --if-exists --exit-on-error < "$1"
docker compose up -d app worker
