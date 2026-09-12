# Auditoria FakenewsBR v2

- v1 intacta: 39,466 linhas
- novas: 176,174 linhas
- total v2: 215,640 linhas

## Composicao das novas
- rotulo: {'true': 154930, 'fake': 21244}
- veredito vs procedencia: {'veredito': 21851, 'procedencia': 154323}
- por era: {'2018_2022': 76470, 'pos_gpt35': 68710, 'ate_2017': 30985, 'sem_data': 9}
- PT-PT: 31,113 (17.66%)
- mencoes a IA: 994

## Datasets (top 20)
- NEWS_PODER360: 55,967
- NEWS_BRASILDEFATO: 55,230
- NEWS_ECO: 31,097
- NEWS_OECO: 12,029
- FC_BOATOS: 10,774
- FC_EFARSAS: 3,208
- FC_G1: 3,187
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
 "dup_nova_near": 2700,
 "dup_v1_exata": 2818,
 "dup_v1_near": 17
}
```