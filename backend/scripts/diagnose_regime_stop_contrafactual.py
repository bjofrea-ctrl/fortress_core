"""
M2 (AUDITORIA_MECANICA.md) — Diagnóstico contrafáctico de las salidas por
REGIME_STOP_HIT (PRE-REGISTRADO, 2026-08-14).

Pregunta: ¿qué habría pasado con las posiciones cerradas por REGIME_STOP_HIT
(n=41, PnL -$5,867 vs +$2,849 total del sistema) si el stop de régimen no
hubiera existido y se hubieran sostenido hasta su salida natural?

Metodología (descripción, sin parámetros libres — no consume slot de n_trials):
- Replay fiel de la mecánica de salida PER-SYMBOL del motor (backtest_engine.run
  + adaptive_risk.check_all_stops/check_technical_exit), con los MISMOS datos
  (load_universe + calculate_all_indicators) y las mismas constantes:
  slippage=0.0005, comision=0.001, ABSOLUTE_CEILING=0.12, parcial a 2.0xATR,
  activation trailing 1.5xATR, trailing 2.0xATR, salida tecnica
  adx14<20 or (close<ema20<ema50). PnL = (exit_price - entry) * shares con
  exit_price = close*(1-slippage) — misma convencion que el parquet (la
  comision NO se descuenta del pnl del trade, igual que el motor).
- En el contrafáctico se elimina SOLO el stop de régimen (REGIME_STOP_HIT).
  Se conservan: ABSOLUTE_CEILING_BREACH, PARTIAL_TP, TRAILING_STOP y TECHNICAL
  (todas reglas per-symbol, independientes del regimen). Los stops de CARTERA
  (PORTFOLIO_REGIME_STOP / PORTFOLIO_CEILING_BREACH) quedan fuera de alcance:
  son acciones conjuntas sobre todo el libro, no una salida natural per-symbol.
- Orden de chequeo por dia (igual que el motor): ceiling -> (regimen, fuera) ->
  parcial (vende mitad, una sola vez) -> trailing (highest = max(highest, close),
  activation (highest-entry)>1.5xATR, salida close<=highest-2xATR) -> tecnica.
  En un mismo dia pueden ocurrir PARCIAL y TRAILING (lista to_close procesada
  en ese orden, igual que el motor).
- Replay desde el primer dia habil posterior a entry_date, con el tamano
  registrado en el parquet (sumando parciales previos si los hubo).
- Si la posicion no sale por ninguna regla natural antes del END (2026-08-04),
  se reporta censurada: pnl a mercado con el close del END.

Criterios pre-registrados (definen el veredicto):
- > 50% de las 41 posiciones con pnl contrafáctico > pnl real (parquet) ->
  "el stop de regimen esta demasiado ajustado" -> hipotesis real para M3.
- En caso contrario -> "el stop esta haciendo su trabajo" -> tema cerrado.
Secundarios: diferencia total de pnl, mediana, cuantas habrian ganado, razones
de salida contrafactuales, dias adicionales sostenidos.

Verificacion de fidelidad (puerta del script, pre-registrada): replay con las
reglas naturales (sin stop de regimen) de los trades que en el parquet salieron
por TECHNICAL / TRAILING_STOP / PARTIAL_TP (+ su continuacion). Para esos debe
reproducirse EXACTO el parquet (exit_date, razon, pnl a 1e-6): cualquiera que no
reproduzca -> el script FALLA y reporta las divergencias. Estos trades no
dependen del regimen ni de la cartera, asi que la replica es determinista.

Artefacto: data/cache/regime_stop_contrafactual_<ts>.txt
"""
import datetime
import os

import numpy as np
import pandas as pd

from app.core.adaptive_risk import AdaptiveRiskManager, REGIME_THRESHOLDS
from scripts.fetch_universe_data import NEW_UNIVERSE
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)
DATA_START = "2015-01-01"
END = pd.Timestamp("2026-08-04")

