"""Publica o FakenewsBR v4 no Hugging Face Hub.

Pre-requisito (feito por voce, uma vez):
    hf auth login          # fluxo de navegador/device no seu terminal

Depois, na raiz deste repositorio:
    python publish_hf.py                 # usa <usuario_logado>/fakenewsbr-v4
    python publish_hf.py --repo usuario/nome

O script cria o dataset repo (se nao existir), sobe o README (card), os tres
CSVs de `data/` e o arquivo de licenca. Nao requer token em argumento: usa a
sessao salva pelo `hf auth login` (ou a variavel `HF_TOKEN` que VOCE definir no
ambiente).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import HfApi, create_repo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None,
                    help="repo_id no Hugging Face (padrao: <usuario_logado>/fakenewsbr-v4)")
    ap.add_argument("--private", action="store_true")
    a = ap.parse_args()

    api = HfApi()
    who = api.whoami()
    repo = a.repo or f"{who['name']}/fakenewsbr-v4"
    print(f"[hf] autenticado como {who['name']}")

    create_repo(repo, repo_type="dataset", exist_ok=True,
                private=a.private)
    print(f"[hf] repo dataset: {repo}")

    files = [
        ("README.md", "README.md"),
        ("LICENSE", "LICENSE"),
        ("LICENSE-DATA.md", "LICENSE-DATA.md"),
        ("SOURCES_AND_LICENSES.md", "SOURCES_AND_LICENSES.md"),
        ("data/FakenewsBR_v4_public.csv", "FakenewsBR_v4_public.csv"),
        ("data/FakenewsBR_v4_labels.csv", "FakenewsBR_v4_labels.csv"),
        ("data/FakenewsBR_v4_provenance.csv", "FakenewsBR_v4_provenance.csv"),
    ]
    for local, remote in files:
        p = Path(local)
        if not p.exists():
            print(f"[hf] AVISO: {local} nao existe, pulando")
            continue
        print(f"[hf] enviando {local} -> {remote} "
              f"({p.stat().st_size/1e6:.1f} MB)")
        api.upload_file(path_or_fileobj=str(p), path_in_repo=remote,
                        repo_id=repo, repo_type="dataset")
    print(f"[hf] pronto: https://huggingface.co/datasets/{repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
