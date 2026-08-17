# Dashboard institucional nivel dios — panel de apoyo a decisión (frontend_v2)

**Estado**: plan aprobado para implementación. Origen: pedido del usuario 2026-08-17
("necesito uno nivel dios", estética TradingView/investing.com, agente institucional).

## 1. Objetivo y marco de honestidad (no negociable)

Panel de **apoyo a la decisión** para un agente institucional, construido sobre lo único
que el proyecto tiene verificado. Restricciones heredadas de ONBOARDING.md (reglas #1 y #4):

- El proyecto NO tiene señal comercial validada (28 trials, todas NO CUMPLE o cerradas).
  El panel NUNCA presenta veredictos como "predicción"; los presenta como **apoyo con
  evidencia citada** (n, ventana, artefacto). Badge global permanente:
  "Apoyo a decisión — sin señal comercial validada".
- Cada etiqueta de resultado proyectado usa umbrales **pre-registrados** (ver §3).
- Filosofía del usuario, ya verificada como la parte más sólida del proyecto: la ganancia
  está en el **manejo de riesgo y la salida**, no en la entrada. Entrada = calidad vs precio
  (Buffett); salida = cuando se pierde la tesis/premisa de entrada; perder poco > ganar
  mucho (loss-first, Dalio/risk-parity). El "Exit Thesis Monitor" (§5.4) ES la feature
  central del panel.

**Contradicción resuelta**: "precios de entrada/salida" se muestran como **zonas mecánicas
del motor** (gates, stops EVT §19, barreras M1, plan de salida de 4 mecanismos), no como
niveles predichos. Es lo único que no viola la regla #4.

## 2. Decisión de alcance (resuelta)

- **`frontend_v2/` nuevo y paralelo** — NO se toca `frontend/` mientras Claude Code lo
  reconstruye. Comparten solo el contrato HTTP del backend (nada se mueve). Migración/
  reemplazo: solo al pasar los acceptance criteria.
- **Gráficos**: Lightweight Charts (open-source de TradingView) como carta principal con
  overlays propios + widget TV embebido como vista secundaria. Ambos, como pidió el usuario.
  Datos: EOD del cache (yfinance); se etiqueta siempre "al último cierre".

## 3. Pre-registro de etiquetas de resultado proyectado (ANTES de implementar UI)

Escribir en PLAN_MEJORA_MATEMATICA.md como sección de documentación de mapeo (NO consume
slot de trial: es presentación de evidencia existente, no hipótesis nueva):

| win_prob calibrado (motor) | Etiqueta | Evidencia citada obligatoria |
|---|---|---|
| ≥ 0.70 | GANANCIA_PROYECTADA (alta selectividad) | VPP real 87.5% (n=8, diagnóstico asesoría 2026-08-17) |
| 0.65–0.70 | GANANCIA_PROYECTADA | VPP 73.7% (n=19) |
| 0.55–0.65 | NEUTRO (leve) | cola media sin selectividad medida |
| 0.45–0.55 | NEUTRO | sin selectividad |
| < 0.45 | RIESGOSA / PERDIDA_PROYECTADA | no hay evidencia de selectividad en esta cola → se muestra como "sin apoyo estadístico" |

Regla adicional: cuando un casillero tiene n<30, la UI muestra el n junto a la etiqueta.
Régimen DEFLATION: banner global que bloquea etiquetas de entrada (mecánica real del motor,
`decision.py` ya lo hace).

## 4. Backend — endpoints nuevos (FastAPI, patrón del repo)

Todos en `backend/app/api/routes/advisor.py` (router `/api/advisor`), solo lectura:

1. `GET /api/advisor/universe` — consolida por símbolo en UNA llamada para la mesa:
   estado INVERTIR/VIGILAR/NO_INVERTIR + razón, win_prob + etiqueta §3, gates crudos
   (adx/rsi/volume/ema), último cierre, distancia a EMA50/200, stop EVT implícito
   (`var_mult×σ_EWMA` + floor, leer la fórmula real de `adaptive_risk.py`/EVT §19),
   nivel de barrera M1 vigente (TP/SL/time del motor), transición vs día previo, y
   `thesis_status` (ver §5.4). Reutiliza `_compute_ticket` de decision.py — NO reprogramar.
2. `GET /api/advisor/{symbol}` — detalle: serie OHLCV EOD completa del cache, indicadores
   para overlays (EMA50/200, bandas EVT, barreras M1), fundamentals snapshot desde
   `edgar_fundamentals.py` si hay cobertura para el símbolo (si no: campo null + flag
   "sin cobertura EDGAR" — NUNCA inventar), plan de salida (`_exit_plan`), historia de
   estados de `decision_states.json`, y el intervalo M2.
3. `GET /api/advisor/evidence` — resumen del ledger para el footer de confianza:
   n_trials por familia, umbral vigente, últimos veredictos (lee `trial_registry.json`
   vía `trial_registry.py`, no parsear a mano).

Tests: patrón `tests/test_advisor_api.py` (asyncio.run + monkeypatch como el resto de la
suite). Ningún endpoint dispara LLM (los de governance quedan donde están, bajo rate limit).

## 5. Frontend `frontend_v2/` — diseño nivel dios

### 5.1 Stack (el del repo, sin inventar)
React 18 + TypeScript + Vite + Tailwind. Gráficos: `lightweight-charts` (nueva dep),
`recharts` (ya usada en el repo legacy) para curvas secundarias. Fetching: hook propio
simple con cache + revalidación (patrón `hooks/` existente), sin data-fetcher pesado.

### 5.2 Identidad visual (TradingView/investing.com)
- Dark theme por defecto: fondo #131722 (TV exacto), paneles #1e222d, texto #d1d4dc,
  verde #26a69a / rojo #ef5350, tipografía mono para números tabulares.
- Densidad institucional: tablas compactas, sparklines inline, cero decoración vacía.
- Responsive desktop-first (usuario de escritorio).

### 5.3 Páginas (3 + footer)
1. **Mesa de decisión** (home): tabla del universo 50 con estado coloreado, win_prob,
   etiqueta §3, último cierre, distancia % a EMA50/200, stop EVT, transición (flecha
   ↑↓ vs ayer), filtro/orden por columna, banner de régimen. Click → detalle.
2. **Detalle por símbolo**:
   - Carta principal Lightweight Charts: velas EOD + EMA50/200 + banda de stop EVT +
     líneas horizontales de barreras M1 (entrada/TP/SL/time-stop) + marcador del día de
     la decisión. Toggle a widget TradingView embebido (misma página, vista 2).
   - Panel de decisión: tesis de entrada (qué gates pasaron y por qué), zona de entrada
     mecánica, plan de salida de 4 mecanismos con niveles concretos, intervalo M2,
     etiqueta proyectada con su n de evidencia.
   - Panel fundamental: snapshot EDGAR si hay cobertura, si no estado "sin cobertura".
3. **Curvas**: equity del baseline + drawdown + Monte Carlo existente (recharts),
   distribución de trades — la parte "portfolio" del panel.
4. **Footer permanente de evidencia**: ledger de trials (familia, n, umbral, últimos
   veredictos) — la firma de confianza institucional del proyecto.

### 5.4 Exit Thesis Monitor (feature central, filosofía del usuario)
Por cada símbolo en estado INVERTIR (o con posición histórica en `decision_states.json`):
- Guardar la foto de la entrada: fecha, gates que pasaron, régimen, win_prob de entrada.
- Monitorear diariamente contra el ticket actual: ¿se rompió algún gate de la tesis?
  ¿cambió el régimen a hostil? ¿el precio cruzó la barrera de tiempo/SL?
- UI: semáforo por tesis: VIGENTE / DEGRADADA (n gates rotos) / **TESIS ROTA — evaluar
  salida** + la razón mecánica concreta. Esto operacionaliza "se sale cuando se pierden
  los fundamentos de la entrada" sin inventar señal: la salida es mecánica del motor +
  tesis, con recordatorio loss-first (riesgo de cola EVT visible junto a cada posición).
- Implementación: endpoint nuevo `GET /api/advisor/theses` (compara estado actual vs
  snapshot de entrada persistida; snapshot se escribe al entrar un símbolo a INVERTIR,
  en el mismo `decision_states.json` extendido — verificar esquema actual primero).

## 6. Tareas en orden (cada una termina verificable)

1. Escribir §3 (mapeo de etiquetas) en PLAN_MEJORA_MATEMATICA.md como doc. Verificar
   contra el artefacto de asesoría (`asesoria_combinaciones_*.txt`) que los VPP/umbrales
   citados son los reales — no copiar de memoria.
2. Backend: `advisor.py` (3 endpoints + theses) + tests. `pytest` verde.
3. Scaffold `frontend_v2/` (copiar config de `frontend/` como base: vite.config,
   tailwind, tsconfig), tokens de color §5.2, Layout con navegación.
4. Mesa de decisión consumiendo `/api/advisor/universe`.
5. Detalle por símbolo con Lightweight Charts + overlays + panel de decisión.
6. Widget TV embebido (vista secundaria) + ver que cargue offline-graceful.
7. Exit Thesis Monitor completo.
8. Curvas + footer de evidencia.
9. Acceptance: `tsc` limpio, `npm run build` OK, `pytest` verde, `ruff` limpio;
   smoke manual: abrir las 3 páginas con el backend corriendo, verificar contra 3
   símbolos (uno INVERTIR, uno VIGILAR, uno sin cobertura EDGAR) que los datos
   mostrados coinciden con la respuesta cruda del endpoint (regla #1: verificar
   contra el artefacto, nunca contra lo que "debería mostrar").
10. Docs: ROADMAP fila nueva, README de frontend_v2, SESSION_LOG; commit + push.

## 7. Riesgos y fallos previstos

- **Colisión con Claude Code**: se evita por construcción (directorio separado). Si su
  reconstrucción termina antes, NO se integra nada de frontend_v2 hacia frontend/ sin
  decisión explícita del usuario.
- **EOD, no realtime**: todo se etiqueta "al último cierre"; el widget TV sí muestra
  realtime de terceros — diferencia declarada en la UI (evita engaño).
- **yfinance inestable**: los endpoints de advisor no re-descargan; leen el cache
  actualizado por el cron diario (instalado hoy). Si el cache está viejo (>2 ruedas),
  el panel muestra staleness explícito.
- **Cobertura EDGAR parcial (5/50)**: sin cobertura = UI honesta "sin datos", nunca
  fallback inventado.
- **LLM**: cero uso en advisor (costo/rate limit); governance panel queda fuera de
  alcance de esta versión.

## 8. Fuera de alcance (explícito)

- Conexión a broker real (bloqueada por decisión de producto hasta edge validado).
- Datos intradía/HFT, websockets de precios (decisión de producto cerrada).
- Nueva investigación de señales (cualquier indicador nuevo pasa por el proceso de
  trials pre-registrados — el dashboard muestra evidencia, no crea nueva).
- Reemplazo de `frontend/` (fase posterior, decisión del usuario).

## 9. Pendiente explícito

Ninguno bloqueante. Nota: el runner M4 mide costos reales de ejecución mañana al open;
el número resultante puede ajustar la presentación de "costo por trade" en el panel
(campo reservado, se llena cuando exista el artefacto).
