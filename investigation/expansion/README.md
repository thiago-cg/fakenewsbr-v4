# Pipeline de Expansão do FakenewsBR

Adiciona linhas ao `FakenewsBR_sanitized.csv` (v1) sem alterá-lo, com foco em
cobertura temporal pré/pós IA generativa, PT-PT e checadores, produzindo
`FakenewsBR_sanitized_v2.csv` + audit.

## Estado (2026-09-10)

- **v1 intacta** (verificada por hash a cada merge): 39.466 linhas.
- **v2 parcial** gerada durante a coleta; números finais em `audit_v2.md`.
- Testes offline: `27 passed`.
- LLM: `openai/gpt-5-nano:batch` (OpenRouter Batch). Submissão depende de
  `OPENROUTER_API_KEY` definida pelo usuário no ambiente.

## Estrutura

```
investigation/expansion/
├── schema.py             # 23 colunas + proveniência; ratings; derivações/métricas da v1
├── http.py               # PoliteSession (robots.txt, opt-out de IA, 1 req/s, backoff)
├── sources.py            # registro de fontes + whitelist do feed
├── collect_wp.py         # WP REST (checadores e portais), por ano
├── collect_sitemap.py    # G1 (/fato-ou-fake/) e Polígrafo
├── collect_feed.py       # feed ClaimReview (Data Commons) -> PT
├── collect_gfc.py        # Google Fact Check Tools claims:search (opcional; exige chave)
├── extract.py            # regras por fonte -> processed/records.jsonl
├── dedup.py              # exata + MinHash LSH
├── merge_and_audit.py    # v1 + novas -> FakenewsBR_sanitized_v2.csv + audit_v2.md
├── llm_batch.py          # OpenRouter Batch (dry-run/custo/submit/collect)
├── langchain_agent.py    # planejador (--planner rules|llm)
├── pipeline.py           # CLI unificado
├── tests/                # unittest offline
├── raw/ processed/ logs/ # gitignored
└── legacy/               # scripts obsoletos (wayback, rss, smoke), mantidos por reversibilidade
```

## Como rodar

```bash
# 1. Planejar (sem chave)
python -m investigation.expansion.pipeline plan --planner rules

# 2. Coletar (pode levar horas; logs em logs/)
python -m investigation.expansion.pipeline collect --pages-per-year 20
# ou por fonte:
python -m investigation.expansion.collect_wp --source boatos
python -m investigation.expansion.collect_sitemap --source g1 --from-year 2018
python -m investigation.expansion.collect_feed

# 3. Extrair + merge + auditoria
python -m investigation.expansion.pipeline extract
python -m investigation.expansion.pipeline merge --news-max-ratio 3

# 4. Testes
python -m unittest discover -s investigation/expansion/tests -t .

# 5. LLM (dry-run; submissão exige OPENROUTER_API_KEY no ambiente)
python -m investigation.expansion.pipeline llm-prepare
python -m investigation.expansion.pipeline llm-submit
python -m investigation.expansion.pipeline llm-collect
```

## Decisões de arquitetura

- **LLM**: `openai/gpt-5-nano:batch` no OpenRouter (Batch API, ~50 % off).
  Variante sem `:batch` para o agente interativo LangChain.
- **Google Fact Check Tools**: leitura via `claims:search` com
  `reviewPublisherSiteFilter`; o endpoint `pages` é CRUD da própria organização
  e não lê checagens de terceiros.
- **Ética**: não se faz scraping de conteúdo de sites com opt-out de IA no
  robots.txt (GPTBot/ClaudeBot/CCBot/Google-Extended). Esses entram só via feed
  ClaimReview (metadado).
- **Dedup**: exata + MinHash LSH (cosseno de shingles ≥ 0,90); precedência
  v1 > veredito > procedência > data mais antiga; conflitos em `conflicts_v2.csv`.
- **Comprimento**: linhas de procedência usam **manchete** como texto (evita
  recriar o atalho de comprimento).
- **Balanceamento**: cotas por era (`--news-max-ratio`), não ratio global.

## Composição da v2

Ver `audit_v2.md` / `audit_v2.json`. A v2 é sempre composta como
`[v1 intacta] + [linhas novas]`, com assert de hash da v1 e de unicidade de `rid`.

## Variáveis de ambiente

```bash
export OPENROUTER_API_KEY="..."          # LLM (OpenRouter)
export GOOGLE_FACTCHECK_API_KEY="..."    # opcional (collect_gfc.py)
```

Defina você mesmo no ambiente; não cole chaves no chat.

## Dependências

Já em uso: `requests`, `pandas`, `numpy`, `langchain`, `langchain-openai`.
Opcionais evitados de propósito: bs4/lxml/trafilatura (usa-se regex/`html.parser`),
pytest (usa-se `unittest`), sentence-transformers/faiss (dedup é MinHash+LSH).
