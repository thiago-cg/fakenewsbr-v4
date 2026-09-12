# Auditoria FakenewsBR v2

- v1 intacta: 39,466 linhas
- novas: 258,206 linhas
- total v2: 297,672 linhas

## Composicao das novas
- rotulo: {'true': 219670, 'fake': 38536}
- veredito vs procedencia: {'veredito': 48446, 'procedencia': 209760}
- por era: {'2018_2022': 115903, 'pos_gpt35': 101233, 'ate_2017': 31818, 'sem_data': 9252}
- PT-PT: 53,109 (20.57%)
- mencoes a IA: 1,235

## Datasets (top 20)
- NEWS_PODER360: 77,359
- NEWS_BRASILDEFATO: 76,297
- NEWS_ECO: 41,439
- NEWS_OECO: 14,665
- FC_POLIGRAFO: 10,831
- FC_BOATOS: 10,772
- EXT_LIARBR: 6,996
- FC_EFARSAS: 3,208
- FC_G1: 3,187
- EXT_AVERITECBR: 2,925
- FC_BOATOS_VIRAL: 2,360
- FC_ESTADAO: 1,477
- FC_LUPA: 1,435
- FC_AFP: 1,044
- FC_COMPROVA: 956
- FC_OBSERVADOR: 824
- FC_AOSFATOS: 813
- FC_UOL: 788
- FC_FOLHA: 211
- FC_BEREIA: 202

## Conflitos de dedup
```
{
 "dup_nova_near": 3994,
 "dup_v1_exata": 4701,
 "dup_v1_near": 605
}
```