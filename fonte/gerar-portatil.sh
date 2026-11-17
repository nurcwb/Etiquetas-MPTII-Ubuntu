#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m PyInstaller --noconfirm --onedir \
  --name Etiquetas-MPTII --distpath dist --workpath build --specpath build \
  --hidden-import PIL._tkinter_finder --hidden-import PIL._imagingtk \
  --add-data "$PWD/icone.png:." --add-data "$PWD/fonts:fonts" \
  "$PWD/etiquetas.py"
cp icone.png instalar.sh LEIA-ME.txt dist/Etiquetas-MPTII/
chmod +x dist/Etiquetas-MPTII/instalar.sh
printf '\nVersão gerada em dist/Etiquetas-MPTII. Nenhum compactado foi criado.\n'
