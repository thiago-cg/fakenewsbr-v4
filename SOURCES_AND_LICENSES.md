# Fontes, licenças e conformidade — FakenewsBR v4

> Documento obrigatório de leitura antes de publicar/redistribuir o dataset.
> Status das licenças verificado em 2026-09-12 via API do GitHub/Hugging Face e
> termos públicos. **Não é aconselhamento jurídico.** Itens marcados com ⚠️
> exigem verificação ou permissão antes do release público.

## 1. Tabela de fontes

### Base histórica (v1, embutida intacta)

| grupo | origem | licença detectada | redistribuição |
|---|---|---|---|
| `Fake.br`, `Fake.br_raw` | HF [`ju-resplande/portuguese-fact-checking`](https://huggingface.co/datasets/ju-resplande/portuguese-fact-checking) (subconjunto Fake.br) | **MIT** | OK com atribuição |
| `COVID19.BR`, `COVID19.BR_raw` | mesmo HF (subconjunto COVID19.BR) | **MIT** | OK com atribuição |
| `MuMiN-PT`, `MuMiN-PT_raw` | mesmo HF (subconjunto MuMiN-PT) | **MIT** (no HF; o corpus MuMiN original tem termos próprios) | OK via HF; citar MuMiN |
| `FakeWhatsApp.BR_2018` | GitHub [`cabrau/FakeWhatsApp.Br`](https://github.com/cabrau/FakeWhatsApp.Br) | **GPL-3.0** | ⚠️ copyleft: revisar implicações de redistribuir o corpus derivado |
| `LLM4BR_300` | GitHub [`GoloMarcos/LLM4BrazilianFakeNews`](https://github.com/GoloMarcos/LLM4BrazilianFakeNews) | **sem licença** ⚠️ | pedir permissão ao autor |
| `fakes`, `true` | Kaggle `fabioselau/fakes-news-portuguese` | **sem licença explícita** ⚠️ | checar termos do Kaggle/autor |
| pipeline da v1 | [`AKCIT-FN/fakenews-data`](https://github.com/AKCIT-FN/fakenews-data) | **MIT** | OK |

### Expansão v2–v4

| grupo/fonte | origem | licença/termos | redistribuição |
|---|---|---|---|
| feed ClaimReview (`FC_LUPA`, `FC_COMPROVA`, `FC_FOLHA`, `FC_SBT`, `FC_NEXO`, parte de `FC_BOATOS`/`FC_G1`) | [Data Commons](https://datacommons.org/) (dump ClaimReview) + Google Fact Check Tools | termos do Data Commons/Google ⚠️ (verificar; tipicamente CC BY / uso com atribuição) | verificar e atribuir |
| `FC_BOATOS`, `FC_BOATOS_VIRAL` | Boatos.org (WP REST; robots sem opt-out de IA) | conteúdo editorial sem licença explícita ⚠️ | usar trechos curtos + atribuição; pedir permissão |
| `FC_EFARSAS` | E-farsas (WP REST) | idem ⚠️ | idem |
| `FC_BEREIA` | Coletivo Bereia (WP REST) | idem ⚠️ | idem |
| `FC_G1` | G1 Fato ou Fake (sitemap) | conteúdo Globo, copyright ⚠️ | idem |
| `FC_POLIGRAFO` | Polígrafo/SAPO (sitemaps; PT-PT) | idem ⚠️ | idem |
| `NEWS_PODER360`, `NEWS_BRASILDEFATO`, `NEWS_OECO`, `NEWS_ECO` | portais (WP REST) | manchetes; direitos autorais dos veículos ⚠️ | usar manchetes curtas + atribuição; revisar |
| `EXT_LIARBR` | [LIAR](https://www.cs.ucsb.edu/~william/data/liar_dataset.zip) (Wang 2017) traduzido | LIAR original: uso de pesquisa, sem licença explícita ⚠️; tradução em [`lucasfrag/automated-fact-checking-in-pt-br`](https://github.com/lucasfrag/automated-fact-checking-in-pt-br) **sem licença** ⚠️ | pedir permissão (tradução é obra derivada) |
| `EXT_AVERITECBR` | [AVeriTeC](https://github.com/MichSchli/AVeriTeC) (Schlichtkrull et al. 2023) traduzido | licença do original ⚠️; tradução sem licença ⚠️ | idem |

Legenda: OK = redistribuição viável com atribuição; ⚠️ = verificar/pedir
permissão antes de publicar.

## 2. Política de opt-out de IA

O projeto **não** faz scraping de conteúdo de sites cujo `robots.txt` bloqueia
robôs de treino de IA (GPTBot, ClaudeBot, CCBot, Google-Extended, Bytespider,
Amazonbot, Applebot-Extended, meta-externalagent, PerplexityBot, entre outros).
Publishers com opt-out que aparecem no dataset (ex.: Lupa, Aos Fatos, Estadão
Verifica, Comprova, Observador) entram **apenas via metadado ClaimReview**
(feed/API), nunca por cópia de artigos. AFP e UOL devolvem 403 e ficaram fora.

## 3. Conteúdo sensível

- O dataset contém **desinformação real**: saúde (vacinas, COVID-19), política,
  violência, teorias conspiratórias e linguagem ofensiva.
- Uso educacional/pesquisa; evitar exibição sem contexto.
- Não é oráculo de verdade: os rótulos se referem a trechos de texto.

## 4. PII (auditoria medida em 2026-09-12)

| padrão | linhas | observação |
|---|---:|---|
| e-mails | 64 | inclui endereços em mensagens virais |
| strings tipo telefone | 319 | muitos falsos positivos numéricos (datas, valores) |
| CPF formatado | 1 | `\d{3}\.\d{3}\.\d{3}-\d{2}` |

**Ação executada:** a variante `FakenewsBR_v4_public.csv` foi gerada com
`python -m investigation.expansion.scrub_pii`, mascarando **705 e-mails, 3 CPFs
e 3.106 strings tipo telefone** (mesmas 291.521 linhas). O CSV de pesquisa
permanece íntegro. Revisar também `factcheck_claimant` para pessoas privadas e
os textos `FC_BOATOS_VIRAL` e `FakeWhatsApp.BR_2018`.

## 5. Licenciamento da compilação

- **Código** do repositório: recomenda-se **MIT** (compatível com a base
  AKCIT-FN e com o ecossistema). Criar `LICENSE`.
- **Dataset compilado**: declarado como `license: other` no card, apontando para
  este documento. Enquanto as licenças ⚠️ não forem resolvidas, publique como
  **uso de pesquisa, não comercial**, com atribuição a cada fonte.
- Atribuições mínimas no card/HF: HF `ju-resplande`, AKCIT-FN, cabrau (GPL-3.0),
  GoloMarcos, Kaggle, Data Commons/Google, LIAR (Wang 2017), AVeriTeC
  (Schlichtkrull et al. 2023), tradutores do STIL 2025, e cada veículo de
  checagem.

## 6. Checklist de release

- [ ] Criar `LICENSE` do código (MIT) e `LICENSE-DATA`/termos próprios.
- [ ] Resolver os itens ⚠️ (permissões de Boatos/E-farsas/Bereia/G1/Polígrafo/
      portais; tradução LIAR/AVeriTeC; LLM4BR_300; Kaggle).
- [ ] Checar termos do Data Commons/Google Fact Check para redistribuição.
- [x] Rodar o scrub de PII (`FakenewsBR_v4_public.csv` gerado).
- [ ] Incluir atribuições e citação no README/HF.
- [ ] Definir se `FakeWhatsApp.BR_2018` (GPL-3.0) fica no release ou em pacote
      separado.
- [ ] Publicar os arquivos de camadas (`labels`) e proveniência junto do CSV.
