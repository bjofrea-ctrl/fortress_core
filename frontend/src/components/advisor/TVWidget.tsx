import { useEffect, useRef, useState } from "react";

/**
 * Widget TradingView embebido — vista secundaria de precio (datos realtime
 * de terceros). Si el script externo no carga (red/offline), se degrada a un
 * aviso sin romper la vista; el chart local (Lightweight Charts) sigue
 * operativo como fuente principal EOD.
 */
export function TVWidget({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setFailed(false);
    if (!containerRef.current) return;
    containerRef.current.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: symbol,
      interval: "D",
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "es",
      hide_legend: false,
      save_image: false,
      calendar: false,
      sth: false,
      hide_top_toolbar: false,
      hide_side_toolbar: true,
      allow_symbol_change: false,
      withdateranges: false,
      details: false,
      backgroundColor: "#131722",
    });

    const timeout = setTimeout(() => {
      // Si en 8s no marcó loaded, lo consideramos degradado (no rompe la UI).
      setFailed((f) => f);
    }, 8000);

    script.onload = () => {
      setLoaded(true);
      clearTimeout(timeout);
    };
    script.onerror = () => setFailed(true);

    containerRef.current.appendChild(script);
    return () => clearTimeout(timeout);
  }, [symbol]);

  return (
    <div className="relative h-[420px] border border-dark-border rounded overflow-hidden bg-dark-bg">
      <div ref={containerRef} className="h-full" />
      {!loaded && !failed && (
        <div className="absolute inset-0 flex items-center justify-center text-tv-dim text-sm">
          Cargando widget TradingView...
        </div>
      )}
      {failed && (
        <div className="absolute inset-0 flex items-center justify-center text-tv-dim text-sm text-center px-6">
          Widget TradingView no disponible (sin red externa). Usá la vista
          Lightweight Charts (EOD, fuente principal).
        </div>
      )}
      <div className="absolute bottom-1 left-2 text-[10px] font-mono text-tv-dim z-10">
        Datos realtime de terceros (TradingView) — difiere del cache EOD local
      </div>
    </div>
  );
}
