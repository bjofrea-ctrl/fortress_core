# Plan 48h — implementación operativa a cargo de OpenCode

Escrito por Claude Code, 2026-08-25. **Aclaración de roles (2026-08-25, pedido
explícito de Boris)**: esto NO es un handover completo del rol de coordinador.
Claude Code sigue siendo la autoridad de planificación, en consulta con
OpenCode (dinámica ya establecida en esta sesión) — lo que cambia es que
Claude Code deja de hacer el sondeo operativo continuo (créditos bajos) y
esa parte queda a cargo de OpenCode, con Cline y Kilo implementando. Para
cualquier decisión de planificación NUEVA (no cubierta en este documento —
ej. una línea de investigación nueva, un cambio de arquitectura, "nivel
dios"), OpenCode la plantea y espera que Boris la traiga de vuelta a Claude
Code para consulta conjunta antes de ejecutar — no decide unilateralmente
solo por tener más presupuesto de créditos disponible en este momento.

Objetivo de este documento: que la disciplina del proyecto no se pierda en
el traspaso operativo. Leer completo antes de actuar.

## 1. Lo que sigue en curso — cerrar con el criterio YA aprobado, no re-abrir

- **§43 PBO/CSCV fidelidad completa** (PID 66163, test-opencode-orca): tiene
  autorización completa de auto-cierre. Al terminar: verificar los 5 checks
  de fidelidad de §43.5, aplicar el criterio §43.4 mecánicamente (sin
  interpretar), documentar en el commit la cadena de autorización real
  ("coordinador Claude Code caído por límite de uso; Boris autorizó a
  OpenCode actuar autónomamente; el paso formal --timing/forecast de §43.6
  no se completó antes de lanzar la corrida completa" — esto es un HECHO
  histórico, no se blanquea ni se omite), registrar en `trial_registry`,
  actualizar ROADMAP.md, commitear en el worktree.
- **§45 EVT-stops v2** (PIDs 46372/46374/51612, test-kilo-orca): Kilo tiene
  autorización completa de auto-cierre. El pre-registro ya está aprobado
  (commit `dd47569`) con la regla de consumo de ledger acordada: si el gate
  F7 (activación ≥50% shares_by_risk en ≥2/3 ventanas) falla, NO se registra
  en el ledger ni consume slot — se documenta como intento inválido, mismo
  tratamiento que el Trial #15 original. Si F7 pasa, se registra sea CUMPLE
  o NO_CUMPLE.

**No re-abrir el diseño de ninguno de los dos.** Ya fueron revisados y
aprobados. Solo verificar que el cierre real coincide con lo aprobado antes
de mergear a main.

## 1.1 Gate de aprobación de merges (2026-08-25, autorizado por Boris)

**Ningún merge a `main` se completa (el `git commit` final tras el
cherry-pick) sin aprobación explícita de Claude Code.** Protocolo:

1. El agente prepara el merge COMPLETO: `git cherry-pick -n` (rango
   completo), corre tests/build él mismo, verifica que todo esté limpio —
   pero **NO ejecuta el commit final**.
2. Escribe (o sobreescribe) `/Users/boris/Desktop/fortress_core/.pending-merge.md`
   (gitignoreado, no se trackea) en la raíz del repo con: qué se va a
   mergear (commits/rango origen), resumen de qué se verificó (tests
   corridos, resultado exacto), y cualquier duda o riesgo detectado.
3. Claude Code tiene un `Monitor` que detecta este archivo apareciendo o
   cambiando y revisa apenas se entera — no hace falta avisar por otro
   canal, pero un mensaje directo por `orca terminal` acelera la revisión.
4. Claude Code aprueba (responde "adelante" o similar) o pide cambios. Solo
   con la aprobación explícita el agente completa `git commit` (+ push si
   corresponde).
5. Excepción: cambios ya pre-aprobados en este mismo documento (ej. cierres
   de trials con criterio ya revisado como §45) igual pasan por el gate —
   la aprobación de DISEÑO no es aprobación de MERGE, son pasos distintos.

## 2. Disciplina de merge a main (no negociable)

- **Nunca usar `git merge-tree` (legacy)** — da conflictos espurios,
  verificado en esta sesión. Usar `git cherry-pick -n <primer-commit>^..<último-commit>`
  (rango completo, no solo el commit final).
- Antes de commitear un merge: correr la suite/tests VOS MISMO en la rama
  destino (no confiar en el reporte del agente que hizo el trabajo). Para
  backend: `cd backend && .venv/bin/python -m pytest -q` (tarda ~18-20 min,
  correr en background y esperar el resultado real). Para frontend:
  `npm --prefix frontend ci && npm --prefix frontend run test`.
- Si `git status` muestra "nothing to commit" después de un `git add` + intento
  de commit, revisar si el auto-backup (corre cada 10-20 min) se adelantó y
  absorbió el staged commit en un `auto-backup: <timestamp>` genérico — no es
  un error, solo verificar con `git show --stat <hash>` que el contenido llegó
  completo. No hace falta reescribir el commit.

## 3. Regla no negociable del proyecto (ONBOARDING.md #1)

**Ningún trial nuevo (pre-registro + corrida) sin decisión EXPLÍCITA de
Boris.** Esto aplica a cualquier línea de investigación nueva, incluida
cualquier idea de "nivel dios" que surja — se propone, no se ejecuta sola.

## 4. Sobre "nivel dios" — qué NO proponer (ya verificado y refutado)

En esta sesión se revisaron DOS evaluaciones externas que proponían líneas
"nuevas" de investigación. Verificado contra ROADMAP.md y el código real:

- **Re-etiquetar por barreras + re-test momentum/RSI contra ese target**: YA
  CERRADO, §23 Triple Barrier (2026-08-16, Cline) → NO_CUMPLE.
- **Re-test sentimiento/fundamentales**: YA CERRADO DOS VECES — Fase 0.6
  (2026-08-12) NO_CUMPLE, y Tarea B/§27 FinBERT earnings sentiment
  (2026-08-17) NO_CUMPLE.
- **Condicionar momentum+RSI por régimen/sub-período temporal** (drift
  detector M5, o cualquier variante): la HIPÓTESIS de fondo ya se probó dos
  veces por vías distintas — §15 sub-período (2026-08-12) y Tarea P §42
  regime gating vía M3/HMM (2026-08-22) — ambas NO_CUMPLE. Un tercer método
  (ej. M5 KS-test) parte con prior bajo; si se propone, necesita pre-registro
  nuevo justificando por qué sería distinto, y decisión de Boris.
- **Correr el conformal engine (M2) sobre el score en walk-forward**: YA
  CERRADO, Trial #17 (2026-08-17) — VPP con abstención vs baseline, p=0.4347,
  no significativo.

**Lo único con fundamento real y genuinamente abierto**: formalizar cuándo
reintentar la validación OOS fresca de momentum+RSI — es CONDICIONAL al
tiempo (el trial de OOS fresca del 2026-08-22 dejó anotado "repetir con
nuevo pre-registro cuando el updater acumule más meses", DSR escala con
√T). No es accionable hoy, solo cuando el `data_updater` acumule
suficientes meses adicionales — verificar con `trial_registry` /
fecha del cache antes de proponerlo como si fuera nuevo.

**Hallazgo de código real, no de investigación**: `adaptive_risk.py:109`
(sizing, `compute_position_size`) usa `stop_distance = max(2×ATR,
price×position_stop)`, pero `:149` (`check_all_stops`, `REGIME_STOP_HIT`)
dispara solo con `position_stop%`, sin ATR. Es una decisión de riesgo, no
un bug a arreglar sin más — ya se le pasó a Kilo como FYI para que lo
documente en el marco de §45 si es relevante. No abrir como frente aparte
sin decisión de Boris (cambia cuánto arriesga cada posición realmente).

## 5. Cline

Libre desde el merge de commit `8859dbb` en main (tests de frontend + fixes
de degradación graceful, verificados). En standby deliberado — no se le
asignó tarea nueva para no generar carga de revisión mientras el coordinador
anterior tenía créditos bajos. Ahora que OpenCode coordina sin ese límite,
es una decisión válida asignarle algo bien acotado (no-investigación) si
surge algo concreto en el ROADMAP — pero seguir sin inventar trabajo por
inventar.

## 6. Trabajo ya cerrado en esta sesión (referencia)

- Kilo: Tarea M KAMA/HMA/Supertrend, NO_CUMPLE 0/9 (commit `ca8cebc` en main).
- Cline: infra de tests frontend + auditoría técnica sincronizada + 24 tests
  de vistas (commits `8859dbb` en main).
- Coordinador: backup versionado de `trial_registry.json` + CI corre tests
  de frontend (commits `c67a99c`, `ead5a2a` en main).

## 6.1 Auditoría externa (2026-08-25, glm-5.2) — verificada, alta calidad

Tercera evaluación externa recibida esta sesión, la de mejor calidad de las
tres: citó código real con números de línea, fue honesta sobre lo que no
pudo verificar (terminal bloqueado, no corrió pytest/git log). Claude Code
verificó lo que ella no pudo: los commits citados (1721a1e, 5edfe6e,
c67a99c) SÍ están en main. Cinco "brechas" propuestas, verificadas y
clasificadas:

- **Brecha 2 — M3 (regime_gate.py) como compuerta STANDALONE sobre el score
  compuesto del motor** (no condicionando un factor como hizo Tarea P/§42).
  **VERIFICADA como genuinamente inédita** — ROADMAP.md línea 343 dice
  textual: "el TRIAL que pruebe macro IC +0.198 GOLDILOCKS/−0.173 DEFLATION
  como compuerta sigue sin pre-registrar — decisión del usuario". **AUTORIZADA
  por Boris (2026-08-25)** — es la más sólida de las cinco, asignada a Kilo
  (ver abajo) como próximo pre-registro tras cerrar §45.
- **Brecha 1 — validar umbrales de salida (walk-forward, position_stop por
  régimen + multiplicadores ATR de partial-TP/trailing/técnica)**: hallazgo
  de código real (mismo que la asimetría sizing-vs-trigger ya pasada a
  Kilo), pero §45 (recién cerrado NO_CUMPLE) ya testeó una variante cercana
  de esta misma zona — un trial nuevo acá necesita diseño tan cuidadoso
  como el de §45, no es territorio limpio. NO autorizada todavía — queda
  documentada como candidata, a revisar después de Brecha 2.
- **Brecha 3 — acumulación OOS para promover el baseline**: coincide con lo
  ya identificado en §4 de este documento. Condicional al tiempo (el
  updater acumula meses), no accionable hoy.
- **Brecha 4 — M2 (conformal engine) sobre un score distinto a win_prob**
  (ej. FinBERT o g3_score): plausible pero con MENOS verificación que la
  Brecha 2 — necesita escrutinio adicional (¿es genuinamente distinto de lo
  ya refutado, o el mismo mecanismo con otra etiqueta?) antes de proponerse
  en firme. NO autorizada, queda anotada para revisión futura.
- **Brecha 5 — cierre de superficie API (auth mínima en endpoints de
  escritura, SECRET_KEY que falla sin setear fuera de development)**: NO es
  investigación, no requiere gate de pre-registro. **Asignada a Cline**
  (ver abajo) — accionable ya.

## 6.2 Asignaciones activas (2026-08-25)

- **Kilo**: tras cerrar/mergear §45, próximo pre-registro es **Brecha 2 (M3
  standalone gate)**. Pre-registrar ANTES de correr, leer umbral real del
  ledger en runtime, mismo rigor que §44/§45.
- **Cline**: **Brecha 5 (auth API)** — endpoints de escritura con auth
  mínima, SECRET_KEY que falla si no está seteada fuera de development.
  Verificar primero contra AUDITORIA_TECNICA.md cuál es el estado real
  antes de tocar nada (no asumir).
- **OpenCode**: sigue con §45 (merge en curso) y §43 (supervisión, PID
  96215 corriendo lento por carga de la Mac).

## 7. Verificación — la regla de oro de todo el proyecto

Nunca aceptar "listo" de un agente sin comprobarlo contra el artefacto real:
leer el archivo, correr el test, verificar el commit. Esto NO cambia con el
handover — es la disciplina central que sostiene la credibilidad de todo
Fortress Core.
