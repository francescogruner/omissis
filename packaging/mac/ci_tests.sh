#!/bin/bash
# Prove automatiche sul Mac di GitHub Actions, con il Python che sta dentro l'app costruita (dist/Omissis.app).
# Accende una copia di prova (porte 8775-8777, protezione attiva, modello scaricato al primo avvio) e lancia le prove
# che non hanno bisogno di un browser. Il Portachiavi vero non si tocca: al suo posto un file (OMISSIS_FAKE_KEYCHAIN).
# La copia di prova parte con l'icona nella barra dei menu: le scorciatoie da tastiera esistono solo cosi'.
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

# Quando un programma cade, macOS ne scrive un rapporto: qui se ne stampa il perche' e dove e' caduto.
crash_report() {
  sleep 5
  python3 - << 'PYEOF'
import glob, json, os
files = sorted(glob.glob(os.path.expanduser("~/Library/Logs/DiagnosticReports/*.ips")), key=os.path.getmtime)
if not files:
    print("nessun rapporto di macOS trovato")
    raise SystemExit
text = open(files[-1], encoding="utf-8", errors="replace").read()
body = text.partition(chr(10))[2]
print("--- rapporto di macOS:", os.path.basename(files[-1]))
try:
    d = json.loads(body)
except ValueError:
    print(text[:3000])
    raise SystemExit
for k in ("exception", "termination", "asi", "lastExceptionBacktrace"):
    if k in d:
        print(k, ":", json.dumps(d[k])[:1800])
images = d.get("usedImages", [])
for t in d.get("threads", []):
    if t.get("triggered"):
        print("thread caduto:", t.get("name") or t.get("queue") or "")
        for fr in t.get("frames", [])[:30]:
            i = fr.get("imageIndex", -1)
            print("   ", images[i].get("name", "?") if 0 <= i < len(images) else "?", fr.get("symbol", ""))
PYEOF
}

cd "$ROOT/app"
icon_bad=0
# Il programma con l'icona nella barra dei menu deve partire ogni volta: alcuni avvii senza protezione, e resta acceso?
# (quattro di serie; OMISSIS_ICON_STARTS ne chiede di piu', e con OMISSIS_ONLY_ICON=1 la prova finisce li')
for n in $(seq 1 "${OMISSIS_ICON_STARTS:-4}"); do
  "$APP/Contents/MacOS/Omissis" --test --no-browser --no-start > "$WORK/icon-$n.log" 2>&1 &
  P=$!
  sleep 5
  if kill -0 "$P" 2> /dev/null; then echo "avvio $n con l'icona: acceso"; else icon_bad=1; echo "### avvio $n con l'icona: il programma e' caduto"; tail -15 "$WORK/icon-$n.log"; crash_report; fi
  kill "$P" 2> /dev/null; sleep 1; pkill -f "$APP/Contents/" 2> /dev/null; sleep 1
done
if [ -n "${OMISSIS_ONLY_ICON:-}" ]; then echo "avvii con l'icona: fine (caduto almeno una volta: $icon_bad)"; exit $icon_bad; fi

"$PY" mock_service.py 9911 > "$WORK/mock.log" 2>&1 &
MOCK=$!
wait_protection() {   # 0 quando la protezione e' attiva; 1 se il programma e' caduto o non parte
  for i in $(seq 1 300); do
    if ! kill -0 "$PANEL" 2> /dev/null; then echo "### il programma e' caduto all'avvio"; tail -20 "$WORK/panel.log"; return 1; fi
    if [ -f "$WORK/data/token.txt" ] && curl -s -m 2 -H "X-Token: $(cat "$WORK/data/token.txt")" http://127.0.0.1:8775/status > /dev/null; then
      echo "protezione attiva dopo $((i * 2)) s"; return 0
    fi
    sleep 2
  done
  return 1
}
"$APP/Contents/MacOS/Omissis" --test --no-browser > "$WORK/panel.log" 2>&1 &
PANEL=$!
echo "attendo la protezione (al primo avvio scarica il modello)..."
if ! wait_protection; then
  icon_bad=1
  crash_report
  echo "### riparto senza icona, per le prove che non ne hanno bisogno"
  pkill -f "$APP/Contents/" 2> /dev/null; sleep 2
  "$APP/Contents/MacOS/Omissis" --test --no-tray --no-browser > "$WORK/panel.log" 2>&1 &
  PANEL=$!
  wait_protection
fi

failed=$icon_bad
for t in e2e_vault.py e2e_central.py e2e_inventory.py e2e_mcp.py e2e_gateway.py e2e_proxy.py e2e_rpc.py e2e_port.py e2e_plugins.py e2e_kimi.py e2e_documents.py e2e_macapp.py; do
  echo "=================== $t"
  if ! timeout 900 "$PY" "$t"; then failed=1; echo "### NON PASSATA: $t"; fi
done
echo "=================== scorciatoie da tastiera"
if ! timeout 120 "$PY" "$ROOT/packaging/mac/keys_test.py"; then failed=1; echo "### NON PASSATA: keys_test.py"; fi
echo "--- registro del pannello"; tail -30 "$WORK/panel.log"
# Per ultima, perche' dopo la copia di prova non c'e' piu': il pannello chiuso di colpo, come in un guasto. Il motore e
# il proxy devono chiudersi da soli, senza restare accesi a tenere le porte
echo "=================== pannello chiuso di colpo"
if ! timeout 120 "$PY" "$ROOT/packaging/mac/closing_test.py"; then failed=1; echo "### NON PASSATA: closing_test.py"; fi
# la copia di prova si spegne qui, con il suo motore e il suo proxy: chi viene dopo deve trovare le porte libere
kill "$PANEL" "$MOCK" 2> /dev/null
sleep 2
pkill -f "$APP/Contents/" 2> /dev/null
exit $failed
