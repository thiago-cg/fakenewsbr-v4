# Plano de validação das linhas `NEWS_*` (true por procedência)

> Antes de publicar a v4, é preciso responder: **o que significa o `true` das
> 209.456 manchetes `NEWS_*` (206.309 na camada `provenance`) e como validá-las?**
> Escrito em 2026-09-12.

## 1. O problema, formulado com precisão

`NEWS_*` não são alegações verificadas; são **manchetes publicadas** por um
veículo. O rótulo `true` codifica "este texto foi publicado por X em D", não
"a afirmação é factual". Validar essas linhas, portanto, não é fazer
fact-checking de 200 mil claims — é medir **quanto cada linha pode ser usada
como exemplo positivo confiável**, em camadas.

A distribuição torna o problema tratável: 99,7% da massa `provenance` vem de
apenas 4 veículos — Poder360 (77.273), Brasil de Fato (76.219), ECO (41.362),
O Eco (14.602). Validação por veículo + amostragem estratificada cobre quase
todo o volume; não é preciso inspecionar cada manchete.

Há três riscos distintos, que exigem validações distintas:

| risco | o que valida | granularidade |
|---|---|---|
| **A. Integridade de origem** (parsing/coleta) | URL existe, título/`h1` bate com o `text`, data bate | por linha (amostrável) |
| **B. Natureza da manchete** | é alegação verificável ou opinião/análise/descritiva | por linha (triagem) |
| **C. Veracidade do evento** | o fato ocorreu e é corroborado por fontes independentes | por linha claim-like |

## 2. Estratégia em quatro trilhas

### Trilha A — Integridade de origem (barata, determinística)

1. **V0 (offline, grátis):** saneamentos que não usam rede — datas futuras ou
   impossíveis, títulos com `&`/HTML residual, `text` que parece nome de seção
   ("Brasil", "Eleições"), duplicatas quase-iguais dentro do mesmo veículo,
   URLs fora do padrão do veículo.
2. **V1 (re-fetch com resume):** para uma **amostra estratificada**
   (veículo × era, ~2.400 linhas; ±2% a 95%), baixar a página, extrair
   `og:title`/`h1`/`datePublished` e medir:
   - taxa de HTTP 200 / artigo removido;
   - similaridade título coletado × título atual (cosseno/char n-gram);
   - data armazenada × `datePublished` (±1 dia).
   Aceite: **≥ 98% de título compatível e ≥ 97% de data compatível** na amostra.
   Se falhar, estender a validação a 100% (206k URLs ≈ 7–30 h com 8 workers,
   cache ETag, respeito a robots).
3. **V1b (liveness leve):** HEAD a cada 90 dias numa amostra rotativa para medir
   *link rot* ao longo do tempo (não bloqueia a publicação).

### Trilha B — Triagem de manchete (heurística + LLM)

4. **V2:** refinar `verify_news.is_claim_like` (hoje 62.257/209.456 = 30%
   claim-like) com dois níveis:
   - heurístico: perguntas retóricas, listas, "veja", "análise", esportes,
     previsão do tempo, celebridades;
   - LLM local: `{is_claim, tipo}` (alegação verificável / opinião / descritiva).
   Saída: `news_role ∈ {claim, opinion, descriptive, not_news}`.
   Uso: só `claim` entra em corroboração/verificação; o resto fica como
   `press_true` (OOD), nunca treino.

### Trilha C — Veracidade do evento (selectiva, com abstenção)

5. **V3 — match de checagem (mais forte):** `match_factcheck.py` contra o corpus
   ClaimReview (feed + `gfc.jsonl`), corte ≥ 0,9. Se um checador avaliou a
   mesma alegação: `supported`/`contradicted` com evidência. Já medido: só 234
   manchetes (0,15%) no corte alto; sozinho não resolve.
6. **V4 — corroboração por evidência:** `verify_news.py` (Google News RSS)
   com ≥ 3 domínios reputáveis independentes, mesmos números e datas ±45 dias
   → `corroborated` (confiança média). Já medido em amostra: 3,3% de cobertura.
7. **V5 — LLM local com evidência (`local_label.py`, já rodado):** veredito
   `true`/`fake`/`unknown` com abstenção. Resultado: 3.836 `true` de 11.640
   (33%), **0 `fake`**. Estender com o cache de evidência agora persistido
   (bug corrigido) e priorizar linhas claim-like.
8. **V6 — contradição:** se qualquer camada acima apontar `fake` (checador ou
   LLM com refutação explícita), a linha sai de `press_true` e vai para um
   balde `contradicted` — **sem** relabelar o dataset bruto.

