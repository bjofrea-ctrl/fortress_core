"""Prueba integral del motor predictivo Fortress Core."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from app.core.data_ingestion import download_data
from app.core.predictive_engine import PredictiveEngine, format_recommendation
from app.core.predictive_indicators import calculate_predictive_indicators

print("=== PRUEBA MOTOR PREDICTIVO FORTRESS CORE ===")
print()

# 1. Prueba indicadores predictivos
print("1) Test indicadores predictivos...")
try:
    df = download_data("AAPL", "2020-01-01")
    df = calculate_predictive_indicators(df)
    required_cols = [
        "williams_r", "cci", "parabolic_sar", "donchian_upper",
        "mfi14", "obv", "ad_line", "cmf20", "force_index",
        "pvt", "vpc_score", "volume_divergence", "smi_proxy",
        "ichimoku_tenkan", "bearish_divergence",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"   ❌ Faltan columnas: {missing}")
    else:
        print(f"   ✅ 15 indicadores predictivos calculados ({len(df)} registros)")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 2. Prueba motor predictivo sin fundamentales ni macro
print("\n2) Test motor predictivo (sin fundamentales ni macro)...")
try:
    engine = PredictiveEngine()
    df = download_data("AAPL", "2020-01-01")
    result = engine.analyze(symbol="AAPL", df=df, regime_state=0)
    print(f"   ✅ Score: {result.composite_score:.4f} | Decisión: {result.decision}")
    print(f"   ✅ Prob corto: {result.prob_up_short:.2%} | mediano: {result.prob_up_medium:.2%} | largo: {result.prob_up_long:.2%}")
    print(f"   ✅ Señales: {len(result.signals)}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 3. Prueba con fundamentales
print("\n3) Test motor predictivo con fundamentales...")
try:
    fundamentals = {
        "pe_ratio": 35.2, "pb_ratio": 55.3, "ev_ebitda": 24.5,
        "roe": 147.9, "roa": 31.6, "debt_equity": 1.75,
        "fcf_yield": 0.6, "div_yield": 0.4, "eps_growth": 8.2,
        "gross_margin": 46.2, "peg": 2.8, "current_ratio": 0.9,
        "asset_turnover": 1.1, "book_value_growth": 12.1, "sue_score": 1.2,
    }
    result = engine.analyze(symbol="AAPL", df=df, regime_state=0, fundamentals=fundamentals)
    print(f"   ✅ Fund. score: {result.fundamental_score:.4f}")
    print(f"   ✅ Señales totales: {len(result.signals)}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 4. Prueba con macro data
print("\n4) Test motor predictivo con datos macro...")
try:
    macro_tickers = {"DXY": "DX-Y.NYB", "gold": "GC=F", "silver": "SI=F", "SPY": "SPY"}
    macro_data = {}
    for name, ticker in macro_tickers.items():
        try:
            df_macro = download_data(ticker, "2020-01-01")
            if len(df_macro) > 30:
                macro_data[name] = df_macro
        except Exception:
            continue

    if macro_data:
        result = engine.analyze(
            symbol="AAPL", df=df, regime_state=0,
            fundamentals=fundamentals, macro_data=macro_data,
        )
        print(f"   ✅ Macro score: {result.macro_score:.4f}")
        print(f"   ✅ Señales: {len(result.signals)}")
        print(f"   ✅ Activos macro: {list(macro_data.keys())}")
    else:
        print("   ⚠️ No se pudieron cargar datos macro")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 5. Prueba con prediction markets
print("\n5) Test con señales de mercados de predicción (Polymarket)...")
try:
    pred_data = {
        "recession_prob": 0.22,
        "fed_cut_prob": 0.75,
        "inflation_prob": 0.15,
        "default_prob": 0.05,
        "unemployment_prob": 0.18,
    }
    result = engine.analyze(
        symbol="AAPL", df=df, regime_state=0,
        prediction_data=pred_data,
    )
    print(f"   ✅ Sentimiento score: {result.sentiment_score:.4f}")
    print(f"   ✅ Señales polymarket incluidas: {sum(1 for s in result.signals if 'Polymarket' in s.name)}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 6. Prueba completa
print("\n6) Test motor predictivo COMPLETO...")
try:
    result = engine.analyze(
        symbol="AAPL", df=df, regime_state=0,
        fundamentals=fundamentals,
        macro_data=macro_data if 'macro_data' in locals() else None,
        prediction_data=pred_data,
    )
    print(format_recommendation(result))
    print(f"\n   ✅ Score: {result.composite_score:.4f}")
    print(f"   ✅ Manipulación: {len(result.manipulation_signals)} señales")
    print(f"   ✅ Señales totales: {len(result.signals)}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 7. Test multi-símbolo
print("\n7) Test análisis multi-símbolo...")
try:
    symbols_to_test = ["AAPL", "MSFT", "NVDA", "AMZN"]
    for sym in symbols_to_test:
        try:
            df_sym = download_data(sym, "2020-01-01")
            if len(df_sym) < 200:
                continue
            res = engine.analyze(symbol=sym, df=df_sym, regime_state=0)
            print(f"   ✅ {sym}: {res.decision} ({res.composite_score:+.4f}) → Prob corto: {res.prob_up_short:.1%}")
        except Exception as e:
            print(f"   ⚠️ {sym}: Error: {e}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n=== ✅✅✅ PRUEBAS MOTOR PREDICTIVO COMPLETADAS ===")