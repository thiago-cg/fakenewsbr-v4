# Licenciamento

## Código e compilação — MIT

O código-fonte (diretórios `investigation/`, `models/`, `sanitize_dataset.py`),
a **compilação**, a **curadoria**, as **anotações** e as **camadas de rótulo**
produzidas pelos autores são distribuídos sob a licença **MIT permissiva**
(arquivo [`LICENSE`](LICENSE)): uso, cópia, modificação, fusão, publicação,
distribuição, sublicenciamento e venda permitidos, com atribuição e sem
garantia.

## Conteúdo de terceiros

O dataset agrega textos de terceiros (checadores, portais, corpora históricos e
traduções LIAR/AveriTeC). Esse conteúdo **permanece sob os termos das fontes
originais** — incluindo materiais sem licença explícita e um corpus GPL-3.0
(`FakeWhatsApp.BR_2018`). A licença MIT do projeto **não substitui** nem
relicencia esses direitos.

Detalhamento fonte a fonte, status de redistribuição e itens que exigem revisão
para uso comercial estão em [`SOURCES_AND_LICENSES.md`](SOURCES_AND_LICENSES.md).

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
