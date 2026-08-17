import { useEffect, useRef, useState } from "react";
import { ColorType, LineStyle, createChart, type IChartApi } from "lightweight-charts";
import { OhlcvBar } from "../../api/client";

interface Props {
  symbol: string;
  bars: OhlcvBar[];
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  last_close_date: string;
}

/**
 * Carta institutional: lightweight-charts (TradingView open-source) con
 * velas EOD + EMA50/200 + líneas de mecánica del motor (entrada/stop/target).
 *
 * Nota de honestidad (regla #4): los niveles dibujados son las zonas
 * mecánicas del motor (entry/stop 2×ATR/target 4×ATR), NO niveles predichos.
 * Sello "al último cierre" siempre visible.
 *
 * Fallback graceful: si lightweight-charts falla por cualquier razón,
 * se muestra un aviso sin romper la página.
 */
export function TradingViewChart({ symbol, bars, entry_price, stop_loss, take_profit, last_close_date }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;
    setChartError(null);

    let chart: IChartApi | null = null;
    try {
      chart = createChart(containerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "#131722" },
          textColor: "#d1d4dc",
        },
        grid: {
          vertLines: { color: "#1e222d" },
          horzLines: { color: "#1e222d" },
        },
        crosshair: { mode: 0 },
        timeScale: { timeVisible: false, borderColor: "#2a2e39" },
        rightPriceScale: { borderColor: "#2a2e39" },
        width: containerRef.current.clientWidth,
        height: 420,
      });
      chartRef.current = chart;

      const candles = chart.addCandlestickSeries({
        upColor: "#26a69a",
        downColor: "#ef5350",
        borderVisible: false,
        wickUpColor: "#26a69a",
        wickDownColor: "#ef5350",
      });
      candles.setData(
        bars.map((b) => ({
          time: b.date as string,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        }))
      );

      const ema50 = chart.addLineSeries({ color: "#f0b90b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      ema50.setData(
        bars.filter((b) => b.ema50 !== null).map((b) => ({ time: b.date as string, value: b.ema50 as number }))
      );

      const ema200 = chart.addLineSeries({ color: "#42a5f5", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      ema200.setData(
        bars.filter((b) => b.ema200 !== null).map((b) => ({ time: b.date as string, value: b.ema200 as number }))
      );

      // Zonas mecánicas del motor (no predicción): entrada / stop / target
      if (entry_price !== null)
        candles.createPriceLine({ price: entry_price, color: "#787b86", lineWidth: 1, lineStyle: LineStyle.Dashed, title: "entrada mecánica" });
      if (stop_loss !== null)
        candles.createPriceLine({ price: stop_loss, color: "#ef5350", lineWidth: 1, lineStyle: LineStyle.Solid, title: "stop 2×ATR" });
      if (take_profit !== null)
        candles.createPriceLine({ price: take_profit, color: "#26a69a", lineWidth: 1, lineStyle: LineStyle.Solid, title: "target 4×ATR" });

      chart.timeScale().fitContent();
    } catch (err) {
      setChartError(err instanceof Error ? err.message : "error de init de chart");
    }

    const ro = new ResizeObserver(() => {
      if (chart && containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    if (containerRef.current) ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [symbol, bars, entry_price, stop_loss, take_profit]);

  return (
    <div className="relative">
      {chartError ? (
        <div className="h-[420px] flex items-center justify-center text-tv-dim text-sm border border-dark-border rounded">
          Chart no disponible: {chartError}
        </div>
      ) : (
        <div ref={containerRef} />
      )}
      <div className="absolute top-2 left-2 flex gap-3 text-[11px] font-mono z-10">
        <span className="text-tv-dim">
          {symbol} · EOD · <span className="text-tv-text">al último cierre {last_close_date}</span>
        </span>
        <span><span className="inline-block w-3 h-0.5 bg-[#f0b90b] align-middle mr-1" />EMA50</span>
        <span><span className="inline-block w-3 h-0.5 bg-[#42a5f5] align-middle mr-1" />EMA200</span>
      </div>
    </div>
  );
}
