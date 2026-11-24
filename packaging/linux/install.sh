#!/bin/sh
# Omissis per Linux: installazione per l'utente che lancia questo script. Non chiede diritti di amministratore.
# Omissis for Linux: installs for the user who runs this script. It does not ask for administrator rights.
#
#   sh install.sh                                   scarica l'ultima versione e la installa / downloads the latest version
#   sh install.sh Omissis-0.1.12-linux-x86_64.tar.gz installa da un archivio gia' scaricato / installs a downloaded archive
#
# Mette il programma in ~/.local/lib/omissis (oppure in $OMISSIS_HOME) e lo avvia. Al primo avvio Omissis aggiunge da solo
# la voce nel menu delle applicazioni, il comando «omissis» e l'avvio all'accesso, che si spegne dal pannello. I dati di
# chi lo usa stanno in ~/.local/share/omissis e questo script non li tocca: rilanciarlo aggiorna il programma e basta.
# Per toglierlo: pannello > Impostazioni > «Togli Omissis da questo computer».
#
#   OMISSIS_NO_START=1    installa senza avviare / install without starting
#   OMISSIS_HOME=<dir>    un'altra cartella per il programma / another folder for the program
set -eu

ORIGIN="${OMISSIS_UPDATES_URL:-https://github.com/francescogruner/omissis/releases/latest/download}"
DEST="${OMISSIS_HOME:-$HOME/.local/lib/omissis}"

case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in it*) ITALIAN=1 ;; *) ITALIAN=0 ;; esac
say() { if [ "$ITALIAN" = 1 ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }
fail() { say "Omissis: $1" "Omissis: $2" >&2; exit 1; }

[ "$(uname -s)" = Linux ] || fail "questo installatore è per Linux." "this installer is for Linux."
case "$(uname -m)" in
  x86_64|amd64) ARCH=x86_64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) fail "processore non previsto: $(uname -m)." "unsupported processor: $(uname -m)." ;;
esac
[ "$(id -u)" -ne 0 ] || fail "non lanciarlo come root, né con sudo: Omissis si installa per l'utente che lo usa." \
                             "do not run it as root or with sudo: Omissis installs for the user who uses it."
command -v tar > /dev/null 2>&1 || fail "manca il comando tar." "the tar command is missing."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
trap 'exit 1' INT TERM

fetch() {   # indirizzo, file
  if command -v curl > /dev/null 2>&1; then
    curl -fL --retry 2 -o "$2" "$1"
  elif command -v wget > /dev/null 2>&1; then
    wget -O "$2" "$1"
  else
    fail "serve curl oppure wget." "curl or wget is needed."
  fi
}

if [ $# -ge 1 ]; then
  PACKAGE="$1"
  [ -f "$PACKAGE" ] || fail "non trovo $PACKAGE." "cannot find $PACKAGE."
else
  say "Cerco l'ultima versione di Omissis…" "Looking for the latest Omissis version…"
  fetch "$ORIGIN/update-linux-$ARCH.json" "$TMP/sheet.json" || fail "non riesco a leggere la pagina delle versioni." "cannot read the releases page."
  FILE="$(sed -n 's/^ *"file": *"\([^"]*\)".*$/\1/p' "$TMP/sheet.json" | head -n 1)"
  SUM="$(sed -n 's/^ *"sha256": *"\([0-9a-f]*\)".*$/\1/p' "$TMP/sheet.json" | head -n 1)"
  case "$FILE" in
    Omissis-*-linux-"$ARCH".tar.gz) ;;
    *) fail "la pagina delle versioni non ha ancora un pacchetto per questo computer." "the releases page has no package for this computer yet." ;;
  esac
  say "Scarico $FILE…" "Downloading $FILE…"
  fetch "$ORIGIN/$FILE" "$TMP/$FILE" || fail "lo scaricamento non è riuscito." "the download failed."
  if command -v sha256sum > /dev/null 2>&1; then
    [ "$(sha256sum "$TMP/$FILE" | cut -d' ' -f1)" = "$SUM" ] || fail "il file scaricato non è quello pubblicato (impronta diversa): riprova." \
                                                                      "the downloaded file is not the published one (different checksum): try again."
  fi
  PACKAGE="$TMP/$FILE"
fi

say "Installo in $DEST…" "Installing into $DEST…"
mkdir -p "$DEST"
NEW="$DEST/.nuova"
rm -rf "$NEW"
mkdir "$NEW"
tar -xzf "$PACKAGE" -C "$NEW" || { rm -rf "$NEW"; fail "l'archivio non si scompatta." "the archive cannot be unpacked."; }
BIN="$NEW/Omissis.app/Contents/MacOS/Omissis"
PY="$NEW/Omissis.app/Contents/Resources/python/bin/python3"
[ -x "$BIN" ] && [ -x "$PY" ] || { rm -rf "$NEW"; fail "l'archivio non contiene Omissis." "the archive does not contain Omissis."; }
# la versione nuova deve partire su questo computer PRIMA di prendere il posto di quella che c'è
if ! "$PY" -I -B -c 'import ssl, sqlite3, onnxruntime, tokenizers, mitmproxy.version' > /dev/null 2>&1; then
  rm -rf "$NEW"
  fail "su questo computer il programma non parte: serve una distribuzione a 64 bit recente almeno quanto Ubuntu 22.04, Debian 12 o Fedora 36." \
       "the program does not start on this computer: it needs a 64-bit distribution at least as recent as Ubuntu 22.04, Debian 12 or Fedora 36."
fi

if [ -d "$DEST/Omissis.app" ]; then   # una versione di prima: si chiude, e resta da parte finché la nuova non è al suo posto
  "$DEST/Omissis.app/Contents/MacOS/Omissis" --quit > /dev/null 2>&1 || true
  rm -rf "$DEST/Omissis.app.old"
  mv "$DEST/Omissis.app" "$DEST/Omissis.app.old"
fi
if ! mv "$NEW/Omissis.app" "$DEST/Omissis.app"; then
  [ -d "$DEST/Omissis.app.old" ] && mv "$DEST/Omissis.app.old" "$DEST/Omissis.app"
  rm -rf "$NEW"
  fail "non riesco a scrivere in $DEST." "cannot write into $DEST."
fi
rm -rf "$NEW" "$DEST/Omissis.app.old"

BIN="$DEST/Omissis.app/Contents/MacOS/Omissis"
if [ "${OMISSIS_NO_START:-}" = 1 ]; then
  say "Omissis è installato. Per avviarlo: $BIN" "Omissis is installed. To start it: $BIN"
  exit 0
fi
if command -v setsid > /dev/null 2>&1; then
  setsid "$BIN" > /dev/null 2>&1 < /dev/null &
else
  nohup "$BIN" > /dev/null 2>&1 < /dev/null &
fi
say "Omissis è installato e si sta aprendo nel browser. Da ora lo trovi nel menu delle applicazioni; da terminale: omissis" \
    "Omissis is installed and is opening in your browser. From now on you find it in the applications menu; from a terminal: omissis"
