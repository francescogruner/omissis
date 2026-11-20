#!/bin/bash
# Prova sul Mac di GitHub: le app vere di Claude e di ChatGPT, avviate da Omissis con la porta di debug.
# Installa le due app con Homebrew, accende una copia di prova di Omissis CON l'icona e lancia desktop_apps_test.py.
# In più prova ciò che le altre prove saltano: il Portachiavi vero, l'icona nella barra dei menu, una notifica.
#
#   CI=1 bash packaging/mac/desktop_apps_test.sh     (dopo build_mac.py)   -> dist/desktop/esito.txt e le schermate
#
# NON va lanciato sul Mac di una persona: installa e chiude le app di Claude e di ChatGPT. Per questo parte solo con CI=1.
# Non entra in nessun account: delle app si vede la finestra d'ingresso. Che un messaggio venga sostituito lo può
# provare solo una persona con il suo accesso.
set -u
[ -n "${CI:-}" ] || { echo "Questa prova installa e chiude le app di Claude e di ChatGPT: solo su una macchina di prova (CI=1)."; exit 2; }
command -v timeout > /dev/null || timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/Omissis.app"
PY="$APP/Contents/Resources/python/bin/python3"
OUT="$ROOT/dist/desktop"
WORK="${RUNNER_TEMP:-/tmp}/omissis-desktop"
mkdir -p "$OUT" "$WORK/data/lists"
exec > >(tee "$OUT/esito.txt") 2>&1
failed=0

echo "### macchina"
echo "macOS $(sw_vers -productVersion) $(uname -m)"

echo "### installazione delle app (Homebrew)"
export HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_ENV_HINTS=1 HOMEBREW_NO_INSTALL_CLEANUP=1
APPS="${OMISSIS_DESKTOP_APPS:-claude chatgpt}"   # quali app provare (per rifare in fretta una sola)
brew update > "$WORK/brew-update.log" 2>&1 || echo "schede di Homebrew non aggiornate: si usano quelle della macchina"
for cask in $APPS; do
  brew info --cask --json=v2 "$cask" 2> /dev/null | python3 -c 'import json, sys
c = json.load(sys.stdin)["casks"][0]
print("scheda:", c["token"], "|", c["version"], "|", c["url"])' || echo "scheda di $cask non letta"
  brew install --cask "$cask" > "$WORK/brew-$cask.log" 2>&1 || { echo "ERRORE: $cask non installata"; tail -8 "$WORK/brew-$cask.log"; }
done
# come su un Mac dove l'app è già stata aperta una volta: senza il segno «scaricata da Internet»
for a in Claude ChatGPT; do
  [ -d "/Applications/$a.app" ] || continue
  xattr -dr com.apple.quarantine "/Applications/$a.app" 2> /dev/null || true
  printf '%s: ' "/Applications/$a.app"; codesign -dv "/Applications/$a.app" 2>&1 | grep -E "^(Identifier|TeamIdentifier)=" | tr '\n' ' '; echo
done

