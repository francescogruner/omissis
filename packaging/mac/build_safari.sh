#!/bin/bash
# Prova dell'estensione per Safari. Converte l'estensione dei browser (app/extension) in un progetto Xcode e lo compila
# con la firma «solo per questo Mac». Serve un Mac con Xcode.
#
#   bash packaging/mac/build_safari.sh     -> dist/safari/Omissis-Safari-prova.zip e dist/safari/conversione.log
#
# NON produce un'estensione da dare agli utenti: per quello servono un Developer ID di Apple e la notarizzazione
# (da Safari 18.4 le estensioni firmate così si installano anche fuori dall'App Store).
# Per provarla su un Mac: Safari > Impostazioni > Avanzate > «Mostra funzionalità per sviluppatori web»; poi
# Sviluppo > «Consenti estensioni non firmate» (Safari lo richiede a ogni avvio); aprire l'app una volta e accendere
# l'estensione in Safari > Impostazioni > Estensioni.
#
# conversione.log dice quali voci del manifest lo strumento di Apple non riconosce: è la prima cosa da leggere.
# Il 20/11/2026 (Xcode 26.6) segnalava «world» e «match_origin_as_fallback». Il codice di Safari però le legge
# (WebKit, WebExtension.cpp): l'avviso da solo non basta, va provato in un Safari vero.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="Omissis Safari"
ID="eu.omissis.safari"
OUT="$REPO/dist/safari"
mkdir -p "$OUT"

{
  echo "### versioni"
  echo "macOS $(sw_vers -productVersion)"
  xcodebuild -version | sed -n 1p
  echo "Safari $(defaults read /Applications/Safari.app/Contents/Info CFBundleShortVersionString 2>/dev/null || echo '?')"
  echo "### conversione"
  xcrun safari-web-extension-converter "$REPO/app/extension" \
    --project-location "$OUT" --app-name "$NAME" --bundle-identifier "$ID" \
    --swift --macos-only --copy-resources --no-open --no-prompt --force 2>&1
} | tee "$OUT/conversione.log"

PROJECT="$OUT/$NAME/$NAME.xcodeproj"
[ -d "$PROJECT" ] || { echo "ERRORE: il progetto Xcode non è stato creato"; exit 1; }

# Lo strumento di Apple dà all'app un identificativo suo (eu.omissis.Omissis-Safari) invece di quello chiesto. Così
# quello dell'estensione (eu.omissis.safari.Extension) non comincia più con quello dell'app, e Xcode si ferma con
# «Embedded binary's bundle identifier is not prefixed with the parent app's bundle identifier».
# Qui l'app prende l'identificativo chiesto; quello dell'estensione resta com'è.
perl -pi -e 's/(PRODUCT_BUNDLE_IDENTIFIER = )(?!"?\Q'"$ID"'\E\.Extension)"?[^";]+"?;/${1}'"$ID"';/' "$PROJECT/project.pbxproj"
echo "### identificativi"
grep -h -o 'PRODUCT_BUNDLE_IDENTIFIER = [^;]*' "$PROJECT/project.pbxproj" | sort | uniq -c | tee -a "$OUT/conversione.log"

SCHEME="$(xcodebuild -list -json -project "$PROJECT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["project"]["schemes"][0])')"

echo "### compilazione ($SCHEME)"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release -derivedDataPath "$OUT/build" \
  CODE_SIGN_IDENTITY="-" CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM="" build 2>&1 | tail -40

APP="$(find "$OUT/build/Build/Products/Release" -maxdepth 1 -name "*.app" | sed -n 1p)"
[ -n "$APP" ] && [ -d "$APP/Contents/PlugIns" ] || { echo "ERRORE: l'app con l'estensione non è stata costruita"; exit 1; }
echo "### estensione dentro l'app"
ls "$APP/Contents/PlugIns"
APPEX="$(find "$APP/Contents/PlugIns" -maxdepth 1 -name "*.appex" | sed -n 1p)"
codesign --verify --deep --verbose=1 "$APP" 2>&1 | tail -2
echo "file dell'estensione: $(find "$APPEX/Contents/Resources" -type f | wc -l | tr -d ' ')"
python3 -c 'import json, sys; m = json.load(open(sys.argv[1])); print("manifest:", m["manifest_version"], m["version"], "| permessi:", ", ".join(m.get("permissions", [])))' "$APPEX/Contents/Resources/manifest.json"
ditto -c -k --keepParent "$APP" "$OUT/Omissis-Safari-prova.zip"
echo "FATTO: $OUT/Omissis-Safari-prova.zip"
