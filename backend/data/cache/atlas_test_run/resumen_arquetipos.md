# Resumen ATLAS — arquetipos por ticker × indicador × horizonte

> ⚠️ Descriptivo (capa 1, §2). NO autoriza trades. Único camino a regla: graduación pre-registrada (§7).

Corrida: 20260902_002317 · Celdas escaneadas: 513

## Tabla de arquetipos

| Ticker | Indicador | h | Arquetipo | Estabilidad | Interp/Esp |
|---|---|---|---|---|---|
| AAPL | momentum_12_1 | 5 | CONTINUISTA | 0.74 | 35/39 |
| AAPL | momentum_12_1 | 20 | INERTE | 0.69 | 13/12 |
| AAPL | momentum_12_1 | 60 | REVERSIONISTA | 1.00 | 4/3 |
| AAPL | rsi14 | 5 | CONTINUISTA | 0.72 | 35/39 |
| AAPL | rsi14 | 20 | CONTINUISTA | 0.79 | 13/12 |
| AAPL | rsi14 | 60 | REVERSIONISTA | 0.89 | 4/3 |
| AAPL | vol20 | 5 | CAMALEÓN | 0.63 | 35/39 |
| AAPL | vol20 | 20 | REVERSIONISTA | 0.78 | 13/12 |
| AAPL | vol20 | 60 | REVERSIONISTA | 0.80 | 4/3 |
| KO | momentum_12_1 | 5 | REVERSIONISTA | 0.80 | 30/39 |
| KO | momentum_12_1 | 20 | REVERSIONISTA | 0.87 | 12/12 |
| KO | momentum_12_1 | 60 | REVERSIONISTA | 1.00 | 4/3 |
| KO | rsi14 | 5 | CAMALEÓN | 0.60 | 30/39 |
| KO | rsi14 | 20 | CAMALEÓN | 0.60 | 12/12 |
| KO | rsi14 | 60 | REVERSIONISTA | 0.85 | 4/3 |
| KO | vol20 | 5 | CONTINUISTA | 0.72 | 30/39 |
| KO | vol20 | 20 | CONTINUISTA | 0.75 | 12/12 |
| KO | vol20 | 60 | REVERSIONISTA | 0.76 | 4/3 |
| NVDA | momentum_12_1 | 5 | CAMALEÓN | 0.68 | 36/39 |
| NVDA | momentum_12_1 | 20 | CONTINUISTA | 0.81 | 13/12 |
| NVDA | momentum_12_1 | 60 | CONTINUISTA | 0.74 | 4/3 |
| NVDA | rsi14 | 5 | CAMALEÓN | 0.63 | 36/39 |
| NVDA | rsi14 | 20 | CONTINUISTA | 0.75 | 13/12 |
| NVDA | rsi14 | 60 | CONTINUISTA | 0.88 | 4/3 |
| NVDA | vol20 | 5 | REVERSIONISTA | 0.90 | 36/39 |
| NVDA | vol20 | 20 | REVERSIONISTA | 0.82 | 13/12 |
| NVDA | vol20 | 60 | REVERSIONISTA | 0.74 | 4/3 |

## Candidatos visibles (no INERTE/INSUFICIENTE, IC ≠ 0)

| Ticker | Indicador | h | Arquetipo | Estabilidad |
|---|---|---|---|---|
| AAPL | momentum_12_1 | 60 | REVERSIONISTA | 1.00 |
| KO | momentum_12_1 | 60 | REVERSIONISTA | 1.00 |
| NVDA | vol20 | 5 | REVERSIONISTA | 0.90 |
| AAPL | rsi14 | 60 | REVERSIONISTA | 0.89 |
| NVDA | rsi14 | 60 | CONTINUISTA | 0.88 |
| KO | momentum_12_1 | 20 | REVERSIONISTA | 0.87 |
| KO | rsi14 | 60 | REVERSIONISTA | 0.85 |
| NVDA | vol20 | 20 | REVERSIONISTA | 0.82 |
| NVDA | momentum_12_1 | 20 | CONTINUISTA | 0.81 |
| AAPL | vol20 | 60 | REVERSIONISTA | 0.80 |
| KO | momentum_12_1 | 5 | REVERSIONISTA | 0.80 |
| AAPL | rsi14 | 20 | CONTINUISTA | 0.79 |
| AAPL | vol20 | 20 | REVERSIONISTA | 0.78 |
| KO | vol20 | 60 | REVERSIONISTA | 0.76 |
| KO | vol20 | 20 | CONTINUISTA | 0.75 |
| NVDA | rsi14 | 20 | CONTINUISTA | 0.75 |
| AAPL | momentum_12_1 | 5 | CONTINUISTA | 0.74 |
| NVDA | momentum_12_1 | 60 | CONTINUISTA | 0.74 |
| NVDA | vol20 | 60 | REVERSIONISTA | 0.74 |
| AAPL | rsi14 | 5 | CONTINUISTA | 0.72 |
| KO | vol20 | 5 | CONTINUISTA | 0.72 |
| NVDA | momentum_12_1 | 5 | CAMALEÓN | 0.68 |
| AAPL | vol20 | 5 | CAMALEÓN | 0.63 |
| NVDA | rsi14 | 5 | CAMALEÓN | 0.63 |
| KO | rsi14 | 5 | CAMALEÓN | 0.60 |
| KO | rsi14 | 20 | CAMALEÓN | 0.60 |

## Legenda de arquetipos (§6, umbrales pre-especificados)

- **CONTINUISTA**: ≥70% de celdas interpretables con mismo signo positivo (IC>0).
- **REVERSIONISTA**: ≥70% de celdas interpretables con mismo signo negativo (IC<0).
- **CAMALEÓN**: ≥60% de celdas con |IC| ≥ 0.05 (signo mixto, magnitud consistente).
- **INERTE**: celdas interpretables pero sin consenso de signo ni magnitud.
- **INSUFICIENTE**: <50% de celdas interpretables (cobertura insuficiente).

Los t están desflactados por N_ef = N/h. N efectivo acompaña siempre al t.