# Resultados da execução noturna (2026-09-12)

Execução autônoma da Fase 0 + Fase 2 (LLM local) do
`PLANO_ROTULAGEM_FINETUNING.md`. Nada foi commitado.

## 1. Artefatos gerados

| artefato | conteúdo |
|---|---|
| `FakenewsBR_sanitized_v4.csv` | **291.521 linhas** (v1 39.466 intacta + 252.055 novas), 23 colunas, juiz OK |
| `FakenewsBR_v4_provenance.csv` | proveniência das 252.055 novas (252.055 linhas) |
| `FakenewsBR_v4_labels.csv` | **291.521 linhas com camadas de rótulo** e `train_label` |
| `investigation/expansion/audit_v4.md` | auditoria de composição |
| `investigation/expansion/v4_quality_report.md` | juiz (conformidade) |
| `investigation/expansion/labels_v4_report.md` | contagem por camada |
| `investigation/expansion/processed/records_ext_*.jsonl` | LIAR-BR 7.010 + AVERITEC-BR 3.017 |
| `investigation/expansion/raw/poligrafo.jsonl` | 12.120 artigos PT-PT coletados (+11.420 linhas extraídas) |
| `investigation/expansion/processed/local_verify_results.jsonl` | 11.640 veredictos da LLM local |

Qualidade: v1 intacta (hash), flags 0, `word_len>=3`, 0 vazamento léxico em
manchetes `true`, paridade `text_clean` com a v1 em 98,56%, unicidade de `rid`.

## 2. Composição da v4

- rótulo bruto: 219.300 `true` / 32.755 `fake` (as 206k `NEWS_*` são `true` por
  procedência — **não entram no treino por padrão**).
- eras: 115k (2018–2022), 98k (pós-GPT), 31,5k (≤2017), 7k sem data.
- PT-PT: **20,7%** (ECO + Polígrafo).
- grupos novos relevantes: `FC_POLIGRAFO` **10.831** (64,6% fake), `EXT_LIARBR`
  **6.996** (35,7% fake), `NEWS_*` (procedência), `FC_BOATOS` 10.774.

## 3. Rotulagem em camadas e pool de fine-tuning

Camadas (`FakenewsBR_v4_labels.csv`):

| tier | linhas | origem |
|---|---:|---|
| v1 | 39.466 | rótulo da fonte (v1) |
| checker | 38.526 | rating de checador + LIAR/AveriTeC |
| checker_match | 4.119 | match ClaimReview ≥ 0,9 |
| llm_local | 3.092 | LLM local, veredito + confiança ≥ 0,8 |
| corroborated | 9 | ≥3 portais reputáveis independentes |
| provenance | 206.309 | `NEWS_*` (publicação, não checagem) |

**Pool de treino (`train_label`): 85.212 linhas — 60.991 fake / 24.221 true
(2,52:1).**
**Grupos informativos (DFR): 36.896 linhas — 19.177 fake / 17.719 true
(1,08:1)** — margem adequada para o fine-tuning. Os grupos balanceáveis agora
incluem `FC_POLIGRAFO`, `EXT_LIARBR` e `EXT_AVERITECBR`.

## 4. LLM local (Fase 2)

- Inferência local via **llama.cpp** (servidor Unsloth Studio, API
  OpenAI-compatível em `http://192.168.15.8:8888`), modelo
  **`openbmb/MiniCPM5-2B-GGUF`** (GGUF, 2B parâmetros). Cliente em
  `investigation/expansion/local_llm.py` (JWT + API key em `%TEMP%`, nunca no
  repositório).
- **Thinking desligado** (`chat_template_kwargs.enable_thinking=false`): 1,3 s
  por chamada contra 6–9 s; throughput ~1.430 rótulos/h com 6 workers.
- Tarefa `verify-news` (verificação seletiva com evidência do Google News RSS):
  **11.640 rótulos** — 3.836 `true`, 7.804 `unknown`, **0 `fake`** (manchete
  raramente *afirma* falsidade; fake exige refutação explícita de checador).
- Dos 11.640, **3.092** (confiança ≥0,8 e sem camada superior) foram promovidos
  a `llm_local` no `train_label`.
- Limitações: modelo 2B, abstenção alta (67%) e `confidence` 50 ruidosa; os
  rótulos `llm_local` ficam em camada separada (não se misturam a `checker`) e
  devem ser auditados antes de uso massivo.

## 5. Fontes ampliadas nesta execução

- **Polígrafo** (PT-PT): 12.120 artigos (11.420 linhas) — antes 0 por latência;
  resolução: fetch paralelo direto com rate-limit (o `PoliteSession` entrava em
  backoff longo sob concorrência).
- **LIAR-BR + AVERITEC-BR** (tradução PT-BR, STIL 2025): +10.027 linhas
  checadas (mapeamento conservador; grupos `EXT_*`).
- **Poder360/Brasil de Fato** (já na v2) seguem na v4.

## 6. Pendências (para quando houver chave ou decisão)

1. **`GOOGLE_FACTCHECK_API_KEY`**: harvest live por `reviewPublisherSiteFilter`
   (Lupa, Aos Fatos, Estadão, AFP, Comprova, UOL, Polígrafo…) com gate de
   similaridade — deve adicionar massas de `true` (equilíbrio) e cobrir 2025+.
2. **Correções verbatim por LLM** (tarefa `correction`, já implementada):
   +1–3k `true` checado.
3. **Auditoria** dos `llm_local` (amostra de 200–300) e dos `checker_match`.
4. **Fine-tuning** com `models/data.py` já estendido:
   `data.load(csv="FakenewsBR_sanitized_v4.csv", labels_csv="FakenewsBR_v4_labels.csv")`
   → pool 85k; usar `group_balanced_weights` (pool informativo 1,08:1) e split
   por cluster de quase-duplicata antes de comparar com a v1.
5. Persistir clusters de quase-duplicata e manifesto SHA256 (Fase 0, feito em
   parte: dedup roda no merge, mas os clusters ainda não vão para o CSV).

## 7. Como reproduzir

```bash
python -m investigation.expansion.ingest_external
python -m investigation.expansion.collect_sitemap --source poligrafo --workers 4 --delay 0.6
python -m investigation.expansion.extract
python -m investigation.expansion.merge_and_audit --news-max-ratio 6 \
    --extra investigation/expansion/processed/records_ext_liarbr.jsonl \
            investigation/expansion/processed/records_ext_averitecbr.jsonl \
    --out FakenewsBR_sanitized_v4.csv --provenance FakenewsBR_v4_provenance.csv
python -m investigation.expansion.local_label --max-minutes 480 --workers-llm 6
python -m investigation.expansion.apply_verification \
    --base FakenewsBR_v4_provenance.csv --v2 FakenewsBR_sanitized_v4.csv \
    --out FakenewsBR_v4_labels.csv
```
