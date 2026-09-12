---
language:
- pt
- pt-BR
- pt-PT
license: mit
license_name: mit
license_link: LICENSE
task_categories:
- text-classification
- text-retrieval
tags:
- fake-news
- misinformation
- disinformation
- fact-checking
- claim-verification
- portuguese
- pt-br
- pt-pt
- politics
- health
- social-media
- whatsapp
pretty_name: FakenewsBR v4
size_categories:
- 100K<n<1M
configs:
- config_name: default
  data_files:
  - split: train
    path: FakenewsBR_sanitized_v4.csv
dataset_info:
  features:
  - name: rid
    dtype: int64
  - name: dataset_name
    dtype: string
  - name: source_type
    dtype: string
  - name: source_description
    dtype: string
  - name: label
    dtype: string
  - name: date_iso
    dtype: string
  - name: url_review
    dtype: string
  - name: text
    dtype: string
  - name: text_clean
    dtype: string
  - name: text_no_url
    dtype: string
  - name: extracted_urls
    dtype: string
  - name: is_duplicated
    dtype: int64
  - name: is_null
    dtype: int64
  - name: too_short
    dtype: int64
  - name: factcheck_rating
    dtype: string
  - name: factcheck_claimant
    dtype: string
  - name: factcheck_url
    dtype: string
  - name: char_len
    dtype: int64
  - name: word_len
    dtype: int64
  - name: num_exclamations
    dtype: int64
  - name: num_questions
    dtype: int64
  - name: num_ellipsis
    dtype: int64
  - name: uppercase_word_ratio
    dtype: float64
  splits:
  - name: train
    num_examples: 291521
---

# FakenewsBR v4

