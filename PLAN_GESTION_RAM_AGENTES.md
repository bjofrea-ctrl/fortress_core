# Plan — gestión de RAM: cerrar agentes ociosos, abrirlos a demanda

Documento para compartir con las otras sesiones de Claude Code (medai,
empresa-hibrida u otro proyecto que use Orca) — mismo problema, misma solución,
aplicable sin cambios al mecanismo, solo ajustando nombres de worktree/agente.

## El problema

Cada proyecto corre 3 agentes (Kilo, Cline, OpenCode) como sesiones de terminal
persistentes vía Orca — aunque un agente no tenga nada que hacer, su proceso
sigue vivo consumiendo RAM (70-800MB según el agente y cuánto contexto
acumuló). Con 3 proyectos corriendo en paralelo (fortress_core, medai,
empresa-hibrida), eso son ~9 sesiones de agente + 3 coordinadores Claude Code +
overhead de Orca, todas compitiendo por los mismos 16GB de RAM del Mac —
verificado hoy: solo 1.4GB libres de 16GB, con actividad de swap pesada.

Nadie está usando activamente los 3 agentes de los 3 proyectos al mismo
tiempo — en la práctica hay uno o dos proyectos con foco real en un momento
dado, y el resto de los agentes están ociosos "por las dudas", sin tarea
asignada, ocupando memoria sin producir nada.

## La solución

**No mantener agentes vivos cuando no tienen tarea pendiente.** El
coordinador (Claude Code de cada proyecto) cierra la sesión de terminal de un
agente en cuanto confirma que terminó su trabajo y no hay nada asignado, y la
vuelve a abrir recién cuando hay una tarea nueva para darle — con el contexto
necesario incluido en el mensaje inicial, ya que de todas formas el
coordinador ya escribe ese contexto completo cada vez que asigna una tarea.

### Comandos de Orca que lo permiten

```bash
# Cerrar limpiamente una sesión de agente (libera su RAM)
orca terminal close --terminal <handle>

# Abrir una sesión nueva cuando haga falta, corriendo el agente que sea
orca terminal create --worktree <selector> --command "kilo"      # o "cline", "opencode"

# Ver qué terminales siguen vivas por worktree, antes de decidir
orca terminal list --worktree <selector> --json
```

### Política de cuándo cerrar

Cerrar un agente cuando **las tres** condiciones se cumplen:
1. El coordinador confirmó que la tarea asignada está terminada (commit hecho,
   `.pending-merge.md` revisado y resuelto, o el agente reportó explícitamente
   que no tiene nada pendiente).
2. No hay ninguna tarea nueva ya decidida para asignarle en el corto plazo.
3. El agente lleva un rato genuinamente ocioso (no está a mitad de generar
   una respuesta ni esperando una confirmación puntual del coordinador).

No cerrar un agente que está:
- Corriendo un proceso de fondo largo (ej. un trial de investigación, un
  backtest) — cerrar la TERMINAL no mata el proceso si quedó como hijo de
  `launchd`/detached, pero corta la visibilidad y la posibilidad de que el
  agente reporte el resultado cuando termine. Mejor esperar a que cierre.
- Con una pregunta sin responder o un `.pending-merge.md` sin resolver.

### Costo real de esta política (ser honesto, no vender esto como gratis)

- **Se pierde el contexto de conversación previo del agente al cerrarlo** —
  al reabrir, arranca una sesión nueva, sin memoria de lo que venía haciendo.
  El coordinador tiene que re-explicar la tarea completa en el mensaje
  inicial (cosa que igual ya hace siempre que asigna trabajo nuevo, así que
  el costo incremental es bajo, no cero).
- Reabrir toma unos segundos (arrancar el CLI + que cargue) — no es
  instantáneo, pero tampoco es lento.
- Vale la pena solo si el agente iba a estar ocioso por un rato real (minutos
  u horas), no para pausas de segundos entre mensajes.

## Qué NO cambia

