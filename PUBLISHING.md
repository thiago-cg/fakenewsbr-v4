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

Conta autenticada via `hf auth login` (nesta maquina: **`titoverso`**). O
`README.md` deste repositorio ja e o **dataset card** (YAML valido com
`dataset_info`, features e split). O jeito mais simples e usar o script:

```bash
python publish_hf.py            # cria <usuario_logado>/fakenewsbr-v4 e sobe tudo
# ou, manualmente:
hf repo create titoverso/fakenewsbr-v4 --repo-type dataset
hf upload titoverso/fakenewsbr-v4 README.md --repo-type dataset
hf upload titoverso/fakenewsbr-v4 data/FakenewsBR_v4_public.csv data/ --repo-type dataset
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

- [ ] Rodar a validacao das `NEWS_*` (ver `PLANO_VALIDACAO_NEWS.md`) e anexar o
      relatorio/tiers; sem isso, nao afirmar veracidade das linhas `press_true`.
- [ ] Resolver os itens ⚠️ de `SOURCES_AND_LICENSES.md` (licencas de
      checadores, portais, traducoes LIAR/AveriTeC, LLM4BR_300, Kaggle) antes
      de uso comercial do conteudo de terceiros.
- [ ] Confirmar que a variante publica (PII mascarada) e a que sera distribuida.
- [x] Licenca definida: MIT permissiva para codigo e compilacao (`LICENSE`).
- [ ] Adicionar tags/descricao no HF e no GitHub (fake-news, pt-BR, pt-PT).
- [ ] Citar fontes e o framework AKCIT-FN nos materiais de divulgacao.