> **Esta é a documentação de publicação do dataset. Antes de redistribuir, leia
> [`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md): as licenças das fontes
> originais ainda precisam de revisão jurídica para redistribuição pública.**

## TL;DR

- **291.521 linhas** em português (pt-BR + pt-PT), tarefa de classificação
  binária `fake` / `true`.
- Constrói sobre a v1 (`FakenewsBR_sanitized.csv`, 39.466 linhas), preservada
  byte a byte, e adiciona cobertura temporal, checadores, PT-PT e rótulos em
  camadas auditáveis.
- **Cada linha recebe uma camada de rótulo** (`label_tier` no arquivo
  `FakenewsBR_v4_labels.csv`); só as camadas verificadas alimentam o treino
  supervisionado.
- Pool de treino verificado: **85.212 linhas** (60.991 `fake` / 24.221 `true`).
  Nos grupos não degenerados: **36.896 linhas, razão 1,08:1**.
- Licenças, opt-out de IA e achados de PII: ver `SOURCES_AND_LICENSES.md`.

## Dataset Description

### Resumo

FakenewsBR reúne alegações, mensagens virais, checagens publicadas por agências
e manchetes sinceras de portais brasileiros e portugueses, normalizadas em um
esquema único de 23 colunas. O rótulo binário segue a convenção das agências de
checagem (`fake` cobre também vereditos "duros": enganoso, distorcido,
exagerado, fora de contexto), com o rating original preservado em
`factcheck_rating`.

A v4 foi desenhada para **dois usos distintos**:

1. **Treino/avaliação de classificadores de veracidade** usando apenas as
   linhas com rótulo verificado (checadores, checagem externa, correspondência
   com ClaimReview, verificação automática de alta confiança e corroboração).
2. **Avaliação out-of-distribution (OOD)** e estudos de cobertura de canais,
   eras e dialetos, usando as linhas `NEWS_*` (manchetes reais rotuladas
   `true` por procedência, não por checagem).

### Idiomas

- `pt-BR` (majoritário) e `pt-PT` (~20,7% das linhas novas; Polígrafo, ECO e
  Polígrafo via ClaimReview).
- Textos virais em português informal (WhatsApp, redes).

### Tarefa

Classificação binária de texto (`fake` vs `true`). O dataset também permite:
recuperação/matching de alegações contra checagens publicadas, verificação
seletiva com abstenção, análise temporal pré/pós-LLM e estudo de atalhos de
proveniência.

### Versão e histórico

| versão | linhas | notas |
|---|---:|---|
| v1 (`FakenewsBR_sanitized.csv`) | 39.466 | gerada com o framework [AKCIT-FN/fakenews-data](https://github.com/AKCIT-FN/fakenews-data) (MIT); base histórica do projeto |
| v2 | 215.640 | expansão: checadores, portais, G1, feed ClaimReview |
| v3 | 242.913 | + LIAR-BR e AVERITEC-BR traduzidos |
| **v4** | **291.521** | + Polígrafo PT-PT completo (~12,1 mil artigos), camadas de verificação consolidadas |

A v1 é **imutável e preservada integralmente** dentro da v4 (hashes de
conteúdo verificados a cada merge).

## Dataset Structure

### Arquivos

| arquivo | linhas | descrição |
|---|---:|---|
| `data/FakenewsBR_v4_public.csv` | 291.521 | **arquivo distribuído** — dataset principal, 23 colunas, PII mascarada |
| `data/FakenewsBR_v4_labels.csv` | 291.521 | camadas de rótulo e `train_label` (`label_tier`, `auto_label`, `confidence`, `method`, `evidence`) |
| `data/FakenewsBR_v4_provenance.csv` | 252.055 | proveniência das linhas novas (`rid`, `label_source`, `text_role`, `publisher`, `lang_variant`, `collector`, `source_url`, `collected_at`, `rating_norm`, `mentions_ai`) |
| `FakenewsBR_sanitized_v4.csv` | 291.521 | CSV de pesquisa completo (não distribuído; regenerável pelo pipeline deste repositório) |

> Os CSVs são versionados com **Git LFS**. Instale o LFS antes de clonar:
> `git lfs install && git clone <url>`; caso contrário você baixará apenas os
> ponteiros.

### Colunas (23, mesma ordem da v1)

| coluna | tipo | descrição |
|---|---|---|
| `rid` | int64 | identificador estável (`sha1` truncado para as linhas novas; 0…51.204 na v1) |
| `dataset_name` | str | grupo/origem (`FC_*` checadores, `NEWS_*` portais, `EXT_*` corpora externos, grupos da v1) |
| `source_type` | str | `news`, `news headline`, `social media post`, `whatsapp messages`, `tweets with only true info`, `brazilian news about politics` |
| `source_description` | str | descrição legível da origem |
| `label` | str | `fake` ou `true` |
| `date_iso` | str | data normalizada `AAAA-MM-DD` (quando disponível) |
| `url_review` | str | URL da checagem ou da matéria |
| `text` | str | texto original consolidado |
| `text_clean` | str | minúsculas, sem acento, sem emoji, espaços colapsados (derivado de `text_no_url`; 98,56% de paridade com a v1) |
| `text_no_url` | str | `text` sem URLs |
| `extracted_urls` | str | lista Python (`repr`) de URLs extraídas |
| `is_duplicated` / `is_null` / `too_short` | int64 | flags; **0 em todas as linhas** |
| `factcheck_rating` | str | rating original do checador ("Falso", "Errado", "Enganoso", "Verdadeiro"…) |
| `factcheck_claimant` | str | quem fez a alegação, quando disponível |
| `factcheck_url` | str | URL da checagem |
| `char_len` / `word_len` | int64 | comprimento sobre `text_clean` |
| `num_exclamations` / `num_questions` / `num_ellipsis` | int64 | pontuação em `text` |
| `uppercase_word_ratio` | float | fração de palavras em caixa alta (len ≥ 3) |

### Rótulo em camadas (`FakenewsBR_v4_labels.csv`)

O dataset bruto tem apenas `label ∈ {fake, true}`. A **força** do rótulo está no
arquivo de camadas:

| `label_tier` | linhas | significado |
|---|---:|---|
| `v1` | 39.466 | rótulo da base histórica |
| `checker` | 38.526 | veredito de checador (feed, WP REST, sitemap, G1) ou corpus externo checado |
| `checker_match` | 4.119 | correspondência ≥ 0,9 com ClaimReview (concordante) |
| `llm_local` | 3.092 | verificação automática com evidência e confiança ≥ 0,8 (LLM local 2B) |
| `corroborated` | 9 | ≥ 3 portais reputáveis independentes |
| `provenance` | 206.309 | **sem verificação**: manchetes `true` por procedência (`NEWS_*`) |

`train_label` é `fake`/`true` apenas para as camadas verificadas (85.212 linhas;
60.991 fake, 24.221 true). As 206.309 linhas `provenance` **não** têm rótulo de
treino e devem ser usadas como OOD.

### Exemplo (linha do grupo `FC_POLIGRAFO`)

```json
{
  "rid": 834297301234567890,
  "dataset_name": "FC_POLIGRAFO",
  "source_type": "news",
  "source_description": "poligrafo",
  "label": "fake",
  "date_iso": "2021-03-15",
  "url_review": "https://poligrafo.sapo.pt/fact-check/...",
  "text": "Dívida pública portuguesa alcançou \"recorde absoluto\" de 268,8% do PIB em 2020?",
  "factcheck_rating": "Falso",
  "label_tier": "checker"
}
```

### Estatísticas

- **Rótulo (dataset completo):** `true` 230.530 (79,1%), `fake` 60.991 (20,9%).
- **Rótulo (linhas novas):** `true` 219.300, `fake` 32.755.
- **Eras (linhas novas):** ≤2017 31.509; 2018–nov/2022 115.232; dez/2022+ 98.219; sem data 7.095.
- **Dialeto:** PT-PT 52.207 linhas novas (20,7%).
- **Menções a IA/deepfake/ChatGPT:** 1.215 linhas novas.
- **Comprimento (`text` novo):** p50 72 / p95 125 caracteres; `word_len` p50 12.
- **Maiores grupos:** `NEWS_PODER360` 77.273; `NEWS_BRASILDEFATO` 76.219; `NEWS_ECO` 41.362; `fakes` 20.347; `NEWS_OECO` 14.602; `FC_POLIGRAFO` 10.831; `FC_BOATOS` 10.774; `Fake.br` 7.160; `EXT_LIARBR` 6.996; `FakeWhatsApp.BR_2018` 6.381.

## Dataset Creation

### Fontes

Detalhamento, URLs, licenças e status de opt-out em
[`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md). Resumo:

- **Checadores (veredito):** Boatos.org, E-farsas, Coletivo Bereia, G1 Fato ou
  Fake, Polígrafo (PT-PT), e metadados ClaimReview (Lupa, Comprova, Folha, SBT,
  Nexo) via [Data Commons](https://datacommons.org/).
- **Portais (manchetes `true` por procedência):** Poder360, Brasil de Fato,
  O Eco, ECO (PT-PT).
- **Corpora externos checados:** LIAR-BR e AVERITEC-BR (traduções PT-BR do
  STIL 2025; grupos `EXT_LIARBR` / `EXT_AVERITECBR`).
- **Base histórica (v1):** Fake.br, COVID19.BR, MuMiN-PT, FakeWhatsApp.BR_2018,
  LLM4BR_300, Kaggle `fakes-news-portuguese`.

### Coleta

- WP REST (`/wp-json/wp/v2`), sitemaps (G1, Polígrafo) e feed ClaimReview.
- `robots.txt` respeitado; **não** se faz scraping de conteúdo de sites cujo
  `robots.txt` bloqueia robôs de treino de IA (GPTBot/ClaudeBot/CCBot/
  Google-Extended). Esses publishers entram apenas via metadado ClaimReview.
- Rate-limit por host; retry/backoff; UA identificável
  (`FakenewsBR-research/2.0`).

### Limpeza e deduplicação

- Métricas idênticas ao gerador da v1 (paridade verificada nas 39.466 linhas).
- Deduplicação exata normalizada + quase-duplicata (MinHash LSH, Jaccard ≥ 0,90
  confirmada), precedência `v1 > veredito > procedência > data`; conflitos
  registrados (`conflicts_v2.csv`).
- A v1 é copiada intacta; um assert de hash a cada merge impede alterações.

### Rotulagem

- `fake` inclui ratings "hard" (Enganoso, Distorcido, Fora de Contexto,
  Exagerado…), seguindo a convenção da v1.
- Ratings sem veredito claro (Explica, Contextualizando, Indeterminado…) são
  descartados.
- Verificação automática: LLM local servida por **llama.cpp** (backend GGUF do
  Unsloth Studio), modelo **`openbmb/MiniCPM5-2B-GGUF`** (2B parâmetros,
  raciocínio desligado via `chat_template_kwargs.enable_thinking=false`), com
  evidência do Google News RSS. O prompt exige ≥ 2 fontes independentes para
  `true`, refutação explícita para `fake` e **abstenção** (`unknown`) caso
  contrário. Abstenções **não** viram rótulo: a linha mantém a camada original e
  fica fora do treino.

## Uses

### Usos pretendidos

- Treinar e avaliar classificadores de desinformação em português.
- Pesquisa em verificação de fatos, recuperação de evidência e calibração.
- Avaliação OOD por canal (checador, portal, viral), era e dialeto.
- Estudo de atalhos (proveniência, comprimento) e robustez.

### Usos fora de escopo

- **Não** usar `NEWS_*` (camada `provenance`) como verdade factual: são
  manchetes publicadas, não alegações verificadas.
- **Não** usar o dataset como oráculo de verdade nem para moderação automática
  sem revisão humana.
- **Não** inferir que uma pessoa citada mentiu; os rótulos são sobre trechos de
  texto.
- **Não** usar para vigilância, perfilamento ou propaganda direcionada.

### Como treinar (receita de referência)

```python
from models import data
d = data.load(csv="data/FakenewsBR_v4_public.csv",
              labels_csv="data/FakenewsBR_v4_labels.csv")   # 85.212 linhas
# grupos informativos (uso da cabeça DFR): is_balanced_group -> 36.896, 1,08:1
w = data.group_balanced_weights(d)
```

Recomendações metodológicas:
1. Excluir `NEWS_*`/`provenance` do treino supervisionado.
2. Criar splits por **cluster de quase-duplicata** (GroupKFold) — o split IID
   infla a métrica do WhatsApp em ~20 pontos.
3. Calibrar na validação balanceada (melhora o subset `true` de 0,19 → 0,64 e o
   ECE de 0,049 → 0,028 sem retreino).
4. Reportar pior-grupo, macro-F1 e AUC por checador, não só acurácia.

## Considerations for Using the Data

### Viés e limitações conhecidas

- **Confundimento origem↔rótulo**: na v1, 58,4% das linhas estão em grupos
  degenerados (uma classe), e a origem determina o rótulo. Mitigar com splits
  por grupo e pesos.
- **Desequilíbrio**: o dataset bruto é 79% `true` (por causa das manchetes);
  o pool verificado é 72% `fake`; os grupos informativos ficam em 1,08:1.
- **Ruído de rótulo**: 210 linhas da v1 têm `factcheck_rating` contradizendo o
  rótulo (39 no teste).
- **Vazamento por quase-duplicata**: 41,4% do teste de `FakeWhatsApp.BR_2018`
  tem quase-duplicata no treino em split IID (por isso a exigência de clusters).
- **Dialeto**: o "gap PT-PT" desaparece quando se controla o checador (AUC
  Polígrafo 0,71 vs Lupa 0,68) — não atribuir a diferenças de desempenho ao
  tokenizer sem controle.
- **Rotulagem automática**: `llm_local` (3.092) usa modelo de 2B e **não foi
  auditada**; manter em camada separada e rodar ablação com/sem.
- **Dados traduzidos**: `EXT_LIARBR`/`EXT_AVERITECBR` vêm de inglês (PolitiFact,
  50 organizações), com distribuição diferente do Brasil; usar ablação.
- **Datas**: 7.095 linhas novas sem data; datas mínimas incluem outliers
  (herança de fontes históricas).

### Conteúdo sensível e PII

- O dataset contém **desinformação real** (saúde, política, violência) e
  linguagem ofensiva; use com cautela em contextos educacionais.
- **Auditoria de PII (medida):** ocorrências mascaradas na variante pública:
  **705 e-mails, 3 CPFs e 3.106 strings tipo telefone**. A variante
  **`FakenewsBR_v4_public.csv`** é gerada por
  `investigation/expansion/scrub_pii.py` (mesmas 291.521 linhas e distribuição
  de rótulo); o CSV de pesquisa permanece sem alteração para reprodutibilidade.
  Recomenda-se publicar a variante pública e manter a íntegra apenas para
  pesquisa mediante solicitação.
- Nomes de figuras públicas aparecem como parte das alegações (esperado em
  fact-checking).

### Licenciamento

- **Código** deste repositório: **MIT** (arquivo [`LICENSE`](LICENSE)).
- **Compilação, curadoria, anotações e camadas de rótulo** produzidas pelos
  autores: **MIT** — uso, cópia, modificação e redistribuição permitidos, com
  atribuição e sem garantia.
- **Conteúdo de terceiros** incluído no dataset (textos de checadores e
  portais, corpora históricos, traduções LIAR/AveriTeC): permanece sob os
  termos das fontes originais, detalhados em
  [`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md). A licença MIT do
  projeto **não substitui** esses termos; para redistribuição comercial,
  revise os itens marcados com ⚠️.

## Additional Information

### Como reproduzir a v4 (código)

```bash
# 1) coleta (sem chave)
python -m investigation.expansion.collect_feed
python -m investigation.expansion.collect_wp --source boatos
python -m investigation.expansion.collect_wp --source efarsas
python -m investigation.expansion.collect_wp --source bereia
python -m investigation.expansion.collect_wp --source poder360 --pages-per-year 60
python -m investigation.expansion.collect_wp --source brasildefato --pages-per-year 60
python -m investigation.expansion.collect_wp --source oeco
python -m investigation.expansion.collect_wp --source eco
python -m investigation.expansion.collect_sitemap --source g1 --from-year 2018
python -m investigation.expansion.collect_sitemap --source poligrafo --workers 4 --delay 0.6

# 2) corpora externos e extracao
python -m investigation.expansion.ingest_external
python -m investigation.expansion.extract

# 3) merge (v1 intacta) + auditoria
python -m investigation.expansion.merge_and_audit --news-max-ratio 6 \
  --extra investigation/expansion/processed/records_ext_liarbr.jsonl \
          investigation/expansion/processed/records_ext_averitecbr.jsonl \
  --out FakenewsBR_sanitized_v4.csv --provenance FakenewsBR_v4_provenance.csv

# 4) camadas de rotulo
python -m investigation.expansion.apply_verification \
  --base FakenewsBR_v4_provenance.csv --v2 FakenewsBR_sanitized_v4.csv \
  --out FakenewsBR_v4_labels.csv
```

Módulos principais: `investigation/expansion/` (`schema`, `http`, `sources`,
`collect_*`, `extract`, `dedup`, `merge_and_audit`, `local_label`,
`apply_verification`, `judge_v2`), `models/` (treino/avaliação),
`sanitize_dataset.py` (geração da v1). Testes: 28 em
`investigation/expansion/tests/`.

### Citação

```bibtex
@misc{fakenewsbr_v4,
  title  = {FakenewsBR v4: A Portuguese Dataset for Misinformation Detection
            and Claim Verification},
  author = {Thiago C. G. and contributors},
  year   = {2026},
  note   = {291,521 rows; layers: checker, checker\_match, llm\_local,
            corroborated, provenance},
  url    = {https://github.com/thiago-cg/FakenewsBR}
}
```

### Manutenção e contato

- Repositório: https://github.com/thiago-cg/FakenewsBR
- Issues para erros de dados, PII e pedidos de remoção.
- Changelog: v1 (39.466) → v2 (215.640) → v3 (242.913) → v4 (291.521).
