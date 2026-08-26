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
