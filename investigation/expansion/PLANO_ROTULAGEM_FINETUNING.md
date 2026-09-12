# Plano robusto — rotulagem dos 215k e margem fake/true para o fine-tuning BERTimbau

> Objetivo do usuário: rotular os ~215k do `FakenewsBR_sanitized_v2.csv` e obter
> margem boa de fake/fato para o fine-tuning do BERTimbau.
> Escrito em 2026-09-11. Números medidos no repositório.

## 1. Diagnóstico (por que "rotular tudo" não é o alvo certo)

Estado atual da v2 (juiz OK em 2026-09-11):

| fatia | linhas | rótulo | força do rótulo |
|---|---:|---|---|
| v1 (intacta) | 39.466 | 28.236 fake / 11.230 true | rótulo de fonte (usado no FT original) |
| novas com veredito (`label_source=rating`) | 21.850 | majoritariamente fake | checador (forte) |
| novas por procedência (`NEWS_*`) | 154.317 | `true` | **publicação, não checagem** |

Consequências para o fine-tuning:
- **O que treina o classificador são alegações checadas.** As 154k manchetes são
  `true` por convenção; usá-las como `true` ensina "estilo de manchete de portal
  ⇒ verdadeiro" (atalho de proveniência), degradando o que o projeto quer medir.
- **O pool checado é fake-heavy** (checadores publicam majoritariamente "falso").
  Para margem boa, é preciso **adicionar massas de `true` checado** (correções,
  AVERITEC Supported, LIAR True/Mostly-True, ratings verdadeiros via API).
- A decisão arquitetural: manter as 154k no dataset como **grupo degenerado/OOD
  (`press_true`)**, e treinar apenas no pool verificado — com a opção de usar
  verificação automática (LLM com evidência) para promover parte delas a
  `true`/`fake` de alta confiança, em camada separada e auditada.

Meta revisada de "rotular": **toda linha recebe um `label_tier`**; o texto só
ganha `auto_label` quando há evidência. A cobertura de veredito é medida, não
forçada.

## 2. Camadas de rotulagem (arquitetura)

```
Tier 1  checker        rating de checador (feed/API/WP/sitemap)      → fake/true/hard
Tier 2  llm_verified   LLM com evidência recuperada + abstenção       → fake/true/unknown
Tier 3  corroborated   ≥3 portais reputáveis independentes            → true
Tier 4  provenance     só publicação (NEWS_*)                         → press_true (não supervisionado)
        unknown        sem evidência suficiente                       → excluído do treino
```

Regra de ouro: `label` existente **nunca é sobrescrito**. As camadas vão para
`FakenewsBR_v2_provenance.csv` (`label_tier`, `auto_label`, `confidence`,
`verification_method`, `evidence_urls`) e, no treino, uma coluna `train_label`
derivada por política explícita.

## 3. Fases, entregáveis e dependências

### Fase 0 — sem chave (executável já)

1. **Polígrafo completo com fetch paralelo** (`collect_sitemap.py --workers`):
   ~12.121 URLs, hoje 0 coletadas por latência (~3,5 s/URL). Com 6–8 workers
   e rate-limit por host: ~1–1,5 h. Entregável: ~10k linhas PT-PT checadas.
2. **Ampliar o feed ClaimReview**: remover a whitelist restritiva e filtrar por
   idioma PT + sanidade de publisher (o feed tem 99.769 itens; hoje usamos
   8.569). Ganho pequeno, custo zero.
3. **Ingerir LIAR-BR e AVERITEC-BR** (repositório
   `github.com/lucasfrag/automated-fact-checking-in-pt-br`, STIL 2025):
   - LIAR-BR: 12.836 alegações políticas (6 níveis → binário:
     true/mostly-true→true; false/pants-on-fire→fake; half/barely→hard ou descarte).
   - AVERITEC-BR: 4.568 claims com evidência QA (Supported→true, Refuted→fake,
     demais→descarta).
   - Novo grupo `EXT_LIARBR`, `EXT_AVERITECBR` (traduzido; distribuição externa).
   - Antes: conferir licença dos datasets originais (LIAR/AveriTeC) e do repo.
4. **Agência Pública (Truco)** via WP REST (sem opt-out): ~200–500 checagens.
5. **Extração de correções** (tarefa LLM já preparada, `correction`): frases
   verbatim de correção dos artigos de Boatos/E-farsas/Bereia/G1/Polígrafo →
   linhas `true` de alta precisão (`FC_<PUB>_CORRECAO`). Preparar dry-run agora;
   executar na Fase 2.
6. **Cluster de quase-duplicatas persistido** para splits honestos
   (`dup_cluster_id` no CSV de proveniência).
7. **Manifesto SHA256** dos artefatos (adaptar `utils.py:11-48` do framework).
8. **Atualizar `models/data.py`** para tiers: `NEWS_*` nunca treina a cabeça;
   `EXT_*` como grupos novos; política de `train_label`.

### Fase 1 — Google Fact Check API (exige `GOOGLE_FACTCHECK_API_KEY`)

9. **Coleta live por publisher** (`reviewPublisherSiteFilter`) para Lupa, Aos
   Fatos, Estadão Verifica, AFP Checomas, Comprova, UOL Confere, Polígrafo,
   Observador, Público, etc. — legal e permitido mesmo para sites com opt-out de
   IA, porque é a API (metadado), não scraping.
   - paginar com `pageToken`/`pageSize=100`, `languageCode=pt`;
   - adotar o padrão do framework `factcheck.py:129-227` (streaming + JOIN SQLite);
   - **gate de similaridade** (não aceitar `claims[0]` cego como o framework faz).
   - Entregável esperado: +5–15k ratings checados (incluindo `Verdadeiro`).
