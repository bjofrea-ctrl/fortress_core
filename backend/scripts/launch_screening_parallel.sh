#!/bin/bash
# Lanzador paralelo para screening_palas — 3 procesos independientes (PPID 1)
# Cada uno con checkpoint y artefacto separados por subconjunto (sin race).
# NO re-corre end-to-end hasta que OpenCode cierre el diagnóstico metodológico.
# Uso: bash backend/scripts/launch_screening_parallel.sh  (desde raíz del repo)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$REPO_ROOT/backend"
# Venv canónico del repo real (Python 3.9.6 con deps). Ajustar si tu venv está en $BACKEND/.venv
VENV_PY="/Users/boris/Desktop/fortress_core/backend/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  VENV_PY="$BACKEND/.venv/bin/python"
fi
if [ ! -x "$VENV_PY" ]; then
  echo "No se encontró venv python en $VENV_PY ni $BACKEND/.venv/bin/python" >&2
  exit 1
fi

cd "$BACKEND"
echo "== launch_screening_parallel.sh =="
echo "venv: $VENV_PY ($($VENV_PY --version 2>&1))"
echo "backend: $BACKEND"
echo "hw.memsize: $(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.1f GB", $1/1024/1024/1024}')  (vm_stat free: $(vm_stat | awk '/Pages free/ {print $3}'))"
echo ""

for SUBSET in PALA RESTO POOLED; do
  TS=$(date +%Y%m%d_%H%M%S)
  LOG="data/cache/screening_palas_${SUBSET}_${TS}.nohup.log"
  CKPT="data/cache/screening_palas_checkpoint_${SUBSET}.json"
  echo "[launch] $SUBSET -> LOG=$LOG  CKPT=$CKPT"
  # -u = unbuffered, para que el log se vea en tiempo real con tail -f
  nohup "$VENV_PY" -u -m scripts.screening_palas_parallel --subset "$SUBSET" > "$LOG" 2>&1 &
  PID=$!
  disown
  # PPID dentro de esta shell sigue siendo esta shell; tras cerrar la shell será 1 (launchd).
  # Verificación inmediata:
  PPID_NOW=$(ps -o ppid= -p "$PID" 2>/dev/null | tr -d ' ' || echo "?")
  RSS_NOW=$(ps -o rss= -p "$PID" 2>/dev/null | tr -d ' ' || echo "?")
  echo "  PID=$PID  PPID_actual=$PPID_NOW  RSS_inicial=${RSS_NOW}KB  (tras disown; al cerrar esta shell PPID->1)"
  # Confirmar que checkpoint y artefacto usan sufijo por subconjunto (sin race con hermanos)
  echo "  checkpoint: $CKPT"
  echo "  artefacto:  data/cache/screening_palas_${SUBSET}_${TS}.txt/.json"
  sleep 1
  # chequeo de que no comparte archivo con hermanos
  if [ -e "data/cache/screening_palas_checkpoint.json" ]; then
    echo "  AVISO: existe checkpoint compartido legacy data/cache/screening_palas_checkpoint.json — los procesos paralelos NO lo usan (usan sufijo _\${SUBSET})"
  fi
  echo ""
done

echo "Tres procesos lanzados (nohup+disown, PPID 1 tras cerrar esta shell)."
echo "Verificar:"
echo "  ps -o pid,ppid,rss,vsz,etime,command | grep screening_palas_parallel"
echo "  tail -f data/cache/screening_palas_PALA_*.nohup.log"
echo "  tail -f data/cache/screening_palas_RESTO_*.nohup.log"
echo "  tail -f data/cache/screening_palas_POOLED_*.nohup.log"
echo "  ls -lh data/cache/screening_palas_checkpoint_*.json"
echo ""
echo "NO re-correr hasta que OpenCode cierre el diagnóstico (N_TRIALS/rangos/tolerancias/pre-registro bloqueados)."
