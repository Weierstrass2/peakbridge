import { useEffect, useRef, useState } from 'react';
import {
  ColorType,
  createChart,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type UTCTimestamp,
} from 'lightweight-charts';
import { consoleApi, type StreamSnapshot } from '../lib/api';

/** 축 라벨을 KST로 표기하기 위한 타임스탬프 시프트 */
const kstNow = (): UTCTimestamp =>
  (Math.floor(Date.now() / 1000) + 9 * 3600) as UTCTimestamp;

const fmt = (n: number, d = 1) =>
  n.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });

interface SessionStats {
  hi: number; lo: number; sum: number; n: number;
}

export default function MarketPanel({ snap }: { snap: StreamSnapshot | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const smpRef = useRef<ISeriesApi<'Area'> | null>(null);
  const demandRef = useRef<ISeriesApi<'Line'> | null>(null);
  const forecastRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bandHiRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bandLoRef = useRef<ISeriesApi<'Line'> | null>(null);
  const seededRef = useRef(false);
  const wasDrRef = useRef(false);
  const markersRef = useRef<SeriesMarker<UTCTimestamp>[]>([]);
  const [stats, setStats] = useState<SessionStats | null>(null);

  // 차트 생성
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#0E1116' },
        textColor: '#5C6673',
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: '#161B22' },
        horzLines: { color: '#161B22' },
      },
      rightPriceScale: {
        borderColor: '#222933',
        scaleMargins: { top: 0.12, bottom: 0.08 },
      },
      leftPriceScale: {
        visible: true,
        borderColor: '#222933',
        scaleMargins: { top: 0.12, bottom: 0.08 },
      },
      timeScale: {
        borderColor: '#222933',
        timeVisible: true,
        secondsVisible: true,
        rightOffset: 4,
      },
      crosshair: {
        vertLine: { color: '#303947', labelBackgroundColor: '#1A2029' },
        horzLine: { color: '#303947', labelBackgroundColor: '#1A2029' },
      },
    });

    const smp = chart.addAreaSeries({
      lineColor: '#E8A33D',
      topColor: 'rgba(232,163,61,0.22)',
      bottomColor: 'rgba(232,163,61,0.0)',
      lineWidth: 2,
      priceScaleId: 'right',
      priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
    });
    const demand = chart.addLineSeries({
      color: '#4C8DFF',
      lineWidth: 1,
      priceScaleId: 'left',
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });
    const forecast = chart.addLineSeries({
      color: '#9B8AFB',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: 'left',
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });

    const bandOpts = {
      color: 'rgba(155,138,251,0.28)', lineWidth: 1 as const, lineStyle: LineStyle.Dotted,
      priceScaleId: 'left', priceLineVisible: false, lastValueVisible: false,
      crosshairMarkerVisible: false,
    };
    bandHiRef.current = chart.addLineSeries(bandOpts);
    bandLoRef.current = chart.addLineSeries(bandOpts);

    chartRef.current = chart;
    smpRef.current = smp;
    demandRef.current = demand;
    forecastRef.current = forecast;

    return () => {
      chart.remove();
      chartRef.current = null;
      seededRef.current = false;
    };
  }, []);

  // 스냅샷 반영
  useEffect(() => {
    if (!snap || !smpRef.current || !demandRef.current || !forecastRef.current) return;
    const t = kstNow();

    if (!seededRef.current) {
      seededRef.current = true;
      // 1순위: 서버 보관 히스토리로 시드 (새로고침 연속성)
      consoleApi.streamHistory().then(({ data }) => {
        if (data.points.length > 5 && smpRef.current && demandRef.current && forecastRef.current) {
          const base = (t as number) - data.points.length * 3;
          smpRef.current.setData(data.points.map((p, i) => ({ time: (base + i * 3) as UTCTimestamp, value: p.smp })));
          demandRef.current.setData(data.points.map((p, i) => ({ time: (base + i * 3) as UTCTimestamp, value: p.demand_kw })));
          forecastRef.current.setData(data.points.map((p, i) => ({ time: (base + i * 3) as UTCTimestamp, value: p.forecast_kw })));
        }
      }).catch(() => undefined);
      // 폴백: 합성 백필 (히스토리 부족 시 즉시 표시용)
      const smpSeed: { time: UTCTimestamp; value: number }[] = [];
      const dSeed: { time: UTCTimestamp; value: number }[] = [];
      const fSeed: { time: UTCTimestamp; value: number }[] = [];
      let s = snap.smp;
      let d = snap.demand_kw;
      for (let i = 60; i >= 1; i--) {
        const ts = (t - i * 3) as UTCTimestamp;
        s += (Math.random() - 0.5) * 0.8;
        d += (Math.random() - 0.5) * 3.5;
        smpSeed.push({ time: ts, value: +s.toFixed(1) });
        dSeed.push({ time: ts, value: +d.toFixed(1) });
        fSeed.push({ time: ts, value: +(d + 6 * Math.sin(i / 8)).toFixed(1) });
      }
      smpRef.current.setData(smpSeed);
      demandRef.current.setData(dSeed);
      forecastRef.current.setData(fSeed);
      const vals = smpSeed.map((p) => p.value);
      setStats({ hi: Math.max(...vals), lo: Math.min(...vals), sum: vals.reduce((a, b) => a + b, 0), n: vals.length });
    }

    smpRef.current.update({ time: t, value: snap.smp });
    demandRef.current.update({ time: t, value: snap.demand_kw });
    forecastRef.current.update({ time: t, value: snap.forecast_kw });
    if (snap.forecast_hi && bandHiRef.current) bandHiRef.current.update({ time: t, value: snap.forecast_hi });
    if (snap.forecast_lo && bandLoRef.current) bandLoRef.current.update({ time: t, value: snap.forecast_lo });

    setStats((prev) =>
      prev
        ? { hi: Math.max(prev.hi, snap.smp), lo: Math.min(prev.lo, snap.smp), sum: prev.sum + snap.smp, n: prev.n + 1 }
        : { hi: snap.smp, lo: snap.smp, sum: snap.smp, n: 1 },
    );

    // DR 발동 마커
    if (snap.dr_active && !wasDrRef.current) {
      markersRef.current = [
        ...markersRef.current.slice(-9),
        { time: t, position: 'aboveBar', color: '#E5484D', shape: 'arrowDown', text: 'DR', size: 1 },
      ];
      smpRef.current.setMarkers(markersRef.current);
    }
    wasDrRef.current = snap.dr_active;
  }, [snap]);

  const avg = stats ? stats.sum / stats.n : null;

  return (
    <div className="mkt-wrap">
      <div className="mkt-legend">
        <span className="key"><i style={{ background: '#E8A33D' }} />SMP <b>{snap ? fmt(snap.smp) : '—'}</b></span>
        <span className="key"><i style={{ background: '#4C8DFF' }} />수요 <b>{snap ? fmt(snap.demand_kw, 0) : '—'}</b></span>
        <span className="key"><i style={{ background: '#9B8AFB' }} />AI 예측 <b>{snap ? fmt(snap.forecast_kw, 0) : '—'}</b> <i style={{ background: 'none', color: 'var(--tx-3)', fontStyle: 'normal', fontSize: 8.5 }}>±3.5% CI</i></span>
        <span className="mkt-stats">
          H <b>{stats ? fmt(stats.hi) : '—'}</b>&ensp;L <b>{stats ? fmt(stats.lo) : '—'}</b>&ensp;AVG <b>{avg !== null ? fmt(avg) : '—'}</b>
        </span>
      </div>
      <div ref={containerRef} className="mkt-chart" />
    </div>
  );
}
