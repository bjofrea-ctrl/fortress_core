#!/bin/bash
# Latido genérico de frescura de datos — vigila TODOS los colectores.
# Mismo espíritu que check_disk_health.sh: NUNCA repara, solo avisa CLARO.
# - Para cada colector: mtime del artefacto más reciente → edad horas → compara con threshold.
# - Log con prefijo [ERROR]/[WARN]/[OK], timestamp, colector, edad, threshold, mtime, path.
# - Exit 0 siempre (no rompe launchd); ERROR visible en log.
# - Intraday respeta mercado cerrado (09:30-16:00 ET, lun-vie) → SKIP sin ERROR.
set -euo pipefail

# --- Repo y log (paridad con check_disk_health.sh + data_updater.sh) ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# REPO por env (override para tests/worktree) o inferido desde script dir
REPO="${FORTRESS_REPO:-${REPO:-}}"
if [[ -z "$REPO" ]]; then
  # scripts/ está en REPO/scripts → REPO = parent de scripts/
  REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/data_freshness.log"
mkdir -p "$LOG_DIR"
# Compat: si logs/ no existe, fallback a $REPO/scripts/data_freshness.log (no usado en prod)
# Thresholds (horas) — ver DISENO_LATIDO_DATOS.md §2
THRESHOLD_OHLCV_H=30        # 24h +6h holgura
THRESHOLD_OHLCV_MON_H=76    # lunes: 72h finde +4h
THRESHOLD_EARNINGS_H=30
THRESHOLD_EARNINGS_MON_H=76
THRESHOLD_INTRADAY_H=1      # 30min cadencia +30min tolerancia

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# --- Resuelve threshold OHLCV/earnings según día de semana (lunes=1) ---
# Si hoy es lunes, usar threshold extendido para cubrir gap viernes→lunes.
dow="$(date +%u)"  # 1=lunes ... 7=domingo
if [[ "$dow" == "1" ]]; then
  TH_OHLCV="$THRESHOLD_OHLCV_MON_H"
  TH_EARN="$THRESHOLD_EARNINGS_MON_H"
else
  TH_OHLCV="$THRESHOLD_OHLCV_H"
  TH_EARN="$THRESHOLD_EARNINGS_H"
fi

now_epoch="$(date +%s)"
errores=0
warnings=0

echo "[$(ts)] data_freshness: inicio (repo=$REPO)" >> "$LOG"

# Helper: dado un glob, halla el archivo con mtime más reciente (max %m)
# Uso: newest_file=$(find_newest "backend/data/cache/*.parquet data/cache/*.parquet")
# Retorna "" si no hay matches.
find_newest() {
  local newest="" newest_mtime=0
  # Expandir globs manualmente para soportar múltiples patrones
  for pat in "$@"; do
    # pat puede contener * — expandir con bash glob
    # shellcheck disable=SC2086
    for f in $REPO/$pat; do
      [[ -e "$f" ]] || continue
      # macOS stat
      local m
      m="$(stat -f %m "$f" 2>/dev/null || echo 0)"
      if [[ "$m" -gt "$newest_mtime" ]]; then
        newest_mtime="$m"
        newest="$f"
      fi
    done
  done
  echo "$newest"
}

# Helper: log de frescura genérico
# Args: colector path mtime_epoch threshold_h
check_freshness() {
  local colector="$1" path="$2" mtime_epoch="$3" threshold_h="$4"
  if [[ -z "$path" || ! -e "$path" ]]; then
    echo "[$(ts)] [WARN] $colector missing: no artefacto encontrado (patrón buscado, repo=$REPO)" >> "$LOG"
    warnings=$((warnings + 1))
    return 0
  fi
  local mtime_human
  mtime_human="$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$path" 2>/dev/null || echo "unknown")"
  local age_h
  age_h="$(awk "BEGIN{printf \"%.1f\", ($now_epoch - $mtime_epoch)/3600}")"
  # Comparación float vía awk
  local is_stale
  is_stale="$(awk "BEGIN{print (($now_epoch - $mtime_epoch)/3600 > $threshold_h) ? 1 : 0}")"
  # Relativizar path para log legible
  local rel
  rel="${path#$REPO/}"
  if [[ "$is_stale" == "1" ]]; then
    echo "[$(ts)] [ERROR] $colector STALE: age=${age_h}h > threshold ${threshold_h}h (last mtime $mtime_human path $rel)" >> "$LOG"
    errores=$((errores + 1))
  else
    echo "[$(ts)] [OK] $colector fresh: age=${age_h}h <= threshold ${threshold_h}h (mtime $mtime_human path $rel)" >> "$LOG"
  fi
}

# --- Mercado abierto para intraday (09:30-16:00 ET, lun-vie) ---
# Usa python3 + zoneinfo para zona correcta (incluye DST). Fallback: si python falla, asumir mercado abierto (fail-open → puede dar falso STALE fuera de horario, pero no silencia real STALE).
is_market_open() {
  python3 -c "
import sys
try:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo('America/New_York')
    now_et = datetime.now(et)
    wd = now_et.weekday()  # 0=lun ... 6=dom
    if wd >= 5:
        print(0)
        sys.exit(0)
    minutes = now_et.hour * 60 + now_et.minute
    open_min = 9*60 + 30
    close_min = 16*60
    print(1 if open_min <= minutes < close_min else 0)
except Exception as e:
    print(1)
" 2>/dev/null || echo 1
}

