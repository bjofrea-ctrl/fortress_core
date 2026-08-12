# Investigación externa: gobernanza multi-agente LLM, risk-mgmt-first y trading cuántico

> ROADMAP item 13 (Tanda D, 2026-08-12). Research web con fuentes primarias verificadas
> (papers en arXiv/JSTOR/RePEc, sitios de conferencias). Nada de esto toca el motor —
> es insumo para decisiones de arquitectura y honestidad sobre el enfoque.

## 1. Gobernanza multi-agente LLM en trading — el estado del arte

**TradingAgents** (UCLA/MIT/Tauric, arXiv:2412.20138, revisado jun-2025; poster ICML 2025
"Multi-Agent Systems in the Era of Foundation Models"; 182 citas según Semantic Scholar):
la arquitectura más citada del espacio. Reproduce una firma: analistas fundamental /
sentimiento / técnico, **equipo de BULL y BEAR que DEBATEN y escriben informes
separados**, un **equipo dedicado de risk management que vigila exposición**, y un
trader que sintetiza. El framework existe en GitHub (github.com/TauricResearch/TradingAgents).
Relevancia: el diseño de fortress_core (triada bull/bear/contrarian + Controller/Judge +
GovernanceSystem con NIM) es estructuralmente el mismo patrón que la academia valida
como "firma simulada" — pero con una diferencia VENTAJOSA: el debate acá está limitado,
los agentes de decisión son deterministas y no hay agente que "opine" sobre órdenes.

**FinCon** (NeurIPS 2024): jerarquía manager-analista con refuerzo verbal conceptual.
Prefiere memoria y roles tipo organización de inversión real.

**Crítica clave — TradeTrap** ("Are LLM-based Trading Agents Truly Reliable and
Faithful?", 2025, vía Semantic Scholar): muestran que **pequeñas perturbaciones en un
solo componente se propagan por el loop de decisión y producen concentración extrema,
exposición desbocada y drawdowns grandes en ambos tipos de agentes**. Su conclusión:
los agentes autónomos LLM pueden ser sistemáticamente desviados a nivel sistema.
Validación externa de la decisión de fortress_core de mantener el loop de decisión
DETERMINISTA y LLM solo como capa de evaluación/gobernanza — justo lo que TradeTrap
recomendaría.

**Gobernanza de sistemas multi-agente**: "Risk Analysis Techniques for Governed
LLM-based Multi-Agent Systems" (2025, reporte tipo guidance): analizar agentes
individuales NO garantiza seguridad del sistema (riesgo emergente, amplificación);
exige governance frameworks específicos. Refuerza el principio del proyecto: el
GovernanceSystem (con NIM) existe porque la tríada sola no se gobierna sola.

## 2. Risk-mgmt-first para operadores chicos — la evidencia definitiva

**Barber & Odean, "Trading Is Hazardous to Your Wealth"** (Journal of Finance 55(2),
773–806, 2000; 1.144 citas en RePEc; SSRN 219228): 66.465 cuentas en un broker con
descuento, 1991–1996. Los hogares que más operan: **11.4% anual vs 17.9% del mercado**;
el hogar promedio factura un **turnover del 75% anual**. Conclusión: el trading activo
es una penalización masiva; explicación dominante: overconfidence.

**Barber, Lee, Liu & Odean** (Taiwan, 2008): en el mercado con TODOS los trades de
inversores individuales (1991–1995), los costos de transacción reducen el retorno
agregado del portafolio individual en **3.8 puntos porcentuales por año**.

**Day-trading survival** (Barber et al., en "Learning Fast or Slow", AEA 2019y citas
interiores): tasas de supervivencia de day traders a 1/2/3 años: **44% / 24% / 15%**.
El 97.5% no abandona dentro del primer mes — la mayoría arde lento.

Lectura para fortress_core: el "risk-mgmt-first para operadores chicos" no es
preferencia estética — es la única evidencia estadística robusta de qué mata a los
retail traders: UNA: over-trading (flujo), DOS: costos. El sistema ya internaliza
eso: gate de entrada restrictivo, DSR≥0.90 pre-registrado, costos 0.15%/lado en el
backtest, y el hallazgo de hoy (gap-reversion: bruto ~0, neto −0.30%/trade) es la
misma lección de Barber-Odean en miniatura.

## 3. Trading cuántico — veredicto: marketing > sustancia (para este proyecto)

Papers reales (QAOA/annealing para optimización de portafolio): TUM (QAOA Based
Portfolio Optimization, 2025), TNO (Multi-Objective Portfolio Optimization Using a
Quantum Annealer, 2024), "End-to-End Portfolio Optimization with Quantum Annealing"
(arXiv 2504.08843, con costos de transacción multi-period), "Constrained Portfolio
Optimization via QAOA with XY-Mixers" (2026). Estado del arte honesto:

- Los resultados publicados son **simulaciones o hardware NISQ experimental**; el
  consenso es que el valor aparece en problemas combinatorios con MILES de activos
  + constraints (liquidez, sector, regulatorio) — imposible de igualar por MIP
  clásico en runtime.
- Los pipelines útiles hoy son **híbridos** (cuántico sondea candidatos, clásico
  refina y valida).
- Un portafolio de 50 tickers con constraints simples se resuelve en milisegundos
  con QP clásico (cvxpy/scipy) — el problema NO es el problema correcto para
  cuántica.

Conclusión: para un operador chico con 50 símbolos y un Mac, el trading cuántico no
aporta NADA hoy — es un campo serio pero con el valor en un régimen de escala que
este proyecto nunca va a tocar. La primera auditoría lo salteó por correcto
escepticismo; esto lo confirma con fuentes.

## 4. Síntesis para el proyecto

1. El patrón multi-agente LLM de fortress_core es el dominante en la literatura
   (TradingAgents/FinCon) y su variante acá (loop determinista + LLM como evaluador)
   es la defensa correcta contra el único fallo crítico documentado (TradeTrap).
2. La disciplina de costos y gate del proyecto es exactamente lo que los datos de
   Barber-Odean dicen que separa a los traders que sobreviven: no sobreoperar.
3. Trading cuántico: documentado como no-relevante y cerrado. No perseguir.

Fuentes: arXiv:2412.20138 (TradingAgents) · NeurIPS 2024 FinCon · TradeTrap via
Semantic Scholar · Barber & Odean 2000 JF 55(2) doi:10.1111/0022-1082.00226 ·
Barber-Lee-Liu-Odean RFS 2008 · TUM/TNO/arXiv 2504.08843 (quantum portfolio).
Busquedas: 2026-08-12.