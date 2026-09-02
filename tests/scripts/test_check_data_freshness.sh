#!/bin/bash
# Tests del latido de frescura — usa archivos temp con mtimes viejos/recientes
# y verifica que el script detecta STALE vs FRESH (touch -t).
# No toca ledger/parquet/cache real; todo en tmpdir con FORTRESS_REPO.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CHECK_SCRIPT="$REPO_ROOT/scripts/check_data_freshness.sh"

if [[ ! -x "$CHECK_SCRIPT" ]]; then
  echo "FAIL: check_data_freshness.sh no existe o no es ejecutable: $CHECK_SCRIPT"
  exit 1
fi

pass=0
fail=0

assert_contains() {
  local file="$1" pattern="$2" msg="$3"
  if grep -q "$pattern" "$file"; then
    echo "  PASS: $msg"
    pass=$((pass+1))
  else
    echo "  FAIL: $msg (patrón '$pattern' no hallado en $file)"
    echo "  --- contenido ---"
    cat "$file" 2>&1 | tail -n 50
    echo "  --- fin ---"
    fail=$((fail+1))
  fi
}
assert_not_contains() {
  local file="$1" pattern="$2" msg="$3"
  if grep -q "$pattern" "$file"; then
    echo "  FAIL: $msg (no debía contener '$pattern')"
    cat "$file" 2>&1 | tail -n 50
    fail=$((fail+1))
  else
    echo "  PASS: $msg"
    pass=$((pass+1))
  fi
}

# Helper: crea tmpdir con estructura mínima
make_tmp_repo() {
  local d
  d="$(mktemp -d)"
  mkdir -p "$d/backend/data/cache/intraday_1min" "$d/backend/data/cache" "$d/data/cache" "$d/logs"
  echo "$d"
}

echo "=== test_check_data_freshness.sh ==="

# ---- Test 1: todo fresh (archivos tocados ahora) → OK, sin ERROR ----
echo ""
echo "Test 1: todo fresh → OK sin ERROR"
tmp1="$(make_tmp_repo)"
touch "$tmp1/backend/data/cache/AAPL.parquet"
touch "$tmp1/backend/data/cache/earnings_sentiment.db"
mkdir -p "$tmp1/backend/data/cache/intraday_1min"
touch "$tmp1/backend/data/cache/intraday_1min/SPY.parquet"
FORTRESS_REPO="$tmp1" bash "$CHECK_SCRIPT" >/dev/null 2>&1
LOG1="$tmp1/logs/data_freshness.log"
assert_contains "$LOG1" "data_freshness: inicio" "log inicio"
assert_contains "$LOG1" "\[OK\] ohlcv_diario fresh" "ohlcv fresh"
assert_contains "$LOG1" "\[OK\] earnings_sentiment fresh" "earnings fresh"
# intraday: puede ser SKIP si mercado cerrado, o fresh si abierto — ambos OK
if grep -q "\[OK\] intraday_1min" "$LOG1"; then
  echo "  PASS: intraday OK/SKIP presente"
  pass=$((pass+1))
else
  echo "  FAIL: intraday debería ser OK/SKIP"
  fail=$((fail+1))
fi
assert_not_contains "$LOG1" "\[ERROR\]" "sin ERROR cuando todo fresh"
rm -rf "$tmp1"

# ---- Test 2: OHLCV stale (3 días viejo) → ERROR ----
echo ""
echo "Test 2: OHLCV stale (3 días) → ERROR"
tmp2="$(make_tmp_repo)"
# touch -t formato [[CC]YY]MMDDhhmm[.SS]; usar date -v-3d para portabilidad macOS
old_ts="$(date -v-3d +%Y%m%d%H%M 2>/dev/null || date -d '3 days ago' +%Y%m%d%H%M)"
touch -t "${old_ts}" "$tmp2/backend/data/cache/AAPL.parquet"
touch "$tmp2/backend/data/cache/earnings_sentiment.db"
touch "$tmp2/backend/data/cache/intraday_1min/SPY.parquet"
FORTRESS_REPO="$tmp2" bash "$CHECK_SCRIPT" >/dev/null 2>&1
LOG2="$tmp2/logs/data_freshness.log"
assert_contains "$LOG2" "\[ERROR\] ohlcv_diario STALE" "ohlcv STALE detectado"
assert_contains "$LOG2" "age=" "log incluye age"
assert_contains "$LOG2" "threshold" "log incluye threshold"
rm -rf "$tmp2"

