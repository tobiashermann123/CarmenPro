#!/usr/bin/env bash
# Apply numbered SQL migrations to Supabase via psql.
# Requires: psql, SUPABASE_DB_URL in environment or .env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="$SCRIPT_DIR/../infrastructure/supabase/migrations"

if [ -f "$SCRIPT_DIR/../.env" ]; then
    set -a && source "$SCRIPT_DIR/../.env" && set +a
fi

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL must be set (postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres)}"

echo "Applying migrations from $MIGRATIONS_DIR"
for file in "$MIGRATIONS_DIR"/[0-9]*.sql; do
    echo "  -> $(basename "$file")"
    psql "$SUPABASE_DB_URL" -f "$file"
done
echo "Done."
