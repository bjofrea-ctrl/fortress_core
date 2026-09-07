# M5 — Verificación HOY (antes de 16:00 ET)

**Objetivo**: Confirmar que `pmset -g assertions` muestra `PreventUserIdleSystemSleep` activo gracias a nuestro `caffeinate -i -s`, para que Kilo pueda cargar el plist HOY antes de las 16:00 ET.

---

## 1. Verificación rápida (ejecutar AHORA en el Mac de producción)

```bash
# 1. Verificar si YA hay un caffeinate -i -s nuestro corriendo
ps aux | grep -E 'caffeinate.*-i.*-s' | grep -v grep
# Si sale algo -> YA está activo. Si no sale nada -> NO está activo aún.

# 2. Ver assertions de power management (LO QUE KILO BUSCA)
pmset -g assertions | grep -A2 -B2 PreventUserIdleSystemSleep
```

### Salida ESPERADA (si caffeinate está activo):

```
Assertion status system-wide:
   BackgroundTask                 0
   ApplePushServiceTask           0
   UserIsActive                   1
   PreventUserIdleDisplaySleep    0
   PreventSystemSleep             0
   PreventUserIdleSystemSleep     1   <-- ESTE DEBE ESTAR EN 1
   ExternalMedia                  0
   PreventUserIdleDisplaySleep    0
   InternalPreventSleep           1
   NetworkClientActive            0
Listed by owning process:
   pid 12345(caffeinate): [0x0000000c00000005] 00:00:00 PreventUserIdleSystemSleep named: "caffeinate"
```

**La línea clave**: `PreventUserIdleSystemSleep     1` y abajo `pid XXXXX(caffeinate): ... PreventUserIdleSystemSleep named: "caffeinate"`

---

## 2. Si NO está activo — cargar AHORA (Kilo ejecuta en producción)

```bash
REPO_ROOT="/Users/boris/Desktop/fortress_core"

# 1. Generar plist concreto desde template
sed -e "s|__REPO_ROOT__|${REPO_ROOT}|g" \
  scripts/com.fortresscore.keepawake.plist.template \
  > /tmp/com.fortresscore.keepawake.plist

# 2. Copiar a ~/Library/LaunchAgents
cp /tmp/com.fortresscore.keepawake.plist ~/Library/LaunchAgents/

# 3. Cargar en launchd (lanza el script que a su vez lanza caffeinate)
launchctl load ~/Library/LaunchAgents/com.fortresscore.keepawake.plist

# 4. Verificar carga
launchctl list | grep keepawake
# Debe mostrar PID (o - si acaba de arrancar)  com.fortresscore.keepawake

# 5. Verificar assertion de nuevo (esperar ~5s)
sleep 5
pmset -g assertions | grep -A2 -B2 PreventUserIdleSystemSleep
# Debe mostrar PreventUserIdleSystemSleep = 1 con pid de caffeinate
```

---

## 3. Verificación de que el script funciona (test manual)

```bash
# Verificar detección de horario (debe salir "DENTRO" si son 09:25–16:05 ET Lun-Vie)
/Users/boris/Desktop/fortress_core/scripts/keep_awake_market_hours.sh --check
# Exit code 0 = DENTRO, 1 = FUERA
```

---

## 4. Troubleshooting

| Síntoma | Acción |
|---------|--------|
| `pmset` muestra `PreventUserIdleSystemSleep 0` | Verificar `launchctl list | grep keepawake` → si no está, `launchctl load`; si está, revisar log `~/Desktop/fortress_core/scripts/keep_awake.log` |
| Log muestra "FUERA de horario" pero es horario de mercado | Verificar zona horaria: `date` y `TZ=America/New_York date` — el Mac debe estar en zona horaria correcta |
| `caffeinate` no aparece en `ps aux` | Verificar que el script se ejecuta (launchd KeepAlive=true) y que no hay otro caffeinate sin -s |
| Market hours check falla en weekend | Correcto: script NO lanza caffeinate en weekend |

---

## 5. Referencias

- Script: `scripts/keep_awake_market_hours.sh` (caffeinate -i -s, 09:25–16:05 ET, weekdays)
- Plist template: `scripts/com.fortresscore.keepawake.plist.template` (placeholder `__REPO_ROOT__`)
- Log: `__REPO_ROOT__/scripts/keep_awake.log`
- PID file: `/tmp/keep_awake_market_hours.pid` (para limpieza propia)