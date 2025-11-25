#!/usr/bin/env bash
#
# rename_dates.sh — vereinheitlicht Verzeichnisnamen im Format YYYYMMDD[_suffix]
# zu YYYY-MM-DD[_suffix].
#
# Nutzung:
#   ./rename_dates.sh [--apply] [VERZEICHNIS]
#
# Optionen:
#   --apply      Führe die tatsächliche Umbenennung durch (Standard: Testlauf)
#   VERZEICHNIS  Wurzelverzeichnis (Standard: aktuelles Verzeichnis)

set -e

APPLY=false
TARGET_DIR="."

# Argumente auswerten
if [[ "$1" == "--apply" ]]; then
  APPLY=true
  shift
fi
if [[ -n "$1" ]]; then
  TARGET_DIR="$1"
fi

echo "📁 Scanne: $TARGET_DIR"
if $APPLY; then
  echo "🚨 Modus: ECHTE UMBENENNUNG (Dateien werden geändert!)"
else
  echo "🧪 Modus: TESTLAUF (keine Änderungen)"
fi
echo

# Schleife über alle Unterverzeichnisse (eine Ebene)
find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -type d | while read -r dir; do
  base=$(basename "$dir")

  # Prüfen auf Muster YYYYMMDD oder YYYYMMDD_suffix
  if [[ "$base" =~ ^([0-9]{4})([0-9]{2})([0-9]{2})(.*)$ ]]; then
    year="${BASH_REMATCH[1]}"
    month="${BASH_REMATCH[2]}"
    day="${BASH_REMATCH[3]}"
    suffix="${BASH_REMATCH[4]}"
    newname="${year}-${month}-${day}${suffix}"

    # Nur umbenennen, wenn sich der Name wirklich ändert
    if [[ "$base" != "$newname" ]]; then
      echo "→ $base  ➜  $newname"
      if $APPLY; then
        mv -i "$dir" "$(dirname "$dir")/$newname"
      fi
    fi
  fi
done

echo
if $APPLY; then
  echo "✅ Umbenennung abgeschlossen."
else
  echo "✅ Testlauf beendet — keine Änderungen vorgenommen."
  echo "   (Führe mit '--apply' aus, um die Änderungen wirklich vorzunehmen.)"
fi
