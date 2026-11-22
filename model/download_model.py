# -*- coding: utf-8 -*-
"""Scarica i pesi del modello da Hugging Face nella cartella models\\<nome>.

  model\\.venv\\Scripts\\python model\\download_model.py [omissis-light | omissis-small | omissis-base]

omissis-light (90 MB, solo ONNX) e' quello che il programma usa di serie; omissis-small (563 MB) e
omissis-base (1,2 GB) sono i modelli interi, anche per PyTorch.
"""
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

AUTORE = "francescogruner"
NOMI = ("omissis-light", "omissis-small", "omissis-base")

if __name__ == "__main__":
    nome = sys.argv[1] if len(sys.argv) > 1 else "omissis-light"
    if nome not in NOMI:
        sys.exit(f"modello sconosciuto: {nome}. Scegliere tra {', '.join(NOMI)}")
    dove = Path(__file__).resolve().parent / "models" / nome
    snapshot_download(repo_id=f"{AUTORE}/{nome}", local_dir=dove)
    print(f"modello scaricato in {dove}")
    print("Nel pannello, nelle impostazioni, si sceglie quale modello usare.")