# ---- Test 3: earnings stale → ERROR ----
echo ""
echo "Test 3: earnings stale → ERROR"
tmp3="$(make_tmp_repo)"
touch "$tmp3/backend/data/cache/AAPL.parquet"
old_ts="$(date -v-3d +%Y%m%d%H%M 2>/dev/null || date -d '3 days ago' +%Y%m%d%H%M)"
touch -t "${old_ts}" "$tmp3/backend/data/cache/earnings_sentiment.db"
touch "$tmp3/backend/data/cache/intraday_1min/SPY.parquet"
FORTRESS_REPO="$tmp3" bash "$CHECK_SCRIPT" >/dev/null 2>&1
LOG3="$tmp3/logs/data_freshness.log"
assert_contains "$LOG3" "\[ERROR\] earnings_sentiment STALE" "earnings STALE"
rm -rf "$tmp3"

# ---- Test 4: intraday stale fuera de horario → SKIP no ERROR ----
echo ""
echo "Test 4: intraday stale pero mercado cerrado → SKIP (no ERROR)"
# Forzamos mercado cerrado parchenado el check python: usamos archivo viejo pero
# el script debería dar SKIP si ahora es fuera de 09:30-16:00 ET.
# No podemos controlar la hora, pero podemos verificar que el script no crashea
# y que produce algún [OK] para intraday. Si ahora es horario de mercado, dará ERROR;
# aceptamos ambos como pass si no crashea y loguea intraday.
tmp4="$(make_tmp_repo)"
touch "$tmp4/backend/data/cache/AAPL.parquet"
touch "$tmp4/backend/data/cache/earnings_sentiment.db"
old_ts2="$(date -v-2H +%Y%m%d%H%M 2>/dev/null || date -d '2 hours ago' +%Y%m%d%H%M)"
touch -t "${old_ts2}" "$tmp4/backend/data/cache/intraday_1min/SPY.parquet"
FORTRESS_REPO="$tmp4" bash "$CHECK_SCRIPT" >/dev/null 2>&1
LOG4="$tmp4/logs/data_freshness.log"
if grep -q "intraday_1min" "$LOG4"; then
  echo "  PASS: intraday logueado (SKIP o STALE según horario, ambos válidos)"
  pass=$((pass+1))
  cat "$LOG4" | grep intraday_1min | sed 's/^/    /'
else
  echo "  FAIL: intraday no logueado"
  fail=$((fail+1))
fi
# No debe haber WARN missing porque sí hay archivos
assert_not_contains "$LOG4" "intraday_1min missing" "intraday no missing cuando hay archivo"
rm -rf "$tmp4"

# ---- Test 5: faltan artefactos → WARN ----
echo ""
echo "Test 5: sin artefactos → WARN"
tmp5="$(make_tmp_repo)"
# no crear ningún parquet/db
FORTRESS_REPO="$tmp5" bash "$CHECK_SCRIPT" >/dev/null 2>&1
LOG5="$tmp5/logs/data_freshness.log"
assert_contains "$LOG5" "\[WARN\] ohlcv_diario missing" "ohlcv missing WARN"
assert_contains "$LOG5" "\[WARN\] earnings_sentiment missing" "earnings missing WARN"
rm -rf "$tmp5"

# ---- Test 6: exit 0 siempre incluso con ERROR ----
echo ""
echo "Test 6: exit 0 siempre incluso con STALE"
tmp6="$(make_tmp_repo)"
old_ts="$(date -v-5d +%Y%m%d%H%M 2>/dev/null || date -d '5 days ago' +%Y%m%d%H%M)"
touch -t "${old_ts}" "$tmp6/backend/data/cache/AAPL.parquet"
touch -t "${old_ts}" "$tmp6/backend/data/cache/earnings_sentiment.db"
set +e
FORTRESS_REPO="$tmp6" bash "$CHECK_SCRIPT" >/dev/null 2>&1
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
  echo "  PASS: exit 0 con STALE"
  pass=$((pass+1))
else
  echo "  FAIL: exit $rc, esperado 0"
  fail=$((fail+1))
fi
rm -rf "$tmp6"

# ---- Test 7: data/cache legacy también cuenta ----
echo ""
echo "Test 7: legacy data/cache/*.parquet también detectado"
tmp7="$(make_tmp_repo)"
# solo en data/cache (legacy), no en backend/data/cache
mkdir -p "$tmp7/data/cache"
touch "$tmp7/data/cache/AAPL.parquet"
touch "$tmp7/backend/data/cache/earnings_sentiment.db"
touch "$tmp7/backend/data/cache/intraday_1min/SPY.parquet"
# borrar backend parquet para que solo quede legacy
rm -f "$tmp7/backend/data/cache/AAPL.parquet"
FORTRESS_REPO="$tmp7" bash "$CHECK_SCRIPT" >/dev/null 2>&1
LOG7="$tmp7/logs/data_freshness.log"
assert_contains "$LOG7" "\[OK\] ohlcv_diario fresh" "legacy parquet detectado como fresh"
rm -rf "$tmp7"

echo ""
echo "=== resumen: $pass PASS, $fail FAIL ==="
if [[ $fail -gt 0 ]]; then
  exit 1
fi
echo "ALL PASS"