- El resto del protocolo de coordinación (gate de merge, `.pending-merge.md`,
  verificación antes de aceptar cualquier resultado de un agente) sigue
  exactamente igual — esto es solo gestión de ciclo de vida de las
  terminales, no cambia cómo se revisa o aprueba el trabajo.
- No hace falta tocar la app de escritorio de Orca ni nada visible para el
  usuario — todo esto se maneja por CLI, en el mismo canal que ya se usa para
  mandar tareas a los agentes.

## Resultado esperado

Con los 3 proyectos aplicando esto, la RAM ocupada por agentes en un momento
dado pasa de "9 sesiones siempre vivas" a "solo las 2-3 sesiones que
realmente tienen trabajo en curso ahora mismo" — el resto queda liberado
hasta que haga falta.

---

## Hallazgos de las tres sesiones (2026-08-26) — para revisión de Boris, NADA aplicado todavía

Las tres coordinadoras (fortress_core, medai, empresa-hibrida) analizaron su
propio estado sin ejecutar cambios adicionales, salvo las excepciones que se
marcan explícitamente abajo como ya hechas (todas de bajo riesgo, verificadas).

### fortress_core

- Cerré las terminales de Kilo y Cline al confirmar que no tenían tarea
  pendiente (H3.1 cerrado y mergeado, reporte mensual cerrado). Resultado
  medido: liberó ~680MB de esos dos procesos, pero la RAM total del sistema
  no bajó proporcionalmente porque otras sesiones activas crecieron en
  paralelo por su propio trabajo — la medida funciona, pero el techo real es
  cuántas sesiones están genuinamente activas al mismo tiempo, no las
  ociosas.
- Las 3 sesiones de Claude Code coordinadoras (una por proyecto) son las que
  más pesan individualmente (700-970MB cada una) — todas llevan ~3 días
  corriendo sin reiniciar. Cerrarlas es una decisión más pesada que cerrar un
  agente (se pierde el hilo completo de coordinación, no solo el de una
  tarea puntual) — no se tocó ninguna, queda para que decida Boris.

### medai

1. **Terminales fantasma sin dueño claro**: encontró 2 terminales vivas que
   no formaban parte de su rotación activa de 3 agentes con nombre (una
   segunda instancia de OpenCode duplicada en el mismo worktree, una
   terminal vacía en un worktree sin uso) — invisibles porque el chequeo
   asume "solo 3 agentes con nombre" por proyecto. **Ya cerradas** (cruzó
   con el pedido de no aplicar nada más, pero eran verificablemente basura —
   una muerta, otra duplicada sin uso). Propone que el plan incluya un
   `orca terminal list` completo por proyecto antes de asumir que solo hay 3
   terminales — puede haber residuales de sesiones anteriores.
2. **Colisiones de trabajo duplicado por reasignación silenciosa**: pasó 2
   veces hoy — reasigna una tarea de un agente sin crédito a otro, y cuando
   el original recupera sesión retoma la tarea vieja por su cuenta (su
   contexto todavía dice "pendiente", no sabe que ya se resolvió). Propone
   que la política de reasignación incluya avisar DIRECTO al agente original
   apenas se detecta que volvió a estar operativo, antes de que tenga
   oportunidad de actuar solo — no alcanza con dejarlo en el log de
   coordinación.
3. **Fricción de rotación de modelo/cuenta**: funciona pero consume varias
   vueltas de verificación manual cada vez. Propone documentar los comandos
   exactos que expone cada CLI (Kilo/Cline/OpenCode pueden diferir) para no
   redescubrirlo cada vez.
4. **Fricción mecánica menor**: los mensajes por `orca terminal send` a
   veces quedan sin enviarse en el input, necesita un segundo `--enter`
   vacío — no consume tokens de agente, pero sí vueltas extra del
   coordinador (mismo patrón que vi yo en fortress_core con Cline hoy).
5. **Lo que NO recomienda tocar**: la calidad del contexto inicial en cada
   dispatch (citas al log + alcance acotado) — según su experiencia de hoy,
   eso es lo que hace que las auditorías pasen limpias a la primera, y es lo
   que hace viable cerrar/reabrir sin perder calidad. No es solo
   compensación del cierre de RAM, es parte central del mecanismo.

