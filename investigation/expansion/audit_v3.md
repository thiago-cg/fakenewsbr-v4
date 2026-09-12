# Auditoria FakenewsBR v2

- v1 intacta: 39,466 linhas
- novas: 203,447 linhas
- total v2: 242,913 linhas

## Composicao das novas
- rotulo: {'true': 177685, 'fake': 25762}
- veredito vs procedencia: {'veredito': 31772, 'procedencia': 171675}
- por era: {'2018_2022': 96133, 'pos_gpt35': 68710, 'ate_2017': 31509, 'sem_data': 7095}
- PT-PT: 34,415 (16.92%)
- mencoes a IA: 1,007

## Datasets (top 20)
- NEWS_PODER360: 62,762
- NEWS_BRASILDEFATO: 61,621
- NEWS_ECO: 34,397
- NEWS_OECO: 12,895
- FC_BOATOS: 10,774
- EXT_LIARBR: 6,996
- FC_EFARSAS: 3,208
- FC_G1: 3,187
- EXT_AVERITECBR: 2,925
- FC_BOATOS_VIRAL: 2,360
- FC_LUPA: 1,437
- FC_COMPROVA: 249
- FC_FOLHA: 211
- FC_SBT: 210
- FC_BEREIA: 202
- FC_NEXO: 9
- FC_POLIGRAFO: 4

## Conflitos de dedup
```
{
 "dup_nova_near": 3013,
 "dup_v1_exata": 2820,
 "dup_v1_near": 18
}
```