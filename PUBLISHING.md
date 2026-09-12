# Publicacao

## GitHub (este repositorio)

O repositorio ja esta commitado localmente com os CSVs no **Git LFS**.

```bash
# 1) criar o repositorio remoto (uma vez)
gh repo create thiago-cg/fakenewsbr-v4 --public --source=. --remote=origin --push
# ou, manualmente:
git remote add origin git@github.com:thiago-cg/fakenewsbr-v4.git
git push -u origin main
```

Verificacoes pos-push:
- os tres CSVs aparecem como `LFS` no GitHub;
- o README renderiza o card (YAML frontmatter + secoes);
- `LICENSE` (codigo, MIT) e `LICENSE-DATA.md` (dados, `other`) visiveis.

## Hugging Face

O `README.md` deste repositorio ja e o **dataset card** (YAML valido com
`dataset_info`, features e split). Para publicar:

```bash
pip install -U huggingface_hub
hf auth login

# criar o dataset repo
hf repo create thiago-cg/fakenewsbr-v4 --repo-type dataset

# subir card + dados (o README vira o card; os CSVs vao por LFS do HF)
hf upload thiago-cg/fakenewsbr-v4 README.md --repo-type dataset
hf upload thiago-cg/fakenewsbr-v4 data/FakenewsBR_v4_public.csv data/ --repo-type dataset
```

Sugestao de arquivos no HF:
- `FakenewsBR_v4_public.csv` (principal)
- `FakenewsBR_v4_labels.csv`
- `FakenewsBR_v4_provenance.csv`

No card, ajuste o bloco `configs`/`dataset_info` se o nome do arquivo no HF
for outro. Exemplo de carregamento:

```python
from datasets import load_dataset
ds = load_dataset("thiago-cg/fakenewsbr-v4", data_files="FakenewsBR_v4_public.csv")
```

## Checklist antes de tornar publico

- [ ] Resolver os itens ⚠️ de `SOURCES_AND_LICENSES.md` (licencas de
      checadores, portais, traducoes LIAR/AveriTeC, LLM4BR_300, Kaggle).
- [ ] Confirmar que a variante publica (PII mascarada) e a que sera distribuida.
- [ ] Definir a licenca dos dados apos a revisao (atualmente `license: other`).
- [ ] Adicionar tags/descricao no HF e no GitHub (fake-news, pt-BR, pt-PT).
- [ ] Citar fontes e o framework AKCIT-FN nos materiais de divulgacao.
