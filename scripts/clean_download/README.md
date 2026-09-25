# Descarga limpia ordenada — fortress_core (Omarchy)

**Estado:** PAUSA_YAHOO_MASS_DOWNLOAD activa en raíz. Este directorio contiene el plan sólido para reordenar todo y eliminar loop.

## Orden sólido (handoff 14-sep)

1. **Cuarentena:** cache actual contaminado (170 parquets en /mnt/mac/root/fortress_core_backups/current) → mover a `backend/data/cache_contaminated_20260914/` (no borrar, para forense)
2. **Fuente limpia:** snapshot más cercano pre-contaminación = `20260830_000044` en disco externo (verificar 2 pares dudosos COST/CRM), o descarga desde cero si snapshot también dudoso.
3. **Descarga limpia ticker por ticker:** un ticker a la vez, delay 3-5s, backoff exponencial en 429, verificación `validate_returns` + `reconcile_symbol` por ticker, hash SHA256 y manifest.
4. **Loop eliminado:** `warmup_advisor_loop` ahora duerme 300s si PAUSE presente; `download_data` retorna cache sin red si PAUSE presente. data_updater.sh diario no corre hasta levantar pausa.

## Ejecución (cuando levantes pausa)

```bash
# quitar pausa solo cuando Yahoo throttle haya bajado (verificar con 1 ticker probe)
rm ~/Work/fortress_core/PAUSE_YAHOO_MASS_DOWNLOAD

# descarga limpia
cd ~/Work/fortress_core/backend
python scripts/clean_download/download_ticker_by_ticker.py --universe 102 --delay 4 --verify

# verificar integridad post-descarga
python -m app.core.cache_integrity --check all --thresh 0.15
```

Ver PLAN_REMEDIO_BRECHAS_20260903.md §A0 y HANDOFF_SESION_20260914.md §2.
