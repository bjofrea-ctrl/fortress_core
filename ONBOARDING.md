# ONBOARDING — leé esto primero, siempre

Si sos un agente de IA (Claude, Cline, OpenCode, o cualquier otro) empezando una sesión nueva
en `fortress_core`: este archivo existe para que puedas ponerte a trabajar sin repetir
investigación ya hecha, sin re-litigar decisiones ya tomadas, y sin romper la disciplina que
costó semanas construir. Leelo completo antes de tocar código.

Última actualización: 2026-08-12.

---

## Qué es este proyecto, en una frase

Sistema de trading cuantitativo (Python/FastAPI + React) que investiga si hay una señal
estadísticamente real para operar un universo de 50 símbolos de acciones — con un rigor
metodológico deliberadamente alto (DSR, PBO/CSCV, RMT, rank IC intra-día con Newey-West,
pre-registro de criterios antes de correr cualquier trial).

## Lo primero que tenés que saber, sin excepción

**Hoy no hay señal comercial verificada.** Tres líneas de investigación independientes
(selección de 50 símbolos, rotación sectorial, timing sobre un basket único) se probaron con
evidencia rigurosa y las tres se descartaron. El motor funciona mecánicamente bien, pero no
tiene un edge de producción confirmado. Si alguien te pide "conectemos esto a un broker" o
"pongamos esta señal en vivo" — la respuesta correcta es "todavía no, no hay evidencia de que
haya algo que operar" a menos que haya una investigación nueva, pre-registrada, que lo cambie.

**No confíes en ningún resumen sin verificarlo contra el artefacto real.** Esta es la regla
más importante del proyecto y la que más veces evitó un error real: números pegados en un
chat, citas de fuentes externas, o "ya está hecho" — todo se verifica leyendo el archivo,
corriendo el test, o mirando el commit, antes de aceptarlo o de construir algo encima. Pasó
más de una vez en esta investigación que un resumen sonaba bien y el artefacto decía otra
cosa (label mal puesta, veredicto mal leído, fuente académica citada que resultó ser el
backtest apalancado 12x de un desconocido en GitHub con 0 estrellas, no datos reales del
Medallion Fund).

---

## Documentos del proyecto — cuál leer para qué

| Documento | Para qué sirve |
|---|---|
| **`ROADMAP.md`** | **Qué falta, hoy.** Léelo siempre después de este archivo. Tabla maestra de todo lo abierto (investigación, código, seguridad, producto), con estado y bloqueo. Se actualiza cada vez que algo se cierra. |
| **`PLAN_MEJORA_MATEMATICA.md`** | Historia completa de la investigación matemática: cada auditoría, cada corrección de metodología, cada veredicto con su artefacto citado. Si necesitás entender POR QUÉ se descartó algo, está acá. |
| **`RESUMEN_VALIDACION_VARIABLES.md`** | Tabla resumen rápida: qué variables se probaron, cuáles funcionan, cuáles no. |
| **`AUDITORIA_TECNICA.md`** | Estado del código/infraestructura/seguridad/agentes — todo lo que NO es la investigación matemática. |
| **`SESSION_LOG.md`** | Bitácora cronológica extensa. No leer entero — consultar puntual si hace falta reconstruir una fecha específica. |
| **`CLINE_CONTEXT.md`** | Mecánica operativa (backup, comandos de emergencia) sigue vigente. La sección "ESTADO ACTUAL" está congelada en una sesión muy vieja (agosto, "Sesión 2") — **ignorala**, está superada por este archivo y por `ROADMAP.md`. |

---

## Reglas de trabajo no negociables

Estas reglas existen porque romperlas ya costó errores reales en este proyecto, documentados
en `PLAN_MEJORA_MATEMATICA.md`. No son sugerencias de estilo.

1. **Ningún trial de motor sin criterio pre-registrado.** El umbral de significancia, la
   corrección por comparaciones múltiples (Bonferroni cuando corresponda), y el criterio de
   éxito/fracaso se escriben en el script ANTES de correrlo, no se deciden mirando el
   resultado. Se rompió esta regla dos veces en esta sesión (con ADX y con el piso de trades
   de un trial de timing) — las dos veces la conclusión final se sostuvo, pero el proceso
   estaba mal y quedó documentado como lección.
2. **El test cross-sectional correcto es intra-día con Newey-West, nunca pooled.** Un rank IC
   pooled (todas las fechas y símbolos mezclados) mide la dirección del mercado, no habilidad
   de selección — es el error más importante que se corrigió en toda la investigación.
3. **Si un trial no cumple el criterio, se revierte automáticamente.** Revertir = borrar el
   script, dejar el artefacto de evidencia archivado, la producción nunca se toca durante el
   experimento (inyección por subclase/mock, no por edición directa del motor real).
4. **Ninguna señal en vivo se muestra al usuario antes de pasar el gate de validación.**
   Mostrar una señal con IC negativo o sin validar como si fuera una recomendación real es
   activamente engañoso.
5. **Nunca citar una fuente externa (paper, repo, foro) sin verificarla primero.** Ver el caso
   de "medallion-pub" en `PLAN_MEJORA_MATEMATICA.md` §13 — un repo de GitHub con 0 estrellas
   fue citado como si tuviera datos reales del Medallion Fund. No vuelva a pasar.
