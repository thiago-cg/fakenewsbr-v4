# Auditoria FakenewsBR v2

- v1 intacta: 39,466 linhas
- novas: 256,911 linhas
- total v2: 296,377 linhas

## Composicao das novas
- rotulo: {'true': 219630, 'fake': 37281}
- veredito vs procedencia: {'veredito': 47151, 'procedencia': 209760}
- por era: {'2018_2022': 115715, 'pos_gpt35': 100197, 'ate_2017': 31818, 'sem_data': 9181}
- PT-PT: 53,110 (20.67%)
- mencoes a IA: 1,231

## Datasets (top 20)
- NEWS_PODER360: 77,359
- NEWS_BRASILDEFATO: 76,297
- NEWS_ECO: 41,439
- NEWS_OECO: 14,665
- FC_POLIGRAFO: 10,831
- FC_BOATOS: 10,773
- EXT_LIARBR: 6,996
- FC_EFARSAS: 3,208
- FC_G1: 3,187
- EXT_AVERITECBR: 2,925
- FC_BOATOS_VIRAL: 2,360
- FC_ESTADAO: 1,478
- FC_LUPA: 1,436
- FC_COMPROVA: 957
- FC_OBSERVADOR: 825
- FC_AOSFATOS: 814
- FC_UOL: 662
- FC_FOLHA: 211
- FC_BEREIA: 202
- FC_SBT: 202

## Conflitos de dedup
```
{
 "dup_nova_near": 3840,
 "dup_v1_exata": 4073,
 "dup_v1_near": 605
}
```