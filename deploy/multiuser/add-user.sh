#!/usr/bin/env bash
# Onboard a user as an isolated instance on this NUC: own database, port, token, and state,
# sharing the primary image / Postgres / Docker network. Run ON THE NUC from the repo.
#
#   ./deploy/multiuser/add-user.sh <name>          # prompts for their Zerodha creds
#   ./deploy/multiuser/add-user.sh <name> --mock   # test instance, no creds (mock portfolio)
#
# Afterwards: add their phone to your tailnet, install the app (TestFlight), and give them
# their URL (printed at the end) + token (in <instance>/.env).
set -euo pipefail

NAME="${1:?usage: add-user.sh <name> [--mock]}"
NAME="$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
MOCK=""; [ "${2:-}" = "--mock" ] && MOCK=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTANCES="${SMA_INSTANCES:-$HOME/sma-instances}"
DIR="$INSTANCES/$NAME"
PRIMARY_ENV="$REPO/.env"
DB_CONTAINER="sm-adviser-db"
COMPOSE_FILE="$REPO/deploy/multiuser/docker-compose.user.yml"

[ -e "$DIR" ] && { echo "ERROR: instance '$NAME' already exists ($DIR)"; exit 1; }
[ -f "$PRIMARY_ENV" ] || { echo "ERROR: primary $PRIMARY_ENV not found (run from the NUC repo)"; exit 1; }

# --- assign the next free API + Tailscale ports (primary uses 8787 / 8443) ---
maxapi=8787; maxts=8443
for f in "$INSTANCES"/*/.env; do
  [ -f "$f" ] || continue
  a=$(grep -E '^API_PORT=' "$f" | cut -d= -f2 || true); [ -n "${a:-}" ] && [ "$a" -gt "$maxapi" ] && maxapi=$a
  t=$(grep -E '^TS_PORT='  "$f" | cut -d= -f2 || true); [ -n "${t:-}" ] && [ "$t" -gt "$maxts"  ] && maxts=$t
done
API_PORT=$((maxapi + 1)); TS_PORT=$((maxts + 1))
DB="sma_$NAME"
TOKEN="$(openssl rand -hex 32)"
POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$PRIMARY_ENV" | cut -d= -f2-)"
ANTHROPIC="$(grep -E '^ANTHROPIC_API_KEY=' "$PRIMARY_ENV" | cut -d= -f2-)"   # shared host key

# --- gather Zerodha credentials (unless --mock) ---
KAK=""; KAS=""; KUID=""; KPW=""; KTOTP=""; CONNECTOR="mock"
if [ -z "$MOCK" ]; then
  CONNECTOR="zerodha"
  echo "Enter $NAME's Zerodha / Kite details:"
  read -rp  "  KITE_API_KEY:     " KAK
  read -rp  "  KITE_API_SECRET:  " KAS
  read -rp  "  KITE_USER_ID:     " KUID
  read -rsp "  KITE_PASSWORD:    " KPW;   echo
  read -rsp "  KITE_TOTP_SECRET: " KTOTP; echo
fi

# --- write the instance dir + .env ---
mkdir -p "$DIR/reports_out"
[ -f "$DIR/kite_token.json" ] || echo '{}' > "$DIR/kite_token.json"
umask 077
cat > "$DIR/.env" <<EOF
# SM Adviser instance: $NAME
INSTANCE_NAME=$NAME
INSTANCE_DIR=$DIR
SMA_CODE=$REPO
SHARED_NET=sm-adviser_default
API_PORT=$API_PORT
TS_PORT=$TS_PORT
PORTFOLIO_CONNECTOR=$CONNECTOR
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
WIDGET_API_TOKEN=$TOKEN
DATABASE_URL=postgresql+psycopg://portfolio:$POSTGRES_PASSWORD@$DB_CONTAINER:5432/$DB
ANTHROPIC_API_KEY=$ANTHROPIC
KITE_API_KEY=$KAK
KITE_API_SECRET=$KAS
KITE_USER_ID=$KUID
KITE_PASSWORD=$KPW
KITE_TOTP_SECRET=$KTOTP
EOF
chmod 600 "$DIR/.env"
umask 022

# --- create the per-user database in the shared Postgres ---
if ! docker exec "$DB_CONTAINER" psql -U portfolio -tc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1; then
  docker exec "$DB_CONTAINER" createdb -U portfolio "$DB"
  echo "created database $DB"
fi

compose() { docker compose -p "sma-$NAME" --env-file "$DIR/.env" -f "$COMPOSE_FILE" "$@"; }

echo "=== migrate + start ==="
compose --profile job run --rm migrate
compose up -d api
sleep 4
compose --profile job run --rm morning-run || echo "  (first morning-run failed — usually Kite creds; fix .env and re-run: $0 ... or run-all.sh morning-run)"

# --- HTTPS via Tailscale serve on the per-user port ---
sudo tailscale serve --bg --https="$TS_PORT" "$API_PORT"

# --- register for the looping timers ---
grep -qxF "$NAME" "$INSTANCES/registry" 2>/dev/null || echo "$NAME" >> "$INSTANCES/registry"

FQDN="$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || echo '<your-nuc>.ts.net')"
echo
echo "================= $NAME onboarded ================="
echo "  Server URL : https://$FQDN:$TS_PORT"
echo "  Token      : in $DIR/.env  (WIDGET_API_TOKEN)"
echo "  Next steps : add their phone to your tailnet; app -> that URL + token."
echo "  Remove     : ./deploy/multiuser/remove-user.sh $NAME"
echo "==================================================="
