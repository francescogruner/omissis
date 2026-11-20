#!/bin/bash
# Prove automatiche sul Mac di GitHub Actions, con il Python che sta dentro l'app costruita (dist/Omissis.app).
# Accende una copia di prova (porte 8775-8777, protezione attiva, modello scaricato al primo avvio) e lancia le prove
# che non hanno bisogno di un browser. Il Portachiavi vero non si tocca: al suo posto un file (OMISSIS_FAKE_KEYCHAIN).
set -u
# Sul Mac il comando «timeout» non c'è: se manca, lo fa perl (il segnale di allarme ferma la prova troppo lunga).
command -v timeout > /dev/null || timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/Omissis.app"
PY="$APP/Contents/Resources/python/bin/python3"
WORK="${RUNNER_TEMP:-/tmp}/omissis-ci"
mkdir -p "$WORK/data/lists"
export OMISSIS_PORT=8775 OMISSIS_TEST=1 OMISSIS_DATA="$WORK/data" OMISSIS_LISTS="$WORK/data/lists"
export OMISSIS_MANAGED_FILE="$WORK/managed.json" OMISSIS_FAKE_KEYCHAIN="$WORK/keychain.json"
printf '{}' > "$OMISSIS_MANAGED_FILE"
printf '{"groups_off": []}' > "$WORK/data/settings.json"   # le prove usano anche i nomi delle aziende
cp "$ROOT/model/lists/"*.txt "$WORK/data/lists/"

cd "$ROOT/app"
"$PY" mock_service.py 9911 > "$WORK/mock.log" 2>&1 &
"$APP/Contents/MacOS/Omissis" --test --no-tray --no-browser > "$WORK/panel.log" 2>&1 &
echo "attendo la protezione (al primo avvio scarica il modello)..."
for i in $(seq 1 300); do
  if [ -f "$WORK/data/token.txt" ] && curl -s -m 2 -H "X-Token: $(cat "$WORK/data/token.txt")" http://127.0.0.1:8775/status > /dev/null; then
    echo "protezione attiva dopo $((i * 2)) s"; break
  fi
  sleep 2
done

failed=0
for t in e2e_vault.py e2e_central.py e2e_inventory.py e2e_mcp.py e2e_gateway.py e2e_proxy.py e2e_plugins.py e2e_kimi.py; do
  echo "=================== $t"
  if ! timeout 900 "$PY" "$t"; then failed=1; echo "### NON PASSATA: $t"; fi
done
echo "--- registro del pannello"; tail -30 "$WORK/panel.log"
exit $failed