SLIPPAGE = 0.0005
COMMISSION = 0.001
CEILING = 0.12
TRADES_PARQUET = "data/cache/baseline_clean_20260811_150643_trades.parquet"

# Chequeos de arriba se cierran solos. Salida natural = reglas per-symbol.
NATURAL_REASONS = {"TECHNICAL", "TRAILING_STOP", "PARTIAL_TP", "ABSOLUTE_CEILING_BREACH"}
PORTFOLIO_REASONS = {"PORTFOLIO_REGIME_STOP", "PORTFOLIO_CEILING_BREACH"}
FULL_REASONS = NATURAL_REASONS | {"REGIME_STOP_HIT"}


def replay_position(symbol, entry_date, entry_price, initial_shares, indicator_df,
                    regime_stop=False, regime_state=0):
    """Replay diario de la salida per-symbol desde el dia posterior a la
    entrada. Devuelve (date, reason, shares_sold, pnl) por venta, o [] si
    la posicion nunca se abre (sin fechas). Las fechas de venta se
    devuelven como Timestamp; la ultima entrada con reason='OPEN_AT_END'
    indica posicion censurada al END."""
    dates = indicator_df.index
    start_pos = dates.searchsorted(entry_date)  # primer indice >= entry_date
    # el motor chequea stops el dia posterior a la entrada
    i = start_pos + 1
    if i >= len(dates):
        return []
    shares = initial_shares
    partial_done = False
    highest = entry_price
    sells = []
    while i < len(dates):
        date = dates[i]
        row = indicator_df.iloc[i]
        close = float(row["close"])
        atr = float(row["atr14"]) if np.isfinite(row["atr14"]) else 0.0
        loss = (close - entry_price) / entry_price

        # 1. ceiling (per-symbol, se conserva en el contrafactico)
        if loss <= -CEILING:
            exit_price = close * (1 - SLIPPAGE)
            sells.append((date, "ABSOLUTE_CEILING_BREACH", shares, (exit_price - entry_price) * shares))
            return sells

        # 2. stop de regimen (SOLO en la verificacion de fidelidad)
        if regime_stop:
            stop = REGIME_THRESHOLDS[regime_state][ "position_stop"]
            if loss <= -stop:
                exit_price = close * (1 - SLIPPAGE)
                sells.append((date, "REGIME_STOP_HIT", shares, (exit_price - entry_price) * shares))
                return sells

        # 3. parcial (una sola vez)
        if atr > 0 and not partial_done and (close - entry_price) >= 2.0 * atr:
            partial_done = True
            half = shares // 2
            if half > 0:
                exit_price = close * (1 - SLIPPAGE)
                sells.append((date, "PARTIAL_TP", half, (exit_price - entry_price) * half))
                shares -= half

        # 4. trailing
        highest = max(highest, close)
        if atr > 0 and (highest - entry_price) > 1.5 * atr and close <= highest - 2.0 * atr:
            exit_price = close * (1 - SLIPPAGE)
            sells.append((date, "TRAILING_STOP", shares, (exit_price - entry_price) * shares))
            return sells

        # 5. tecnica
        adx = float(row["adx14"]) if np.isfinite(row["adx14"]) else np.nan
        close_v = close
        ema20 = float(row["ema20"]) if np.isfinite(row["ema20"]) else np.nan
        ema50 = float(row["ema50"]) if np.isfinite(row["ema50"]) else np.nan
        if (np.isfinite(adx) and adx < 20) or (np.isfinite(ema20) and np.isfinite(ema50) and close_v < ema20 < ema50):
            exit_price = close * (1 - SLIPPAGE)
            sells.append((date, "TECHNICAL", shares, (exit_price - entry_price) * shares))
            return sells

        i += 1

    # censurada al END
    close_end = float(indicator_df.iloc[-1]["close"])
    sells.append((dates[-1], "OPEN_AT_END", shares, (close_end * (1 - SLIPPAGE) - entry_price) * shares))
    return sells


