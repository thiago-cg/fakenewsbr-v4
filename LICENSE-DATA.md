# Licenciamento do dataset

Este repositório contém **código** e **dados**, com licenças diferentes:

## Código

O código-fonte (diretórios `investigation/`, `models/`, `sanitize_dataset.py`,
scripts) é distribuído sob a licença **MIT** (arquivo [`LICENSE`](LICENSE)).

## Dataset

A compilação `FakenewsBR v4` (`data/*.csv`) é distribuída como
**`license: other`** (uso de pesquisa) porque agrega fontes com licenças
distintas — incluindo materiais **sem licença explícita** e um corpus
**GPL-3.0** (`FakeWhatsApp.BR_2018`). O detalhamento fonte a fonte, o status de
redistribuição e o checklist de release estão em
[`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md).

**Antes de reutilizar comercialmente ou redistribuir, verifique as licenças de
cada fonte.** Até a revisão completa, considere os dados para **pesquisa**.

## PII

A variante `data/FakenewsBR_v4_public.csv` foi mascarada (e-mails, CPF e
telefones) por `investigation/expansion/scrub_pii.py`. O CSV de pesquisa
(`FakenewsBR_sanitized_v4.csv`) não é distribuído aqui para evitar exposição de
PII; ele pode ser regenerado com o pipeline deste repositório.

## Atribuições

HF `ju-resplande/portuguese-fact-checking`; framework
[AKCIT-FN/fakenews-data](https://github.com/AKCIT-FN/fakenews-data) (MIT);
`cabrau/FakeWhatsApp.Br` (GPL-3.0); `GoloMarcos/LLM4BrazilianFakeNews`; Kaggle
`fabioselau/fakes-news-portuguese`; Data Commons / Google Fact Check Tools;
Boatos.org, E-farsas, Coletivo Bereia, G1 Fato ou Fake, Polígrafo;
Poder360, Brasil de Fato, O Eco, ECO; LIAR (Wang, 2017) e AVeriTeC
(Schlichtkrull et al., 2023) e suas traduções PT-BR (STIL 2025).