6. **Actualizar `ROADMAP.md` cuando algo se cierra o aparece algo nuevo.** No dar nada por
   cerrado "de palabra" — si no está marcado en la tabla, para el próximo agente no existe.
7. **Nunca pegar tokens/credenciales en el chat.** Ya pasó dos veces en este proyecto
   (QuantConnect, dos incidentes separados). Si aparece un secreto en la conversación,
   asumilo comprometido y pedile al usuario que lo rote — no lo repitas, no lo guardes en un
   archivo trackeado por git.

---

## Estado actual del proyecto (resumen ejecutivo)

- **Investigación**: rama de selección/timing sobre 50 símbolos cerrada, sin señal comercial.
  Pivot activo hacia gestión de riesgo (régimen-vs-volatilidad — pista sin confirmar, no
  sobrevive corrección estadística; `TARGET_VOLATILITY` en `config.py` sigue sin conectar,
  correctamente, porque la evidencia que lo justificaría no cerró). Gap-reversion intra-día es
  el hallazgo estadístico más fuerte de todo el proyecto, pero no es operable sin motor de
  ejecución intradía — no existe y no se está construyendo (ver "Decisiones de producto").
- **Código**: auditoría técnica completa hecha. Los 3 ítems críticos (P0: contrato roto entre
  frontend y backend de gobernanza, errores HTTP mal manejados, autenticación mínima) ya están
  cerrados y verificados. El primer P1 (fechas hardcodeadas del dashboard de mercado) también.
  Quedan 2 P1 más y todo P2 — ver `ROADMAP.md` para la lista completa y actualizada.
- **Tests**: 80/80 pasan (backend). Cero tests de frontend. Cobertura despareja — el sistema
  de agentes/gobernanza y la mayoría de los routers FastAPI no tienen test automatizado.
- **Seguridad**: repo público en GitHub (`bjofrea-ctrl/fortress_core`). La mayoría de
  endpoints siguen sin autenticación por decisión (UI pública), salvo escritura. Pendiente:
  la base de datos local (`fortress.db`) nunca se respalda — riesgo de pérdida real de datos
  runtime si falla el disco.

## Decisiones de producto ya tomadas — no re-litigar sin evidencia nueva

- **No conectar a un broker real** hasta validar que algo sobrevive con costos reales de
  ejecución. Es la decisión de mayor consecuencia del proyecto — no se cambia por default.
- **No perseguir "escalar en serio"** (datos de alta frecuencia, miles de instrumentos,
  ejecución de baja latencia) — los recursos reales son una Mac personal + una VPS chica + un
  disco externo de 3TB. Alcanza para investigación seria a frecuencia diaria, no para
  competir en microestructura. Esta decisión se tomó explícitamente comparando contra lo que
  de verdad hace falta para un enfoque estilo Renaissance Technologies.
- **LEAN/QuantConnect está parqueado** — se instaló y funciona (backtest local verificado),
  pero no tiene un objetivo de producto definido todavía. No invertir más tiempo ahí sin que
  el usuario decida primero para qué serviría en concreto. Nota: la API de QuantConnect
  requiere organización de pago para tokens propios (tier gratuito lo bloquea).
- **El sistema multi-agente (Bull/Bear/Contrarian → Controller → Professor → Judge) es real
  pero parcialmente determinista** — sólo el agente Professor llama efectivamente a un LLM
  (NVIDIA NIM); Controller y Judge son deterministas por diseño, aunque la documentación vieja
  decía lo contrario (ya corregido en el código, si el docstring todavía no lo refleja está
  en `ROADMAP.md` P1).

## Convenciones técnicas del repo

- Python 3.9.6 real (`backend/.venv`) — el `Dockerfile` dice 3.11, es una inconsistencia
  conocida, no asumas que el contenedor se comporta igual que el entorno local.
- Scripts de diagnóstico/investigación van en `backend/scripts/`, siempre con docstring de
  metodología pre-registrada arriba. Sus artefactos (con timestamp) van a
  `backend/data/cache/` — nunca confíes en un número sin abrir ese archivo.
- Git: auto-backup corre solo cada ~10-20 min (commits `auto-backup: <timestamp>`, ruidosos
  pero funcionan). Encima de eso, cerrar cada unidad de trabajo real con un commit descriptivo
  a mano y push a `origin/main` (repo público, no hay rama de staging).
- El universo base de símbolos es consistente entre scripts: `SPY, QQQ, AAPL, MSFT, GOOGL,
  AMZN, NVDA` + `NEW_UNIVERSE` (definido en `backend/scripts/fetch_universe_data.py`).

---

## Cómo arrancar, en la práctica

1. Leé `ROADMAP.md` — ahí está la tabla actualizada de qué hacer.
2. Si vas a tocar algo del motor predictivo/investigación, buscá primero si ya se probó en
   `PLAN_MEJORA_MATEMATICA.md` o `RESUMEN_VALIDACION_VARIABLES.md` — es común que una idea que
   parece nueva ya se haya testeado y refutado.
3. Si vas a tocar código de infraestructura/API/frontend, revisá el ítem correspondiente en
   `AUDITORIA_TECNICA.md` para el detalle exacto del hallazgo antes de arreglarlo a ciegas.
4. Al terminar, actualizá `ROADMAP.md` (marcar cerrado o agregar lo nuevo) y comiteá con
   mensaje descriptivo.