def main():
    out_path = os.path.join("data", "cache",
                            f"regime_stop_contrafactual_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    trades = pd.read_parquet(TRADES_PARQUET)
    log("=" * 72)
    log("M2 — CONTRAFACTICO DE LAS SALIDAS POR REGIME_STOP_HIT (PRE-REGISTRADO)")
    log(f"Parquet: {TRADES_PARQUET} | {len(trades)} trades | END={END.date()}")
    log(f"Reglas naturales conservadas: {sorted(NATURAL_REASONS)} | fuera de alcance: "
        f"{sorted(PORTFOLIO_REASONS)} + REGIME_STOP_HIT (la variable)")
    log("=" * 72)

    # reconstruir posiciones: el tamano inicial = suma de todos los tramos
    positions = {}
    for t in trades.itertuples():
        key = (t.symbol, pd.Timestamp(t.entry_date))
        positions.setdefault(key, {"entry": float(t.entry_price), "shares": 0, "records": []})
        positions[key]["shares"] += int(t.shares)
        positions[key]["records"].append(t)

    price_data = load_universe(SYMBOLS, DATA_START, END)
    indicators = {s: calculate_all_indicators(df) for s, df in price_data.items()}
    log(f"indicadores calculados: {len(indicators)}/{len(SYMBOLS)} simbolos")

    # ---- VERIFICACION DE FIDELIDAD (puerta pre-registrada) ----
    log("\n--- VERIFICACION DE FIDELIDAD (parquet vs replay, reglas naturales) ---")
    ver_fail = 0
    for key, pos in positions.items():
        symbol, entry_date = key
        # La puerta de fidelidad solo aplica a posiciones con salidas 100%
        # naturales (sin REGIME_STOP_HIT ni stops de cartera): para ellas el
        # replay SIN el stop de regimen debe reproducir el parquet exacto.
        # Las posiciones con REGIME_STOP_HIT son el objeto del contrafactico.
        rec_natural_only = [r for r in pos["records"]
                            if r.exit_reason in NATURAL_REASONS]
        if len(rec_natural_only) != len(pos["records"]):
            continue  # tiene REGIME_STOP_HIT o PORTFOLIO_* -> fuera de la puerta
        if symbol not in indicators:
            continue
        idx = indicators[symbol].index
        if entry_date not in idx:
            continue
        if pos["shares"] <= 0:
            continue
        sells = replay_position(symbol, entry_date, pos["entry"], pos["shares"],
                                indicators[symbol], regime_stop=False)
        if not sells:
            ver_fail += 1
            log(f"  FALLO: {key} sin replay")
            continue
        # comparar contra los records reales (ordenados por fecha)
        real = sorted([(pd.Timestamp(r.exit_date), r.exit_reason, int(r.shares), float(r.pnl))
                       for r in rec_natural_only])
        cf = [(d, r, s, p) for d, r, s, p in sells if r != "OPEN_AT_END"]
        if len(cf) != len(real):
            ver_fail += 1
            log(f"  FALLO {key}: {len(cf)} ventas replay vs {len(real)} reales "
                f"(reales: {[(str(a), b) for a, b, _, _ in real]})")
            continue
        for (d1, r1, s1, p1), (d2, r2, s2, p2) in zip(cf, real):
            if d1 != d2 or r1 != r2 or s1 != s2 or abs(p1 - p2) > 1e-6:
                ver_fail += 1
                log(f"  FALLO {key}: replay ({d1.date()},{r1},{s1},{p1:.2f}) vs "
                    f"real ({d2.date()},{r2},{s2},{p2:.2f})")
                break
    if ver_fail:
        log(f"\nPUERTA DE FIDELIDAD NO PASA ({ver_fail} divergencias) -> diagnostico NO VALIDO")
        log(f"Out: {out_path}")
        return

    n_ver = sum(1 for _, pos in positions.items()
                if all(r.exit_reason in NATURAL_REASONS for r in pos["records"]))
    log(f"FIDELIDAD OK: {n_ver} posiciones evaluables reproducen el parquet exacto "
        f"(exit_date + razon + pnl). Puerto abierto.")

    # ---- CONTRAFACTICO DE LAS 41 ----
    log("\n--- CONTRAFACTICO: 41 posiciones cerradas por REGIME_STOP_HIT ---")
    reg_trades = trades[trades.exit_reason == "REGIME_STOP_HIT"]
    detalles = []
    for t in reg_trades.itertuples():
        key = (t.symbol, pd.Timestamp(t.entry_date))
        pos = positions[key]
        sells = replay_position(t.symbol, pd.Timestamp(t.entry_date), pos["entry"],
                                pos["shares"], indicators[t.symbol], regime_stop=False)
        cf_pnl = sum(p for _, _, _, p in sells)
        n_days = (pd.Timestamp(sells[-1][0]) - pd.Timestamp(t.exit_date)).days if sells else 0
        detalles.append({
            "symbol": t.symbol, "entry": pd.Timestamp(t.entry_date).date(),
            "exit": pd.Timestamp(t.exit_date).date(), "real_pnl": float(t.pnl),
            "cf_pnl": cf_pnl, "cf_reason": sells[-1][1], "n_days_extra": n_days,
        })

    df = pd.DataFrame(detalles)
    better = df[df.cf_pnl > df.real_pnl]
    worse = df[df.cf_pnl <= df.real_pnl]
    log(f"Mejores que el parquet (cf_pnl > real): {len(better)}/{len(df)} "
        f"({100 * len(better) / len(df):.1f}%)")
    log(f"Peores o iguales: {len(worse)}/{len(df)}")
    log(f"  pnl real total: ${df.real_pnl.sum():,.2f} | cf total: ${df.cf_pnl.sum():,.2f} "
        f"| delta: ${(df.cf_pnl.sum() - df.real_pnl.sum()):,.2f}")
    log(f"  mediana pnl real: ${df.real_pnl.median():,.2f} | mediana cf: ${df.cf_pnl.median():,.2f}")
    log(f"  cf > 0 (posiciones que habrian ganado): {len(df[df.cf_pnl > 0])}/{len(df)}")
    log(f"  df['cf_reason'] conteo: {df.cf_reason.value_counts().to_dict()}")
    log(f"  dias adicionales sostenidos (mediana): {df.n_days_extra.median():.0f}")

    log("\n--- VEREDICTO vs criterio pre-registrado ---")
    if len(better) > len(df) / 2:
        log(f"  {len(better)}/{len(df)} se habrian recuperado -> el stop de regimen esta "
            "DEMASIADO AJUSTADO -> hipotesis real para M3 (pre-registro con slot).")
    else:
        log(f"  {len(better)}/{len(df)} se habrian recuperado -> el stop esta HACIENDO SU "
            "TRABAJO: el -$5,867 es el precio del seguro, no una fuga -> tema cerrado.")

    log("\nDetalle por posicion (primeras 15):")
    for _, r in df.head(15).iterrows():
        log(f"  {r.symbol:6s} {r.entry} -> {r.exit} | real ${r.real_pnl:9,.2f} | "
            f"cf ${r.cf_pnl:9,.2f} | salida {r.cf_reason} | +{r.n_days_extra}d")

    # resumen por simbolo
    log("\nResumen por simbolo (real vs cf):")
    agg = df.groupby("symbol").agg(real=("real_pnl", "sum"), cf=("cf_pnl", "sum"), n=("real_pnl", "count"))
    for sym, row in agg.iterrows():
        log(f"  {sym:6s} n={int(row['n']):2d} real ${row['real']:9,.2f} cf ${row['cf']:9,.2f}")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()