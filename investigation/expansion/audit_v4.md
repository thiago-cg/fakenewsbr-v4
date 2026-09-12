# Auditoria FakenewsBR v2

- v1 intacta: 39,466 linhas
- novas: 252,055 linhas
- total v2: 291,521 linhas

## Composicao das novas
- rotulo: {'true': 219300, 'fake': 32755}
- veredito vs procedencia: {'veredito': 42599, 'procedencia': 209456}
- por era: {'2018_2022': 115232, 'pos_gpt35': 98219, 'ate_2017': 31509, 'sem_data': 7095}
- PT-PT: 52,207 (20.71%)
- mencoes a IA: 1,215

## Datasets (top 20)
- NEWS_PODER360: 77,273
- NEWS_BRASILDEFATO: 76,219
- NEWS_ECO: 41,362
- NEWS_OECO: 14,602
- FC_POLIGRAFO: 10,831
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

## Conflitos de dedup
```
{
 "dup_nova_near": 3493,
 "dup_v1_exata": 2820,
 "dup_v1_near": 603
}
```