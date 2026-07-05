#!/usr/bin/env bash
# Instalación de second-brain: entorno virtual, dependencias y configuración.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

echo "→ Creando entorno virtual (.venv)"
"$PYTHON" -m venv .venv
./.venv/bin/pip install --upgrade pip --quiet

echo "→ Instalando second-brain y dependencias"
./.venv/bin/pip install -e ".[dev]" --quiet

if [ ! -f .env ]; then
  cp .env.example .env
  echo "→ Creado .env — edítalo con tu TELEGRAM_BOT_TOKEN y tu user id"
fi

if ! command -v tesseract >/dev/null 2>&1; then
  echo "⚠ tesseract no está instalado: el OCR de imágenes quedará pendiente."
  echo "  macOS:  brew install tesseract tesseract-lang"
  echo "  Debian: sudo apt install tesseract-ocr tesseract-ocr-spa"
fi

echo ""
echo "✔ Instalación completa."
echo "  1. Edita .env (token de @BotFather + tu user id)"
echo "  2. source .venv/bin/activate"
echo "  3. second-brain run"
