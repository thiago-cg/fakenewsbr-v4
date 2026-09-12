# Pipeline do Score de Confiança — FakenewsBR

Objetivo: um **score contínuo e calibrado** de P(desinformação), robusto a mudança
de canal — não um classificador que maximiza acurácia média.

Substitui `bert_finetune.py`. Ver `../.claude` → memória do projeto para os achados
que motivaram cada decisão.

## Por que a acurácia média não é a métrica

58,4% da base vem de dois subsets onde a origem determina o rótulo: `fakes`
(20.347 linhas, 100% falso) e `true` (2.710, 100% verdadeiro). Um modelo pode
atingir acurácia alta aprendendo "texto curto em estilo de alegação de agência
= falso", que é artefato de compilação do corpus, não semântica.

As métricas de manchete aqui são:

1. **macro-F1 do pior grupo** — a média esconde o confundimento
2. **ECE** — um score precisa ser calibrado para ser um score
3. **desempenho fora de domínio** (leave-one-channel-out)
4. **casos limítrofes** — as 1.020 meias-verdades (`Enganoso`, `Distorcido`, `Fora de contexto`)

Baseline honesto a superar: **76,70% acc / 82,92% F1(fake)** (Variante B do baseline linear).

## Módulos

| Arquivo | Papel |
|---|---|
| `data.py` | Carga, grupos, canais, features estilísticas, splits IID e OOD |
| `evaluate.py` | Temperature scaling, ECE, Brier, por-grupo, pior-grupo, casos limítrofes |
| `embed.py` | Export ONNX + extração de embeddings na Vega 8 (DirectML) |
| `score.py` | Cabeça DFR + features híbridas + calibração → o Score |
| `encoder.py` | Fine-tuning do BERTimbau (opcional; a Trilha A não precisa) |

## Trilha A — iteração em minutos (recomendada para começar)

Encoder congelado. A GPU faz um passe único; depois cada experimento leva segundos.

```bash
python -m models.embed export --out models/artifacts/bertimbau.onnx
```

```bash
python -m models.embed run --onnx models/artifacts/bertimbau.onnx --out models/artifacts/embeddings.npy
```

```bash
python -m models.score --embeddings models/artifacts/embeddings.npy
```

## Trilha B — fine-tuning (uma noite)

```bash
python -m models.encoder --max-length 192 --freeze-layers 6 --epochs 2
```

Depois reextraia os embeddings do modelo ajustado e rode a Trilha A de novo:

```bash
python -m models.embed export --model models/artifacts/bertimbau_finetuned --out models/artifacts/bertimbau_ft.onnx
```

## Experimentos A/B previstos

O projeto trata comparação como método, não como enfeite. Cada flag existe para
**medir** uma decisão que estava sendo assumida:

| Flag | Pergunta que responde |
|---|---|
| `--no-style` | As features estilísticas ajudam ou só reintroduzem o viés? |
| `--include-length` | Quanto do desempenho vem do comprimento (o atalho mais contaminado)? |
| `--ood whatsapp portal` | Um modelo treinado em portal detecta corrente de WhatsApp? |
| `encoder --mask-entities` | Mascarar entidades ajuda? (ficou em aberto no plano original) |
| `encoder --class-weights` | Quanto a loss ponderada degrada a calibração? |

Em todo relatório aparecem duas variantes lado a lado:

- **ERM (ingênua)** — treina em tudo, inclusive os grupos degenerados
- **DFR (honesta)** — treina só onde a origem não prediz o rótulo, com
  ponderação por célula (grupo × rótulo). Kirichenko et al. (2023),
  *Last Layer Re-Training is Sufficient for Robustness to Spurious Correlations*

Espera-se que o DFR tenha **acurácia média menor e pior-grupo maior**. Essa é a
troca que o projeto já aceitou explicitamente ao aprovar a Variante B do baseline.

## Hardware

Treino é CPU-only nesta máquina (Ryzen 7 5825U): não há caminho de backward por
GPU — `torch-directml` não existe para Python 3.13, e o backend Vulkan do PyTorch
é inference-only e nunca teve kernels de backward.

A Vega 8 **é** usada, em inferência, onde entrega 2,3–2,7x sobre a CPU. Use
`--batch-size 16`: batch maior piora o ganho porque a iGPU divide o barramento
DDR4 com a CPU e satura banda antes de FLOPs.

| | CPU (8 threads) | Vega 8 / DirectML |
|---|---:|---:|
| seq=64, batch=16 | 18,8 am/s | **51,2 am/s** (2,73x) |
| seq=128, batch=16 | 8,7 am/s | **20,5 am/s** (2,35x) |
| seq=128, batch=64 | 8,7 am/s | 15,4 am/s (1,78x) |