### empresa-hibrida

- Estado actual: solo OpenCode sigue con terminal viva, legítimamente
  (vigila un batch real de re-medición en background, ~102 chunks en
  curso). Cline y Kilo ya estaban cerradas — las cerró Boris directamente
  tras confirmar que terminaron su trabajo (2 tickets mergeados hoy).
- **Ya cerrado** (antes de la corrección, sin relación con "aplicar el
  plan"): un monitor de fondo propio, roto, que seguía vigilando handles de
  terminal de Cline/Kilo que ya no existían — loop de 60s corriendo en vano
  desde que esas terminales rotaron, cero impacto en trabajo real.
- **Propuesta 1 — no incluir el hub daemon de Cline en la política de
  cerrar/reabrir**: `--cline-hub-daemon` (puerto 25463) lleva 2 días 7h
  corriendo continuo — parece ser infraestructura compartida (multiplexor de
  sesiones), no un worker por tarea, y probablemente deba persistir aunque
  las terminales individuales de Cline se cierren y reabran. Sí encontró un
  cliente `.cline` conectado a ese hub con la misma antigüedad que no
  corresponde a ninguna terminal viva ahora — candidato a huérfano, lo deja
  para que decida Boris, no lo tocó.
- **Propuesta 2 — cerrar un loop redundante**: un loop de shell corriendo
  ~6h vigilando el catálogo de NVIDIA NIM cada 30min quedó redundante desde
  que se mergeó `scripts/check_model_health.py` (hace lo mismo, testeado,
  on-demand). Recomienda cerrarlo cuando Boris confirme.
- **Eficiencia de tokens/créditos — hallazgos**:
  - 2 falsos positivos distintos en el security scan de `staff/bin/gate.sh`
    (regex sin boundary de palabra: matcheaba el nombre de variable
    `OPENROUTER_API_KEY` y también "eval(" dentro de "retrieval(") — cada
    uno costó un ciclo completo de verificación manual. Si `gate.sh` es
    compartido entre los tres proyectos, vale la pena arreglar el regex una
    sola vez.
  - Fricción de UI de agente (cola de mensajes sin procesar en Cline/Kilo)
    que necesitó varios intentos a ciegas hasta destrabar — mismo patrón de
    fricción mecánica que reportó medai independientemente.
  - Tramos de espera activa por rate-limits de proveedores generan turnos
    cortos de "sin cambios" — el propio mecanismo de loop ya los colapsa en
    la vista de Boris, impacto real bajo pero lo marca igual.

### Patrón que aparece en las tres sesiones, independientemente

La fricción mecánica de `orca terminal send` (mensajes que no se procesan a
la primera, necesitan reintento o un segundo Enter) la reportaron las tres
sesiones por separado, sin coordinarse entre sí — es la señal más fuerte de
que vale la pena investigar/documentar una solución única en vez de que cada
proyecto la resuelva a mano cada vez que aparece.

---

## Memoria externa (gbrain, Obsidian, OpenViking, Cognee, TencentDB Agent
## Memory, OpenKnowledge) — ¿sirve para el problema de RAM? (2026-08-26)

Boris preguntó si alguna herramienta de "memoria acumulada" externa serviría
para aliviar la presión de RAM. Se investigó en tres frentes independientes
(fortress_core vía sub-agente, medai, empresa-hibrida) — las tres convergen
en la misma conclusión, con caveat: el WebSearch estuvo caído para las tres
sesiones ese turno (falla de plataforma, no puntual); solo el sub-agente de
fortress_core logró búsquedas reales y verificó las herramientas con fuentes.

### Qué son realmente (verificado)

| Herramienta | ¿Real? | Qué es |
|---|---|---|
| **gbrain** | Sí | `github.com/garrytan/gbrain` — "cerebro" de conocimiento personal/equipo, grafo de páginas con síntesis, expuesto a agentes vía capa de retrieval tipo MCP. Servicio externo. |
| **Obsidian** | Sí (no es memoria de agente por sí sola) | App de notas markdown sin lógica de retrieval propia — solo funciona como "memoria de agente" si se le suma un MCP server aparte que lea/escriba notas; en ese caso el trabajo lo hace el MCP, no Obsidian. |
| **OpenViking** | Sí | `github.com/volcengine/OpenViking` (ByteDance/Volcengine) — "base de datos de contexto" autohospedada, filesystem virtual `viking://` con carga por niveles. Servicio externo. |
| **Cognee** | Sí | `cognee.ai` — plataforma de memoria de agentes open-source, combina grafo+vectores+relacional, autohospedada o cloud. Servicio externo. |
| **TencentDB Agent Memory** | Sí | `github.com/TencentCloud/TencentDB-Agent-Memory` — convierte conversaciones/código en memoria reusable (Chat Memory, Skill, LLM-Wiki, Code-Graph), afirma ~61% de reducción de TOKENS en sesiones largas (dato real y citado, pero es sobre tokens/costo, no sobre RAM). Servicio externo.
| **OpenKnowledge** | No hay match creíble | El repo más cercano tiene 48 estrellas, proyecto personal chico. No es un producto establecido — probablemente no es a lo que se refería. |

### El veredicto (triangulado, tres fuentes independientes coinciden)

**Ninguna de estas resuelve el problema de RAM — es la capa equivocada del
stack.** El argumento, consistente entre las tres investigaciones:

- La RAM de una sesión Claude Code de larga duración viene de que el
  **proceso** (runtime Node del CLI) retiene en memoria el historial
  completo de conversación/salidas de herramientas mientras está vivo — eso
  no cambia según dónde viva el conocimiento de largo plazo.
- Las 4 herramientas reales (gbrain, OpenViking, Cognee, TencentDB Agent
  Memory) son, arquitectónicamente, almacenes externos a los que el agente
  consulta por tool call — **exactamente el mismo patrón que ya usa Engram**
  (memoria persistente ya instalada y en uso). No corren "adentro" del
  proceso de Claude Code para achicarlo.
- Si alguna corriera como servidor MCP local, **sumaría** un proceso más
  (más RAM), no restaría.
- El único lever real para bajar RAM de una sesión sigue siendo el mismo
  que ya está documentado arriba: cerrar terminales ociosas + compactar o
  reiniciar la sesión coordinadora cuando haga falta. Una memoria externa
  puede hacer que reiniciar sea MÁS CÓMODO (menos que re-explicar al volver,
  porque el estado relevante se recarga del almacén) — pero no reduce la RAM
  de un proceso que sigue corriendo.

**Nota aparte, no sobre RAM**: el dato de TencentDB Agent Memory (~61% menos
tokens en sesiones largas) es real y podría ser interesante para *costo/
eficiencia de tokens* — un eje distinto al de RAM, que no se evaluó acá en
profundidad. Si a Boris le interesa esa arista, es una investigación aparte.

**Recomendación de las tres sesiones**: no adoptar ninguna de estas
herramientas para el problema de RAM — Engram ya cubre lo que aportarían. El
fix sigue siendo cerrar-terminal-ociosa/reabrir-a-demanda (ya documentado
arriba) más compactar/reiniciar la sesión coordinadora cuando el proceso
crezca demasiado.

### Para que decida Boris (nada de esto se ejecutó)

1. ¿Cerrar el cliente `.cline` huérfano del hub daemon en empresa-hibrida?
2. ¿Cerrar el loop redundante de vigilancia de NIM en empresa-hibrida (ya
   reemplazado por `check_model_health.py`)?
3. ¿Arreglar el regex de `gate.sh` (falsos positivos) si es compartido entre
   proyectos?
4. ¿Adoptar la política de "avisar directo al agente al recuperar sesión"
   antes de que reasigne nada, para evitar las colisiones de trabajo
   duplicado que vio medai?
5. ¿Alguna de las 3 sesiones coordinadoras de Claude Code (700-970MB cada
   una, ~3 días corriendo) se puede reiniciar sin perder algo importante?
