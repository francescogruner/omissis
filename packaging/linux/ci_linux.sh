#!/bin/bash
# Tutte le prove di Omissis su Linux, dalla radice del repository, da un utente normale (non root):
#   bash packaging/linux/ci_linux.sh <versione> [cartella dei pesi di omissis-small]
# 1. costruisce il programma (dist/Omissis.app) e l'archivio, e controlla che il pannello risponda;
# 2. la serie comune a Mac e Linux (packaging/mac/ci_tests.sh): archivio, proxy, gateway, plugin, documenti, aggiornamenti;
# 3. la prova di Linux (linux_test.py): installatore, menu, avvio all'accesso, chiusura, cestino, disinstallazione.
# Con la cartella dei pesi il modello non viene scaricato (540 MB) e la prova di Linux accende anche la protezione.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${1:?versione (per esempio 0.1.7)}"
MODEL="${2:-}"
cd "$ROOT"
failed=0
echo "=================== costruzione"
# OMISSIS_SKIP_BUILD=1: si usa il programma gia' costruito in dist/ (per rilanciare solo le prove)
[ -n "${OMISSIS_SKIP_BUILD:-}" ] || python3 packaging/linux/build_linux.py --version "$VERSION" --smoke-test || exit 1
echo "=================== prove comuni"
export RUNNER_TEMP="${RUNNER_TEMP:-$(mktemp -d)}"
if [ -n "$MODEL" ]; then
  mkdir -p "$RUNNER_TEMP/omissis-ci/data/models"
  ln -sfn "$MODEL" "$RUNNER_TEMP/omissis-ci/data/models/omissis-small"
fi
bash packaging/mac/ci_tests.sh || failed=1
echo "=================== aggiornamenti"
# le parti che valgono anche su Linux; le altre (spostamento in Applicazioni, voce di login del Mac) sono del Mac
dist/Omissis.app/Contents/Resources/python/bin/python3 packaging/mac/update_test.py update rollback auto || failed=1
echo "=================== Linux"
python3 packaging/linux/linux_test.py ${MODEL:+--model "$MODEL"} || failed=1
[ $failed = 0 ] && echo "TUTTO BENE" || echo "### QUALCOSA NON È PASSATO"
exit $failed
