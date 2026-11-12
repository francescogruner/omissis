# -*- coding: utf-8 -*-
"""Scarica i pesi del modello da Hugging Face nella cartella models\\<nome>.

  model\\.venv\\Scripts\\python model\\download_model.py [omissis-small | omissis-base]

omissis-small (537 MB) e' piu' leggero, omissis-base (1,2 GB) piu' preciso.
"""
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

AUTORE = "francescogruner"
NOMI = ("omissis-small", "omissis-base")

if __name__ == "__main__":
    nome = sys.argv[1] if len(sys.argv) > 1 else "omissis-small"
    if nome not in NOMI:
        sys.exit(f"modello sconosciuto: {nome}. Scegliere tra {', '.join(NOMI)}")
    dove = Path(__file__).resolve().parent / "models" / nome
    snapshot_download(repo_id=f"{AUTORE}/{nome}", local_dir=dove)
    print(f"modello scaricato in {dove}")
    if nome != "omissis-base":
        print("Nel pannello, sezione Impostazioni, scegliere questo modello e salvare.")
