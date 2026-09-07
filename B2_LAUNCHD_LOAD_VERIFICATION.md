# B2 — Colector IV Surface: Carga en launchd y Verificación

**Generado**: 2026-09-07  
**Ticket**: B2 (PLAN_REMEDIO_BRECHAS_20260903) — auditoría encontró que el plist NO estaba cargado en launchd; el colector nunca corría por cron.

---

## 1. Template del plist (para instalar en cualquier máquina)

Archivo: `scripts/com.fortresscore.ivcollector.plist.template`

Placeholders a sustituir:
| Placeholder | Valor real (ejemplo máquina Boris) |
|-------------|-------------------------------------|
| `__VENV_PYTHON__` | `/Users/boris/Desktop/fortress_core/backend/.venv/bin/python` |
| `__REPO_ROOT__` | `/Users/boris/Desktop/fortress_core` |

---

## 2. Comando EXACTO de carga (ejecutar en producción)

```bash
# 1. Generar plist concreto desde template
REPO_ROOT="/Users/boris/Desktop/fortress_core"
VENV_PYTHON="${REPO_ROOT}/backend/.venv/bin/python"

sed \
  -e "s|__VENV_PYTHON__|${VENV_PYTHON}|g" \
  -e "s|__REPO_ROOT__|${REPO_ROOT}|g" \
  scripts/com.fortresscore.ivcollector.plist.template \
  > /tmp/com.fortresscore.ivcollector.plist

# 2. Copiar a ~/Library/LaunchAgents (requerido para launchctl user)
cp /tmp/com.fortresscore.ivcollector.plist ~/Library/LaunchAgents/

# 3. Cargar en launchd
launchctl load ~/Library/LaunchAgents/com.fortresscore.ivcollector.plist

# 4. Verificar que está cargado
launchctl list | grep ivcollector
# Debe mostrar: PID  (o - si no ha corrido aún)  com.fortresscore.ivcollector
```

**Nota**: El load en producción lo ejecuta Kilo en el repo real (`/Users/boris/Desktop/fortress_core`). Este worktree (`test-opencode-orca`) NO debe tocar launchd de producción.

---

## 3. Verificación POST-22:35 (la noche de la carga)

Después de las 22:35 (hora local, misma zona que el Mac que corre launchd):

### 3.1 Verificar log
```bash
tail -f /Users/boris/Desktop/fortress_core/scripts/iv_collector.log
# Debe mostrar líneas como:
# [iv] snapshot 2026-09-07 -> iv_snapshot_20260907.parquet: 720 filas, 30 OK / 0 FAIL, 2.3 MB
```

### 3.2 Verificar parquet generado
```bash
REPO_ROOT="/Users/boris/Desktop/fortress_core"
DAY=$(date +%Y%m%d)
PARQUET="${REPO_ROOT}/backend/data/cache/iv_surface/iv_snapshot_${DAY}.parquet"

if [[ -f "${PARQUET}" ]]; then
    echo "✅ Parquet existe: ${PARQUET}"
    python3 -c "
import pandas as pd
df = pd.read_parquet('${PARQUET}')
print(f'Filas: {len(df)}')
print(f'Símbolos únicos: {df[\"symbol\"].nunique()}')
print(f'Columnas: {list(df.columns)}')
print(df.head(3))
"
else
    echo "❌ NO se generó parquet para hoy"
fi
```

### 3.3 Verificar símbolos esperados (30 de B1/B2)
```bash
python3 -c "
import pandas as pd
df = pd.read_parquet('${PARQUET}')
expected = 30
actual = df['symbol'].nunique()
if actual == expected:
    print(f'✅ {actual} símbolos (esperado {expected})')
else:
    print(f'⚠️  {actual} símbolos (esperado {expected})')
    print('Símbolos:', sorted(df['symbol'].unique()))
"
```

### 3.4 Verificar campos del snapshot
```bash
python3 -c "
import pandas as pd
df = pd.read_parquet('${PARQUET}')
required = {'symbol','option_type','expiry','dte','strike','last','bid','ask',
            'implied_volatility','open_interest','volume','in_the_money','spot','snapshot_date'}
missing = required - set(df.columns)
if not missing:
    print('✅ Todas las columnas requeridas presentes')
else:
    print(f'❌ Faltan columnas: {missing}')
"
```

---

## 4. Troubleshooting común

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| launchctl list muestra `-` (no PID) y no hay log | Plist no cargado o error en ProgramArguments | `launchctl unload ... && launchctl load ...` y revisar log |
| Log muestra "ConfigurationError: Faltan credenciales" | Variables de entorno ALPACA_* no disponibles en launchd | Añadir `EnvironmentVariables` al plist o cargar credenciales en `~/.launchd.conf` |
| Parquet tiene < 30 símbolos | Algunos símbolos fallaron "sin spot" | Verificar que cache diario tiene los 30 símbolos antes de 22:35 |
| Error "ModuleNotFoundError: scripts.collect_intraday_1min" | B1 no instalado en ese repo | IV_SYMBOLS cae a fallback (opportunities_universe.SYMBOLS, 50 símbolos) — warning en log |

---

## 5. Desinstalar (si hace falta)

```bash
launchctl unload ~/Library/LaunchAgents/com.fortresscore.ivcollector.plist
rm ~/Library/LaunchAgents/com.fortresscore.ivcollector.plist
```

---

## 6. Referencias

- PLAN_REMEDIO_BRECHAS_20260903.md → B2 (línea ~80): "launchd 22:35 diario (scripts/com.fortresscore.ivcollector.plist)"
- backend/scripts/collect_iv_surface.py — colector principal
- backend/tests/test_collect_iv_surface.py — tests (13 passed, 2 skipped)