10. **Fallback live na v2**: para linhas sem match no índice local, consultar a
    API uma vez e anexar rating com gate; cache para reprocessar.

### Fase 2 — LLM (exige `OPENROUTER_API_KEY`)

11. **`verify-news`** (já implementado, dry-run 62.257 req ≈ US$ 3,59–6):
    evidência do Google News RSS no prompt, veredito com abstenção. Meta de
    cobertura *estimada* 40–70% das claim-like; auditar amostra de 300–500 com
    precisão ≥95% antes de promover a rótulo de treino.
12. **Correções** (tarefa `correction`) nos artigos de checadores → massas de
    `true` checado.
13. **G1 multi-alegação** e feed `other` (tarefa `verdict_claim` já pronta).
14. **Auditoria**: comparar LLM × checker onde ambos existem; medir concordância;
    descartar prompts/limiares que reproduzam viés.

### Fase 3 — Montagem v3 e fine-tuning

15. **v3**: v1 + novas (com tiers), dedup com clusters, cotas por era, balanceamento
    por grupo. `judge_v3` estendido (tiers, conflitos, paridade).
16. **Splits honestos**: `GroupKFold` por cluster de quase-duplicata; OOD por
    canal/era/dialeto; nunca treinar em `NEWS_*`/`unknown`.
17. **Balanceamento**: pool checado com pesos por célula (grupo×rótulo, DFR);
    meta 1:1–1,5:1 fake:true **no pool de treino**, não no dataset bruto.
18. **Fine-tuning BERTimbau** (CPU): 2–3 épocas com early stop no pior-grupo;
    calibração Platt na validação balanceada (melhoria gratuita já medida:
    subset `true` 0,19→0,64, ECE 0,049→0,028).
19. **Avaliação**: macro-F1, pior-grupo, AUC por checador, PT-PT vs PT-BR
    dentro do checador, recortes de era; comparar v1 × v2-checado × v2+LLM.

## 4. Fontes de expansão e volumes estimados

| fonte | tipo | ganho | custo | chave |
|---|---|---|---|---|
| Polígrafo (sitemap, paralelo) | veredito | ~10k PT-PT | 1,5–3 h | não |
| LIAR-BR | veredito (6 níveis) | 12,8k | minutos | não |
| AVERITEC-BR | veredito + evidência | 4,6k | minutos | não |
| GFC live por publisher | veredito | 5–15k | 1–2 h | GOOGLE_FACTCHECK_API_KEY |
| Correções por LLM | `true` verbatim | 1–3k | US$ ~1 | OPENROUTER_API_KEY |
| G1 multi-alegação | veredito | ~0,4k | US$ ~0,1 | OPENROUTER_API_KEY |
| `verify-news` (62k claim-like) | `true`/`fake`/unknown | 25–45k | US$ 3,6–6 | OPENROUTER_API_KEY |
| Agência Pública (Truco) | veredito | 0,2–0,5k | minutos | não |
| Feed sem whitelist | veredito | ~0,1k | minutos | não |

Efeito no **pool checado** (o que importa para o FT): de ~61k (v1 + novas com
rating) para **~90–130k**, com mais `true` (correções + AVERITEC + LIAR +
ratings verdadeiros da API), melhorando a margem.

## 5. Orçamento

| item | custo | tempo |
|---|---:|---|
| Google Fact Check API | grátis (quota) | 1–2 h |
| OpenRouter (todas as tarefas) | **< US$ 15** | 1–2 h + 24 h de janela batch |
| Coleta (Polígrafo etc.) | grátis | ~3–5 h |
| Re-merge + auditoria | grátis | ~1 h |
| Fine-tuning CPU (3 runs) | grátis | 1,5–4 dias (overnight) |

## 6. Riscos e mitigação

- **Tradução (LIAR-BR/AVERITEC-BR)**: distribuição internacional, sem PT-BR
  nativo → manter como grupos separados e rodar ablação com/sem eles.
- **LLM labels**: não são checagem humana → tier separado, auditoria amostral,
  ablação com/sem LLM no FT; nunca misturar com `label_source=rating` na
  avaliação de acurácia.
- **Falso match** (headline que *reporta* alegação vs *afirma*): exigir stance;
  o prompt do LLM e os gates já impõem isso; sem LLM, abster.
- **Vazamento por quase-duplicata**: clusters persistidos e GroupKFold.
- **Desequilíbrio**: pesos por grupo/célula; nunca usar o dataset bruto como
  se fosse balanceado.
- **Licenças**: verificar LIAR/AveriTeC e o repo de tradução antes de incorporar.

## 7. Checklist de entregáveis

- [ ] Polígrafo completo (paralelo) e feed ampliado
- [ ] LIAR-BR/AVERITEC-BR ingeridos como grupos `EXT_*`
- [ ] Agência Pública/Truco ingerido
- [ ] `collect_gfc` live por publisher + gate de similaridade (exige chave)
- [ ] `verify-news` rodado, auditado e aplicado com `label_tier`
- [ ] Correções extraídas (massas de `true`)
- [ ] `FakenewsBR_sanitized_v3.csv` + proveniência com tiers + manifesto
- [ ] `models/data.py` com política `train_label` (NEWS/unknown fora)
- [ ] Splits por cluster de quase-duplicata
- [ ] FT BERTimbau: v1 × v2-checado × v2+LLM, com pior-grupo e calibração balanceada
- [ ] Relatório final com margem fake/true do pool de treino e limites de uso

## 8. Imediato (sem nenhuma chave)

1. Polígrafo paralelo + Agência Pública + LIAR-BR/AVERITEC-BR + feed ampliado.
2. Preparar (dry-run) correções e `verify-news` para quando houver chave.
3. Persistir clusters de quase-duplicata e manifesto.
4. Atualizar `models/data.py` e o juiz para tiers.
