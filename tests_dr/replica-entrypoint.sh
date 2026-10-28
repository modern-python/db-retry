#!/bin/bash
set -eu
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    pg_basebackup -h pg-primary -U dr -D "$PGDATA" -R -X stream
    chmod 0700 "$PGDATA"
fi
exec postgres
