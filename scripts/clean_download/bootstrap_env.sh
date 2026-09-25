#!/usr/bin/env bash
# Bootstrap env en /tmp (NO en el árbol del repo)
# Uso: source scripts/clean_download/bootstrap_env.sh
# Crea venv en /tmp/fortress_clean_dl_venv, instala requirements pinned
# Reporta compatibilidad py3.14 vs pins

set -euo pipefail

VENV_DIR="/tmp/fortress_clean_dl_venv"
REQ_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/backend/requirements.txt"

echo "=== Bootstrap ETAPA 0 env ==="
echo "VENV: $VENV_DIR"
echo "Requirements: $REQ_FILE"

# 1. Crear venv con python3 (system)
python3 -m venv "$VENV_DIR" --clear
echo "Venv creado"

# 2. Upgrade pip/setuptools/wheel
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

# 3. Instalar requirements pinned
"$VENV_DIR/bin/python" -m pip install -r "$REQ_FILE"

# 4. Verificar versiones instaladas vs pins
echo ""
echo "=== Versiones instaladas vs requirements.txt ==="
"$VENV_DIR/bin/python" -m pip list --format=freeze | grep -E "$(tr '\n' '|' < "$REQ_FILE" | sed 's/|$//')"

# 5. Compatibilidad Python 3.14
echo ""
echo "=== Python version ==="
"$VENV_DIR/bin/python" --version

echo ""
echo "=== Check compatibilidad py3.14 (heurístico) ==="
# PyPI metadata check: pip index versions no está disponible offline.
# Verificamos constraints conocidos:
# - torch 2.2.2: NO tiene wheel py3.14 (máx 3.12 en 2024)
# - transformers 4.44.2: py3.14 no probado oficialmente
# - statsmodels 0.14.6: py3.14 experimental
# - numpy 1.26.3: py3.14 no soportado (requiere >=2.0)
# - pandas 2.2.0: py3.14 no soportado (requiere >=2.2.1)
# - scipy 1.12.0: py3.14 no soportado (requiere >=1.13)
# - scikit-learn 1.4.0: py3.14 no soportado (requiere >=1.5)
# - hmmlearn 0.3.0: sin release desde 2022, py3.14 improbable
# - yfinance 1.2.0: pure python, probablemente OK
# - fastapi 0.109.0: py3.14 probablemente OK (starlette/pydantic sí)
# - pydantic-settings 2.1.0: pydantic 2.x soporta py3.14 desde 2.8+

cat << 'EOF'
⚠️  ALERTA COMPATIBILIDAD PYTHON 3.14:
Los pins actuales (requirements.txt) son para Python 3.9-3.12.
Python 3.14 (previsto oct 2025) ROMPE la mayoría de deps científicas:
  - numpy>=2.0 requerido (pin: 1.26.3) → BREAKING
  - pandas>=2.2.1 requerido (pin: 2.2.0) → BREAKING  
  - scipy>=1.13 requerido (pin: 1.12.0) → BREAKING
  - scikit-learn>=1.5 requerido (pin: 1.4.0) → BREAKING
  - statsmodels>=0.15 requerido (pin: 0.14.6) → BREAKING
  - torch 2.2.2: sin wheel py3.14 → compilar desde fuente (lento, falla probable)
  - hmmlearn 0.3.0: abandono, sin py3.14
  - transformers 4.44.2: py3.14 no testeado

RECOMENDACIÓN: Mantener Python 3.9/3.10/3.11 para producción.
Si migran a 3.12+, actualizar TODOS los pins en bloque (testing obligatorio).
EOF

echo ""
echo "=== Venv listo en $VENV_DIR ==="
echo "Para usar: source $VENV_DIR/bin/activate"
echo "Runner: $VENV_DIR/bin/python scripts/clean_download/download_ticker_by_ticker.py"