# ========== 1) OHLCV diario ==========
# Artefactos: backend/data/cache/*.parquet y data/cache/*.parquet (ambos, el más reciente manda)
ohlcv_path="$(find_newest "backend/data/cache/*.parquet" "data/cache/*.parquet")"
if [[ -n "$ohlcv_path" ]]; then
  mtime_ohlcv="$(stat -f %m "$ohlcv_path" 2>/dev/null || echo 0)"
  check_freshness "ohlcv_diario" "$ohlcv_path" "$mtime_ohlcv" "$TH_OHLCV"
else
  echo "[$(ts)] [WARN] ohlcv_diario missing: no parquet found in backend/data/cache/*.parquet nor data/cache/*.parquet" >> "$LOG"
  warnings=$((warnings + 1))
fi

# Opcional: verificar filas >0 si pyarrow disponible (no bloquea si no está)
if [[ -n "${ohlcv_path:-}" && -e "${ohlcv_path:-}" ]]; then
  if python3 -c "import pyarrow.parquet" 2>/dev/null; then
    rows="$(python3 -c "
import sys
try:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile('$ohlcv_path')
    print(pf.metadata.num_rows)
except Exception as e:
    print(f'ERR:{e}')
" 2>/dev/null || echo "ERR")"
    if [[ "$rows" == ERR* ]]; then
      echo "[$(ts)] [WARN] ohlcv_diario rows: no se pudo leer parquet ($rows) path ${ohlcv_path#$REPO/}" >> "$LOG"
      warnings=$((warnings + 1))
    elif [[ "$rows" == "0" ]]; then
      echo "[$(ts)] [ERROR] ohlcv_diario rows: parquet vacío (0 filas) path ${ohlcv_path#$REPO/}" >> "$LOG"
      errores=$((errores + 1))
    fi
  fi
fi

# ========== 2) earnings_sentiment ==========
# Artefacto de vida: el LOG de corrida diario (earnings_sentiment_run_*.txt,
# escrito ~22:00 siempre que el colector corre). La DB (earnings_sentiment.db)
# NO es artefacto de vida: es un store incremental con dedup por accession —
# solo cambia cuando llega un 8-K nuevo, lo que ocurre por rachas (earnings
# season). Vigilar su mtime producía ERROR espurio cualquier día sin filings
# nuevos (fix 2026-09-04: el latido detectó su propio falso positivo — db
# congelada 3 días mientras las corridas diarias reportaban 0 errores).
earn_path="$(find_newest "backend/data/cache/earnings_sentiment_run_*.txt" "data/cache/earnings_sentiment_run_*.txt")"
if [[ -n "$earn_path" ]]; then
  mtime_earn="$(stat -f %m "$earn_path" 2>/dev/null || echo 0)"
  check_freshness "earnings_sentiment" "$earn_path" "$mtime_earn" "$TH_EARN"
else
  echo "[$(ts)] [WARN] earnings_sentiment missing: no run log found (backend/data/cache/earnings_sentiment_run_*.txt)" >> "$LOG"
  warnings=$((warnings + 1))
fi

# ========== 3) intraday_1min ==========
intraday_path="$(find_newest "backend/data/cache/intraday_1min/*.parquet")"
market_open="$(is_market_open)"
# Normalizar (is_market_open puede imprimir newline)
market_open="$(echo "$market_open" | tr -d ' \n\r')"
if [[ -z "$intraday_path" ]]; then
  if [[ "$market_open" == "0" ]]; then
    echo "[$(ts)] [OK] intraday_1min SKIP (market closed, no parquet yet — esperado fuera de horario)" >> "$LOG"
  else
    echo "[$(ts)] [WARN] intraday_1min missing: no parquet in backend/data/cache/intraday_1min/*.parquet (market open, esperado al menos 1)" >> "$LOG"
    warnings=$((warnings + 1))
  fi
else
  mtime_intra="$(stat -f %m "$intraday_path" 2>/dev/null || echo 0)"
  mtime_human_intra="$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$intraday_path" 2>/dev/null || echo "unknown")"
  rel_intra="${intraday_path#$REPO/}"
  age_h_intra="$(awk "BEGIN{printf \"%.1f\", ($now_epoch - $mtime_intra)/3600}")"
  is_stale_intra="$(awk "BEGIN{print (($now_epoch - $mtime_intra)/3600 > $THRESHOLD_INTRADAY_H) ? 1 : 0}")"
  if [[ "$market_open" == "0" ]]; then
    echo "[$(ts)] [OK] intraday_1min SKIP (market closed, age=${age_h_intra}h mtime $mtime_human_intra path $rel_intra)" >> "$LOG"
  else
    if [[ "$is_stale_intra" == "1" ]]; then
      echo "[$(ts)] [ERROR] intraday_1min STALE: age=${age_h_intra}h > threshold ${THRESHOLD_INTRADAY_H}h (last mtime $mtime_human_intra path $rel_intra)" >> "$LOG"
      errores=$((errores + 1))
    else
      echo "[$(ts)] [OK] intraday_1min fresh: age=${age_h_intra}h <= threshold ${THRESHOLD_INTRADAY_H}h (mtime $mtime_human_intra path $rel_intra)" >> "$LOG"
    fi
  fi
fi

echo "[$(ts)] data_freshness: fin (errores=$errores warnings=$warnings)" >> "$LOG"
exit 0
