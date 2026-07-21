"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";

export type PriceData = {
  date: string;
  close: number;
  open: number;
  high: number;
  low: number;
};

function toDay(date: string): string {
  return date.slice(0, 10);
}

/**
 * Interactive OHLC/line chart built on TradingView's lightweight-charts
 * (Apache-2.0). Pure-canvas, offline, ~35 kB — adds crosshair, pan/zoom and a
 * proper time axis that the previous hand-rolled SVG could not provide.
 */
export function LightweightPriceChart({
  data,
  chartType,
  onHover,
}: {
  data: PriceData[];
  chartType: "line" | "candle";
  onHover?: (point: PriceData | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const dark =
      typeof document !== "undefined" &&
      (document.documentElement.classList.contains("dark") ||
        window.matchMedia?.("(prefers-color-scheme: dark)").matches === true);

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: dark ? "#a1a1aa" : "#71717a",
        fontSize: 11,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: dark ? "#27272a" : "#f4f4f5" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: { mode: 1 },
    });

    // lightweight-charts requires strictly ascending, de-duplicated times.
    const byDay = new Map<string, PriceData>();
    for (const point of data) {
      if (point && point.date) byDay.set(toDay(point.date), point);
    }
    const sorted = [...byDay.entries()].sort((a, b) => a[0].localeCompare(b[0]));

    if (chartType === "candle") {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });
      series.setData(
        sorted.map(([time, d]) => ({
          time: time as Time,
          open: d.open ?? d.close,
          high: d.high ?? d.close,
          low: d.low ?? d.close,
          close: d.close,
        })),
      );
    } else {
      const rising =
        sorted.length > 1 && sorted[sorted.length - 1][1].close >= sorted[0][1].close;
      const series = chart.addSeries(AreaSeries, {
        lineColor: rising ? "#22c55e" : "#ef4444",
        topColor: rising ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)",
        bottomColor: "rgba(0,0,0,0)",
        lineWidth: 2,
      });
      series.setData(sorted.map(([time, d]) => ({ time: time as Time, value: d.close })));
    }
    chart.timeScale().fitContent();

    if (onHover) {
      const lookup = new Map(sorted.map(([time, d]) => [time, d]));
      const handler = (param: MouseEventParams) => {
        const t = param.time;
        onHover(typeof t === "string" ? lookup.get(t) ?? null : null);
      };
      chart.subscribeCrosshairMove(handler);
      return () => {
        chart.unsubscribeCrosshairMove(handler);
        chart.remove();
      };
    }
    return () => chart.remove();
  }, [data, chartType, onHover]);

  return <div ref={containerRef} className="h-56 w-full" />;
}