echo "### Portachiavi vero"
# la chiave dell'archivio si crea e si rilegge nel Portachiavi di questo utente, poi si toglie
( unset OMISSIS_FAKE_KEYCHAIN; cd "$ROOT/app" && timeout 60 "$PY" -c '
import keyring, sistema
name = "prova-ci"
first = sistema.keychain_secret(name)
again = sistema.keychain_secret(name)
print("Portachiavi:", type(keyring.get_keyring()).__name__, "| chiave creata:", bool(first), "| riletta uguale:", first == again)
keyring.delete_password("Omissis", name)
print("tolta:", keyring.get_password("Omissis", name) is None)
raise SystemExit(0 if first and first == again else 1)
' ) && echo "OK    Portachiavi vero: la chiave si crea, si rilegge uguale e si toglie" || { echo "NO    Portachiavi vero"; failed=1; }

echo "### Omissis di prova, con l'icona"
export OMISSIS_PORT=8775 OMISSIS_TEST=1 OMISSIS_DATA="$WORK/data" OMISSIS_LISTS="$WORK/data/lists"
export OMISSIS_MANAGED_FILE="$WORK/managed.json" OMISSIS_FAKE_KEYCHAIN="$WORK/keychain.json"
printf '{}' > "$OMISSIS_MANAGED_FILE"
cp "$ROOT/model/lists/"*.txt "$WORK/data/lists/"
cd "$ROOT/app"
"$APP/Contents/MacOS/Omissis" --test --no-browser > "$WORK/panel.log" 2>&1 &
PANEL=$!
ready=0
for i in $(seq 1 300); do
  if [ -f "$WORK/data/token.txt" ] && curl -s -m 2 -H "X-Token: $(cat "$WORK/data/token.txt")" http://127.0.0.1:8775/status > /dev/null; then
    echo "protezione attiva dopo $((i * 2)) s"; ready=1; break
  fi
  sleep 2
done
[ "$ready" = 1 ] || { echo "NO    la protezione non è partita"; failed=1; }
sleep 5
if kill -0 "$PANEL" 2> /dev/null; then echo "OK    Omissis resta acceso con l'icona nella barra dei menu (processo vivo)"; else echo "NO    Omissis con l'icona si è chiuso"; failed=1; fi
screencapture -x "$OUT/omissis-1-icona.png" 2> /dev/null && echo "schermata dell'icona salvata" || echo "schermata non riuscita"
( timeout 20 "$PY" -c '
import sistema, time
print("notifica chiesta al sistema:", bool(sistema.notify("Prova di Omissis sul Mac")))
time.sleep(4)' ) || echo "notifica non riuscita"
screencapture -x "$OUT/omissis-2-notifica.png" 2> /dev/null || true

echo "### le app vere"
timeout 900 "$PY" "$ROOT/packaging/mac/desktop_apps_test.py" "$OUT" $APPS || failed=1

# Un'app che si chiude appena vede la porta: la si avvia a mano e si guarda che cosa scrive e con che codice esce.
diagnose() {   # nome, programma, porta, modo (diretto | open)
  local log="$WORK/diag-$1-$4.log" pid="" n=0
  echo "--- diagnosi: $1 con la porta $3, avvio $4"
  if [ "$4" = open ]; then
    open -n -a "/Applications/$1.app" --args --remote-debugging-port="$3" > "$log" 2>&1
  else
    ELECTRON_ENABLE_LOGGING=1 "$2" --remote-debugging-port="$3" > "$log" 2>&1 &
    pid=$!
  fi
  while [ $n -lt 25 ]; do
    sleep 1; n=$((n + 1))
    nc -z 127.0.0.1 "$3" 2> /dev/null && break
    [ -n "$pid" ] && ! kill -0 "$pid" 2> /dev/null && break
  done
  echo "dopo $n s: porta $3 $(nc -z 127.0.0.1 "$3" 2> /dev/null && echo aperta || echo chiusa), processi dell'app $(pgrep -f "$2" | wc -l | tr -d ' ')"
  if [ -n "$pid" ] && ! kill -0 "$pid" 2> /dev/null; then wait "$pid"; echo "il programma è uscito da solo, codice $?"; fi
  echo "ciò che ha scritto:"; tail -30 "$log" | cut -c1-400
  pkill -f "$2" 2> /dev/null; sleep 3
}
if [ "$failed" = 1 ] && [ -d /Applications/Claude.app ] && grep -q "^NO    claude" "$OUT/esito.txt"; then
  echo "### diagnosi di Claude"
  defaults read /Applications/Claude.app/Contents/Info CFBundleShortVersionString
  diagnose Claude /Applications/Claude.app/Contents/MacOS/Claude 9551 diretto
  diagnose Claude /Applications/Claude.app/Contents/MacOS/Claude 9551 open
  ls "$HOME/Library/Application Support/Claude" 2> /dev/null | head -20
  for f in "$HOME/Library/Logs/Claude/"*.log; do [ -f "$f" ] && { echo "--- $f"; tail -15 "$f" | cut -c1-300; }; done
fi

echo "--- registro di Omissis (ultime righe)"; tail -25 "$WORK/panel.log"
kill "$PANEL" 2> /dev/null
ls -la "$OUT"
exit $failed
