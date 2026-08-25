# Plan maestro — de la investigación a la validación prospectiva

Arquitectura completa acordada con Boris (2026-08-25). Claude Code orquesta;
tres agentes ejecutan en dos frentes paralelos que convergen en un mismo
sistema (`ARBOL_DECISION_ESTRATEGICO.md` + `PROPUESTA_PAPER_TRADING_PROSPECTIVO.md`).
No hay "modelo nuevo" separado — todo alimenta el mismo ledger, el mismo árbol,
el mismo ensamble.

## Roles

| Agente | Frente | Por qué este rol |
|---|---|---|
| **Kilo** | Investigación (Camino A del árbol) | Rigor de pre-registro demostrado en §44/§45/§46 — sigue el trabajo que ya domina |
| **Cline** | Construcción — cliente Alpaca + ledger | Disciplina de verificar-antes-de-construir (Brecha 5: no arregló lo que ya estaba bien) |
| **OpenCode** | Construcción — pipeline diario + reportes | Ya opera procesos automatizados (coordinó `data_updater`) y hace verificación de fidelidad (explore agent en §45) |

Ningún agente se interrumpe a mitad de tarea — este plan define el PRÓXIMO
paso de cada uno, no reemplaza lo que están haciendo ahora.

## Frente 1 — Investigación (Kilo, continuo)

Sigue el árbol de decisión tal cual está escrito:

1. Cerrar §46 (Brecha 2, en curso) — auto-cierre, gate de merge.
2. A5 — Quality+Value sistemático (Buffett's Alpha): pre-registro nuevo,
   misma disciplina, corre en paralelo sin competir con Frente 2.
3. Lo que el árbol indique después, según lo que A5 y A1 arrojen.

No tiene fecha de cierre fija — depende de cuántas hipótesis hagan falta
agotar. Es investigación, no ingeniería: el calendario lo pone la evidencia.

## Frente 2 — Construcción (Cline + OpenCode, en paralelo)

### Semana 1

- **Cline**: extender `AlpacaPaperClient` (`execution_costs.py`) con lectura
  de cuenta/posiciones (`GET /v2/account`, `GET /v2/positions`). Integrar con
  `signal_ledger.py` para que cada orden de papel genere una fila real
  (entrada, salida pendiente, `pnl_r` a completar al cierre).
- **OpenCode**: diseñar y construir el pipeline diario (mismo patrón que
  `com.fortresscore.dataupdater.plist`) — genera la señal con la definición
  CONGELADA (la misma de la validación OOS fresca, sin re-optimizar), la
  manda como orden de papel vía el cliente que construye Cline.

**Checkpoint semana 1**: correr el pipeline manualmente un día completo,
verificar que la orden se ejecuta y el `signal_ledger` registra bien. Sin
esto verificado, no se instala el cron.

### Semana 2

- **Cline**: reporte mensual — Sharpe realizado del mes vs. lo que el
  backtest predijo para ese período (no % crudo, Sharpe). Bitácora acumulada
  por variante.
- **OpenCode**: instalar el pipeline como proceso automático (launchd),
  correr en modo observación 1-2 semanas antes de confiar en que corre solo
  sin supervisión.

**Checkpoint semana 2**: pipeline corriendo solo, primer reporte generado
(aunque sea con pocos días de datos — valida el mecanismo, no la señal).

### Mes 1 en adelante — acumulación (no es fase de ingeniería)

El sistema corre solo. Cada mes cierra con veredicto (Sharpe realizado vs
esperado). Cuando A5 (u otro candidato del árbol) cierre CUMPLE, se agrega
como variante nueva al ensamble — tarea de construcción chica y puntual, no
un nuevo proyecto.

**No hay fecha de "listo"**: como hablamos con el ejemplo de Jim Simons, esto
madura con tiempo de calendario real, no con más ingenieros. El objetivo de
Dalio (15-20 fuentes no correlacionadas) se alcanza sumando candidatos
validados del árbol a medida que aparecen, no de una vez.

## Carta Gantt

```
                          Sem1   Sem2   Mes1   Mes2   Mes3 ... MesN
Kilo -- cierre §46         ██
Kilo -- A5 Quality+Value        ████████████ (sin fecha fija, evidencia manda)
Cline -- cliente Alpaca+ledger  ██
Cline -- reporte mensual              ██
OpenCode -- pipeline diario     ████
OpenCode -- launchd + observ.          ████
Acumulación prospectiva (ambos)              ████████████████████████ (continuo)
Checkpoint semana 1              ▲
Checkpoint semana 2                     ▲
Primer cierre mensual real                     ▲
Candidato nuevo se suma al ensamble (si aplica)       ▲ (cuando cierre, no antes)
```

## Gate de aprobación (vigente, sin cambios)

Todo lo que cualquiera de los tres construya pasa por el mismo protocolo ya
establecido (`PLAN_HANDOVER_48H.md` §1.1): preparar completo, `.pending-merge.md`,
aprobación de Claude Code antes del commit final a `main`.

## Qué NO cambia

- La regla no negociable sigue vigente: ningún trial de investigación nuevo
  sin pre-registro y decisión de Boris (ONBOARDING.md #1).
- No se conecta a broker real en ningún momento de este plan — todo es
  dinero sintético (Alpaca paper), sin excepción, hasta que el ensamble
  acumule evidencia prospectiva suficiente y Boris decida lo contrario
  explícitamente.
- La construcción no compite por presupuesto de Bonferroni — solo la
  investigación (Frente 1) consume slots del ledger.
