# Propuesta de Ampliación del Universo — 100+ Símbolos

**Fecha**: 2026-09-01 (actualizada 2026-09-01 operativo)
**Origen**: ROADMAP §1b — Trial #21 (Asimetría Direccional) cerró GRIS por cobertura DOWN insuficiente (mediana DOWN/fecha=4, piso=10).
**Estado**: APROBADA — OPERATIVO COMPLETADO (ingesta 2026-09-01, 95/95 cache, cobertura verificada).

---

## 1. Diagnóstico

El universo actual (50 símbolos) es 100% large/mega-cap. En un universo así, los movimientos
están altamente correlacionados: en cualquier fecha dada, la mayoría de los 50 suben o bajan
juntos. Resultado: el lado DOWN es estructuralmente escaso (mediana DOWN/fecha = 4, piso
requerido por el gate del trial #21 = 10). Solo 21% de las fechas tenían ≥10 símbolos DOWN.

**Solución**: agregar small/mid caps con menor correlación entre sí y con los large-caps.
Esto dispersa el comportamiento direccional y sube la mediana DOWN/fecha.

---

## 2. Universo actual (referencia)

**Fuente canónica**: `backend/scripts/fetch_universe_data.py` (`NEW_UNIVERSE`, 43 símbolos)
+ `_BASE_SYMBOLS` (7: SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA) = **50 únicos**.

El dashboard deriva de `backend/app/api/routes/opportunities_universe.py` que importa
`NEW_UNIVERSE` desde el script de fetch (fuente única, Tarea F, 2026-08-19).

Los 43 de NEW_UNIVERSE son todos large/mega-cap (META, TSLA, AVGO, LLY, JPM, WMT, V, UNH,
XOM, MA, ORCL, PG, COST, HD, JNJ, ABBV, BAC, MRK, CRM, KO, ADBE, PEP, AMD, NFLX, TMO, CVX,
CSCO, ACN, MCD, IBM, LIN, QCOM, GE, INTU, PM, CMCSA, DIS, TXN, CAT, AMGN, PFE, SPGI).

---

## 3. Criterio de selección para los ~52 adicionales

| Criterio | Valor | Por qué |
|----------|-------|---------|
| **Market cap** | $2B – $50B (tolerancia hasta ~60B si diversifica) | Small/mid cap real (excluye mega >$200B ya representadas) |
| **Historia** | Listadas antes de 2019, verificado 2015-01-01 con datos | ≥7 años de datos (2019→2026), compatible con ventanas walk-forward |
| **Liquidez** | ADTV ≥ 500k shares (estimado) | Asegura datos OHLCV fiables y spreads manejables |
| **Diversificación** | ≤10 por sector | Evita sobrerrepresentación; busca correlación baja entre los nuevos |
| **Tipo** | Common stock (no ETF, no ADR oscuros) | Consistencia con el universo actual |
| **Verificación** | yfinance 1.2.0 batch 2015-01-01→2015-12-31 + info marketCap 2026-09-01 | Descarta delistados/adquiridos y sin historia |

---

## 4. Lista candidata (52 símbolos, por sector) — CORREGIDA Y VERIFICADA

**Correcciones 2026-09-01**: verificación yfinance detectó 8 tickers no viables en la propuesta v1:
ANSS (adquirida por SNPS 2024, delistada), SPLK (adquirida por Cisco 2024, delistada),
SQ (ticker migrado a XYZ 2025), ZS/DDOG/NET/CRWD (IPO 2018-2019, sin datos 2015), COIN (IPO 2021).
Reemplazados por alternativas con historia ≥2015 y cap SMID verificada (ver §4b).

### Tecnología / Software (10)
| Ticker | Nombre | Cap 2026-09-01 | Verif 2015 | Rationale |
|--------|--------|----------------|------------|-----------|
| SNPS | Synopsys | ~80B* | OK 2015-01-02 | EDA software, mid-cap estable |
| CDNS | Cadence Design | ~70B* | OK 2015-01-02 | EDA, complementario a SNPS |
| TYL | Tyler Technologies | 15.2B | OK | Gov-tech SaaS, reemplaza ANSS |
| PTC | PTC Inc | ~22B | OK | Industrial software (CAD/PLM) |
| AKAM | Akamai | 15.6B | OK | CDN/security, reemplaza SPLK |
| FFIV | F5 Networks | 23.1B | OK | App delivery, reemplaza DDOG |
| EPAM | EPAM Systems | 6.1B | OK | Digital engineering, reemplaza NET |
| CHKP | Check Point | 14.2B | OK | Cybersecurity, reemplaza ZS |
| PANW | Palo Alto Networks | ~120B* | OK | Cybersecurity large-mid (conservar) |
| QLYS | Qualys | 6.4B | OK | Cloud security, reemplaza CRWD |

### Semiconductores / Hardware (6)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| MRVL | Marvell | ~70B* | OK | Data center chips, menos correlacionado con NVDA/AMD |
| SWKS | Skyworks | ~10B | OK | RF chips, ciclo diferente |
| QRVO | Qorvo | ~4B | OK | RF/movilidad |
| MPWR | Monolithic Power | ~20B | OK | Power management ICs |
| AMAT | Applied Materials | ~150B* | OK | Equipment, ciclo semi diferente a las fabless |
| LRCX | Lam Research | ~80B* | OK | Equipment, complementario a AMAT |

### Salud / Biotech / Devices (7)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| DXCM | DexCom | ~30B | OK | CGM diabetes, crecimiento secular |
| ISRG | Intuitive Surgical | ~150B* | OK | Robótica quirúrgica |
| VEEV | Veeva Systems | ~30B | OK | SaaS salud |
| ALGN | Align Technology | ~15B | OK | Ortho/clear aligners |
| BIIB | Biogen | ~30B | OK | Biotech large-mid |
| REGN | Regeneron | ~90B* | OK | Biotech, diferente ciclo a LLY/JNJ |
| ZTS | Zoetis | ~70B* | OK | Animal health |

### Financieros / Fintech (6)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| PYPL | PayPal | ~60B* | OK | Fintech payments |
| BR | Broadridge | 20.8B | OK | Fintech infra, reemplaza SQ |
| STAG | STAG Industrial | 7.3B | OK | REIT industrial (diversificador financiero), reemplaza COIN |
| AXP | American Express | ~180B* | OK | Payments/tarjetas |
| SCHW | Charles Schwab | ~120B* | OK | Brokerage |
| BLK | BlackRock | ~140B* | OK | Asset management |

### Industrial / Transporte / Logística (6)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| UPS | United Parcel Service | ~120B* | OK | Logística |
| UNP | Union Pacific | ~140B* | OK | Rail |
| DE | Deere & Company | ~90B* | OK | Agrícola/industrial |
| ETN | Eaton Corp | ~100B* | OK | Power management |
| PH | Parker-Hannifin | ~80B* | OK | Motion/control |
| WM | Waste Management | ~85B* | OK | Servicios, baja volatilidad |

### Consumo discrecional / Retail (4)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| MAR | Marriott International | ~75B* | OK | Hospitality |
| SBUX | Starbucks | ~100B* | OK | Consumo recurrente |
| RCL | Royal Caribbean | ~30B | OK | Cruises, alta volatilidad |
| DRI | Darden Restaurants | ~15B | OK | Restaurantes |

### Energía / Materiales (5)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| SLB | Schlumberger | ~70B* | OK | Oilfield services |
| OKE | ONEOK | ~50B | OK | Midstream gas |
| VLO | Valero | ~40B | OK | Refinación |
| FCX | Freeport-McMoRan | ~20B | OK | Cobre/minería |
| NEM | Newmont | ~20B | OK | Oro |

### Real Estate / Utilities (5)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| PLD | ProLogis | ~100B* | OK | REIT logístico |
| EQIX | Equinix | ~80B* | OK | REIT data centers |
| DLR | Digital Realty | ~45B | OK | REIT data centers |
| WELL | Welltower | ~50B | OK | REIT healthcare |
| XEL | Xcel Energy | ~30B | OK | Utility regulada |

### Comunicación / Medios (3)
| Ticker | Nombre | Cap | Verif | Rationale |
|--------|--------|-----|-------|-----------|
| TMUS | T-Mobile US | ~200B* | OK | Telecom |
| CHTR | Charter Communications | ~50B | OK | Cable/broadband |
| EBAY | eBay | ~28B | OK | E-commerce |

\* Cap >50B: excede criterio SMID ideal pero conservado por diversificación sectorial o por ser parte de propuesta v1 aprobada; el beneficio direccional principal vendrá de los 20+ tickers SMID puros (TYL, AKAM, FFIV, EPAM, CHKP, QLYS, BR, STAG, QRVO, MPWR, etc.) con baja correlación. Futuros refinamientos pueden rotar los mega hacia SMID más puros.

#### 4b. Detalle de reemplazos (trazabilidad)

| Original | Motivo descarte | Reemplazo | Cap | Historia |
|----------|-----------------|-----------|-----|----------|
| ANSS | Adquirida SNPS 2024, yfinance 404 delisted | TYL | 15.2B | OK 2015 |
| SPLK | Adquirida Cisco 2024, yfinance no timezone | AKAM | 15.6B | OK 2015 |
| DDOG | IPO 2019-09, sin 2015 | FFIV | 23.1B | OK 2015 |
| NET | IPO 2019-09, sin 2015 | EPAM | 6.1B | OK 2015 |
| ZS | IPO 2018-03, sin 2015 | CHKP | 14.2B | OK 2015 |
| CRWD | IPO 2019-06, sin 2015 | QLYS | 6.4B | OK 2015 |
| SQ | Ticker migrado a XYZ 2025, 404 | BR | 20.8B | OK 2015 |
| COIN | IPO 2021-04, sin 2015/2019 | STAG | 7.3B | OK 2015 |

---

## 5. Resumen

| Categoría | Count |
|-----------|-------|
| Universo actual | 50 (7 base + 43 NEW_UNIVERSE) |
| Propuesta adicional (corregida) | 52 (verificados 2015) |
| **Total proyectado** | **102** |
| Verificados con datos 2015 | 52/52 (100%) |
| SMID puro ($2-50B) | ~28/52 (54%) |
| Large-mid/mega (>50B) | ~24/52 (46% conservados por sector) |

**Sectores cubiertos**: Technology 10, Semiconductors 6, Healthcare 7, Financials 6, Industrials 6, Consumer 4, Energy/Materials 5, REITs/Utilities 5, Communications 3.

---

## 6. Ejecución operativa (2026-09-01)

1. **Verificar** — HECHO (yfinance batch 2015 + info marketCap, 8 reemplazos por delistados/IPO cortos).
2. **Agregar** — HECHO `fetch_universe_data.py` 43→95 (diff 43+52), `opportunities_universe.py` fallback sincronizado.
3. **Ingesta** — HECHO `fetch_universe_data.py` OK 95/95 (cache 2015-01-02→2026-08-31, 2931 filas/símbolo, 130 parquet en backend/data/cache y data/cache sincronizados).
4. **Confirmar** — HECHO `SYMBOLS` 102 (7 base + 95) verificado vía import.
5. **Cobertura** — HECHO (ver §8): universo 102 pasa gate §5 en 2/3 ventanas (antes 0/3), mediana DOWN 4→11.

## 6b. Artefactos

- `backend/scripts/fetch_universe_data.py:12` — NEW_UNIVERSE expandido documentado por bloques sectoriales
- `backend/app/api/routes/opportunities_universe.py:35` — SYMBOLS 102, fallback sincronizado
- `backend/data/cache/*.parquet` + `data/cache/*.parquet` — 130 archivos, rsync vigente
- Este archivo — propuesta v2 corregida + verificación + cobertura

---

## 7. Riesgos / Notas

- **Caps >50B** (# marcados *): varios candidatos superan el corte SMID ideal; se conservan por diversificación pero futuros ciclos deberían rotarlos hacia SMID más puros (ej. MANH, PAYX, ATO, EWBC, SKX, TXRH verificados como alternativas).
- **Correlación real** debe medirse empíricamente post-ingesta; la diversificación por sector no la garantiza.
- **Fuente única**: todo cambio va en `fetch_universe_data.NEW_UNIVERSE`; el fallback en `opportunities_universe.py` se sincroniza en §6 paso 2.
- **Cuota yfinance**: ingesta 52 tickers × ~10 años ≈ 52 descargas; usar `download_data` (cache backfill/refresh) para no re-descargar los 50 existentes.

---

## 8. Verificación de cobertura (post-ingesta, 2026-09-01)

**Método**: closes.parquet → ret_imp = P(t-1)/P(t-1-63)-1, UP≥+10% DOWN≤-10% (idéntico a `diagnose_asimetria_direccional.py:132-140`), ventana 2019-01-01→2026-08-04, gate §5 (≥75 fechas ambos lados + ≥10 símb/lado mediana).

| Universo | W1 2020-21 | W2 2022-23 | W3 2024-26 | TOTAL 2019-26 |
|----------|------------|------------|------------|---------------|
| **50 (original)** | both 1 (0.2%) UP 19 DOWN 2 → NO | both 24 (4.8%) UP 10 DOWN 6 → NO | both 83 (12.8%) UP 16 DOWN 5 → NO | both 108 (5.7%) UP 15 DOWN **4** (p50) |
| **102 (ampliado)** | both 114 (22.6%) UP 43 DOWN 6 → NO | both 245 (48.9%) UP 19 DOWN **16** → **SI** | both 485 (74.7%) UP 33 DOWN **15** → **SI** | both 907 (47.6%) UP 33 DOWN **11** (p50) |

- **0/3 → 2/3 ventanas interpretables** (§5: 1 sola → GRIS automático; ahora 2/3 habilitan veredicto).
- **Mediana DOWN 4→11** (+175%), cruza piso 10; p90 17→37 muestra dispersión ganada.
- **W1 sigue NO** por mediana DOWN 6 (<10): 2020-21 fue bull extremo, ni 102 lo rescata; W2/W3 sí pasan holgados.
- **Implicancia**: próximo trial de asimetría (slot 29, pre-registro nuevo, jamás edición retroactiva del #21) ya puede correr sobre universo 102 con potencia suficiente en W2/W3. W1 quedará NO interpretable — documentar como limitación, no re-intentar con X distinto sin pre-registro nuevo.

**Comando de reproducción**:
```bash
PYTHONPATH=backend ~/Desktop/fortress_core/backend/.venv/bin/python /tmp/coverage_102.py
# Gate full con indicadores (más lento, incluye fwd_ret):
# PYTHONPATH=backend ~/Desktop/fortress_core/backend/.venv/bin/python -m scripts.diagnose_asimetria_direccional  # genera trial21_*.txt con gate
```
