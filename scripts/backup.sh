#!/bin/sh
set -eu
umask 077
mkdir -p backups
file="backups/newschops-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U newschops -d newschops -Fc > "$file"
printf '%s\n' "$file"
