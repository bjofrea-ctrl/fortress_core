"""Wrapper para event_pairs.py — punto de entrada CLI.

Mismo patrón que pipeline_daily_signal.py: scripts/ es el entry point,
app/core/ es la librería. Ejecutar con:
  cd backend && .venv/bin/python -m scripts.event_pairs --long CAT --short TRV --qty 10
"""
import sys

from app.core.event_pairs import main

if __name__ == "__main__":
    sys.exit(main())
