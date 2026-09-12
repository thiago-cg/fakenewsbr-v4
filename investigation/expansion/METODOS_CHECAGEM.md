# Métodos para verificar manchetes/URLs e rotular `NEWS_*` — pesquisa e decisão

> Objetivo do usuário: rotular fake/true todas as linhas sem rótulo de veredito
> (hoje 154.317 `NEWS_*` são `true` apenas por procedência).
> Pesquisa feita em 2026-09-11; números medidos no repositório.

## 1. O que a API Google Fact Check faz (e não faz)

`claims:search` é um **índice de checagens publicadas**, não um verificador.
Parâmetros: `query` (opcional se houver `reviewPublisherSiteFilter`),
`languageCode`, `maxAgeDays`, `pageSize`, `pageToken`. O endpoint `pages` é CRUD
do ClaimReview da própria organização.

Consequência: para uma manchete receber veredito, é preciso que alguém tenha
checado **aquela alegação**. Medido: casando as 154.317 manchetes contra o
corpus ClaimReview (feed Data Commons), só **234 (0,15%)** têm match de
alta confiança (cos ≥ 0,9). A API não resolve o problema de rotular manchetes.

## 2. Estado da arte (o que a literatura recomenda)

O padrão convergente é **retrieval + stance/NLI + abstenção**:

| referência | ideia central |
|---|---|
| WKGFC (arXiv 2603.00267, 2026) | agente que recupera evidência em KG (Wikidata/DBpedia) e web; +5 pp de balanced accuracy |
| ZoFia (Findings ACL 2026) | zero-shot, entidades → retrieval duplo (Wikipedia + web) + debate multi-LLM |
| HARIS (ACL 2026) | agentes separados de raciocínio e busca, treinados com RL |
| RAFTS (ACL 2024) | recupera documentos, gera argumentos contrastantes (a favor/contra) e decide |
| SourceMinds (CheckThat! 2026) | gera artigo de checagem com auditoria de citações via NLI |
| **Calibrated Selective Fact-Checking (arXiv 2607.18240, 2026)** | **abster-se é essencial**: 97,8% de acurácia seletiva com 93,7% de cobertura; forçar binário com evidência fraca é o erro central |
| Gomes et al. (FEVER 2025, PT) | PT: LLM extrai alegação → busca web (Google CSE) + FactCheck API; sem NLI; alerta para "desinformação auto-reforçada" e desalinhamento temporal |
| Delucis et al. (STIL 2025, PT-BR) | LIAR-BR/AVERITEC-BR: encoder fine-tuned > Gemma zero/few-shot; metadados/evidência são decisivos |
| InvestigA (GitHub, PT-BR) | RAG local sobre 19.502 artigos de checadores brasileiros, BM25 + embeddings, votação multi-run |
| Santos & Pardo (PROPOR/STIL) | checagem em PT via grafo de conhecimento construído de notícias verdadeiras |

Três lições para o nosso caso:
1. **Nunca forçar rótulo**: `unknown` é uma saída de segurança, não uma falha.
2. **Evidência de checador > conhecimento do LLM**: o LLM só deve classificar
   *com base nas evidências recuperadas*, nunca pela memória.
3. **Consistência de números/datas**: similaridade semântica sozinha confunde
   "2ª parcela" com "6ª parcela" (foi medido; por isso as guardas).

## 3. O que dá para fazer sem chave (implementado)

`verify_news.py` — verificador seletivo, sem nenhuma chave de API:

1. **Triagem**: 62.257 das 154.317 manchetes são "claim-like" (o resto é
   opinião/análise/pergunta).
2. **Evidência**: Google News RSS (funciona sem chave e **traz checagens**:
   no teste, Aos Fatos e AFP Checamos apareceram espontaneamente).
3. **Match semântico local**: encoder BERTimbau fine-tuned do próprio projeto
   (`models/artifacts/bertimbau_ft.onnx`, ONNX/CPU, ~35 textos/s via
   `models.embed.extract`). Sem instalar nada novo.
4. **Regras de rótulo conservadoras**:
   - checador com veredito explícito + similaridade ≥ 0,80 + números
     compatíveis → `fake`/`true` (confiança alta);
   - ≥ 3 domínios reputáveis independentes + números e datas compatíveis
     (±45 dias) → `true` (confiança média);
   - senão → `unknown` (**abstenção**).
5. **Medição (amostra de 300 claim-like)**: cobertura **3,3%** (10 `true`), 0
   matches de checador de alta confiança. É o teto realista do método
   lexical/semântico sem LLM.

Também implementado: `match_factcheck.py` casa a v2 contra o corpus ClaimReview
offline (34.180 matches a 0,5, mas **ruído**: concordância 38,5%; a 0,9 são
4.330 matches com **95,5% de concordância** — usar só esse corte).

## 4. O que dá para fazer com LLM (preparado, exige chave)

`llm_batch.py --task verify-news`:
- monta um request por manchete claim-like com as evidências do Google News RSS
  (top-8 títulos + domínio + data + flag de checador);
- prompt obriga: usar **somente as evidências**; `fake` só se a evidência
  refutar; `true` só com ≥2 evidências independentes e números/datas
  compatíveis; caso contrário `unknown` (abstenção);
- saída JSON estrita (`is_claim`, `verdict`, `confidence`, `claim`,
  `rationale`, `evidence_idx`);
- **dry-run medido: 62.257 requests ≈ US$ 3,59** (sem evidências; com elas,
  ~US$ 5–6 no `gpt-5-nano:batch`); busca de evidência paralelizável
  (`--workers 4 --delay 0.4` ⇒ ~2,5 h para 62k);
- fluxo: `llm-prepare --task verify-news` → (usuário define
  `OPENROUTER_API_KEY`) → `llm-submit --task verify-news` → `llm-collect` →
  `llm-apply` ⇒ `FakenewsBR_v2_llm_labels.csv`.

Estimativa de cobertura do LLM com evidência: *estimativa* 40–70% das
claim-like com veredito, o resto `unknown`; **auditar uma amostra** antes de
usar como rótulo de treino.

## 5. Decisão e integridade do dataset

- **Não** sobrescrever `label`: criar a coluna/tabela `auto_label` com
  `method` e `confidence`. O rótulo por procedência continua separado
  (`label_source=provenance`) e não deve ser misturado com veredito ao medir
  acurácia de fact-checking.
- Manchetes `unknown` **permanecem** no dataset como `press_true` (grupo
  degenerado), que é a função delas: cobertura/OOD, não supervisão factual.
- Ordem de confiança: (1) veredito de checador → (2) LLM com evidência e
  auditoria → (3) corroboração por múltiplos portais → (4) `unknown`.
- Se o objetivo for massa de alegações checadas, o caminho continua sendo
  ampliar checadores e o feed — o LLM **não** substitui um fact-check.

## 6. Como rodar

```bash
# sem chave (amostra ou todas; mede cobertura real)
python -m investigation.expansion.verify_news --limit 0     # todas (longo)
python -m investigation.expansion.verify_news --limit 1000  # amostra

# com chave (OpenRouter) — rotula as claim-like com evidência
python -m investigation.expansion.pipeline llm-prepare --task verify-news
python -m investigation.expansion.pipeline llm-submit  --task verify-news
python -m investigation.expansion.pipeline llm-collect --task verify-news
python -m investigation.expansion.pipeline llm-apply   --task verify-news
```