### Trilha D — Auditoria estatística (a que dá credibilidade)

9. **V7 — auditoria cega por amostragem:** 400 linhas por tier relevante
   (`press_true` claim-like corroborado, `press_true` LLM-true, `press_true`
   não validado), sorteadas estratificadamente; 2 anotadores independentes
   (pode ser você + LLM como segundo leitor, com adjudicação manual de
   discordâncias). Medir **precisão por tier com IC 95%** (n=400 ⇒ ±4,9 p.p.
   para p≈0,9) e reportar matriz de concordância.
   Critério de publicação: `corroborated` ≥ 95% de precisão; `llm_local` ≥ 90%;
   `press_true` não validado reportado **sem** alegação de veracidade.

## 3. Integração no dataset (sem quebrar o contrato)

A v4 continua com 23 colunas e `label` inalterado. A validação vai em um novo
artefato + colunas de proveniência estendidas:

`FakenewsBR_v4_news_validation.csv`:

| coluna | descrição |
|---|---|
| `rid` | chave |
| `url_status` | `200` / `404` / `paywall` / `erro` / `nao_checado` |
| `title_match` | similaridade [0–1] entre `text` e o título atual |
| `date_match` | `0/1` (±1 dia) |
| `news_role` | `claim` / `opinion` / `descriptive` / `not_news` |
| `news_validation_tier` | `checker_match` / `corroborated` / `llm_local` / `press_true` / `contradicted` |
| `n_domains` | nº de domínios independentes na corroboração |
| `evidence` | URLs/ids das evidências |
| `validated_at`, `validator` | auditoria/reprodutibilidade |

Regra de treino: `train_usable = True` apenas para
`checker_match | corroborated | llm_local (conf ≥0,8)`; `press_true` permanece
**OOD** (grupo degenerado), como já definido em `models/data.py`.

## 4. Amostragem e poder estatístico

- Estimativa de proporção: n=2.400 ⇒ ±2 p.p. (p≈0,5, 95%); n=400 por tier ⇒
  ±4,9 p.p. (p≈0,9).
- Estratificação: veículo (4 dominantes + "outros") × era (≤2017, 2018–2022,
  pós-GPT) × tipo (claim/outros).
- Seed fixa e registro do plano amostral (reprodutibilidade).
- Custo: V0 grátis; V1 amostra ≈ 2 h; V1 completo 7–30 h; V2 LLM ≈ 62k
  requisições ≈ 40 h a 1.430/h (paralelizável); V4 RSS ≈ 7–24 h; V7 manual
  4–8 h.

## 5. Critérios de aceite (para liberar a publicação)

1. V0 sem anomalias > 1% da massa (datas/títulos/duplicações).
2. V1 na amostra: título ≥ 98%, data ≥ 97%, HTTP 200 ≥ 95%.
3. V2: `news_role` definido para 100% das `NEWS_*`; ao menos 25% `claim`.
4. V3–V5: tiers preenchidos; nenhuma linha `contradicted` fica em `press_true`.
5. V7: precisão `corroborated` ≥ 95% e `llm_local` ≥ 90% (IC 95%).
6. Card atualizado com a definição exata de `press_true` e com os números da
   validação; nenhuma afirmação de "fato verificado" para linhas não checadas.

## 6. Riscos e mitigação

- **Paywall/anti-bot no V1:** aceitar `paywall` como categoria; usar
  `og:title` de cache do Google/arquivo; não forçar scraping (opt-out de IA).
- **Corroboração circular:** mesma matéria de agência replicada em N portais.
  Mitigar exigindo domínios editorialmente independentes e, quando possível,
  verificação na fonte primária (documento, nota oficial).
- **Viés de veículo:** Poder360/Brasil de Fato têm linhas editoriais distintas;
  estratificar e reportar por veículo; nunca usar o veículo como rótulo.
- **Datas e números:** guardas do `verify_news` (números compatíveis, ±45 dias)
  já bloqueiam parte dos falsos positivos.
- **Limite epistêmico:** validação em camadas melhora a qualidade, mas
  `press_true` continua não sendo veredito de checador — o card deve dizer isso.

## 7. Sequência sugerida

1. V0 + V1 amostra + V2 (heurística) — roda hoje, sem chave.
2. V3/V4 no subconjunto `claim-like` (reusa `match_factcheck`, `verify_news`).
3. V5 estendido com cache de evidência persistido (corrigido).
4. V7 auditoria da amostra e ajuste dos critérios de publicação.
5. Só então publicar no HF com o card atualizado e
   `FakenewsBR_v4_news_validation.csv` anexado.
