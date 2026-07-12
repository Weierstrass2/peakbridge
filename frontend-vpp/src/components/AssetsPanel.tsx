import { useEffect, useState } from 'react';
import { consoleApi, type GridMap, type Portfolio, type StreamSnapshot } from '../lib/api';

const NODE_COLOR: Record<string, string> = {
  '정상': 'var(--ok)', '경고': 'var(--warn)', '과부하': 'var(--crit)',
  '대기': 'var(--acc)', '미연결': 'var(--tx-3)',
};

const fmt = (n: number, d = 0) =>
  n.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });

/** 직교(엘보) 배선 경로 — 산업 도면 문법 */
function elbow(ax: number, ay: number, bx: number, by: number): string {
  const midY = (ay + by) / 2;
  return `M ${ax} ${ay} L ${ax} ${midY} L ${bx} ${midY} L ${bx} ${by}`;
}

export default function AssetsPanel({
  portfolio, snap,
}: {
  portfolio: Portfolio | null;
  snap: StreamSnapshot | null;
}) {
  const [map, setMap] = useState<GridMap | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const { data } = await consoleApi.gridMap();
        if (alive) setMap(data);
      } catch { /* noop */ }
    };
    load();
    const t = setInterval(load, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const drActive = snap?.dr_active ?? false;
  const activeUnits = Math.round(((snap?.discharge_percent ?? 0) / 100) * 20);
  const nodeById = (id: string) => map?.nodes.find((n) => n.id === id);
  const outputs: Record<string, number> = {};
  snap?.buildings.forEach((b) => { outputs[b.id] = b.output_kw; });

  return (
    <div className="assets">
      <div className="assets-left">
        <table className="dg">
          <thead>
            <tr>
              <th>SITE</th><th>MODE</th><th className="num">SOC</th>
              <th className="num">SOH</th><th className="num">PCS°C</th><th className="num">AVL kW</th><th className="num">OUT kW</th>
            </tr>
          </thead>
          <tbody>
            {(portfolio?.buildings ?? []).map((b) => (
              <tr key={b.building_id}>
                <td>{b.building_id.replace('building-', '단지 ')}</td>
                <td>
                  <span className={`mode ${b.live ? 'live' : ''}`}>{b.live ? 'LIVE' : 'SIM'}</span>
                </td>
                <td className="num">
                  <span className="socbar"><i style={{
                    width: `${Math.min(100, b.current_soc)}%`,
                    background: b.current_soc < 30 ? 'var(--warn)' : 'var(--ok)',
                  }} /></span>
                  {fmt(b.current_soc)}%
                </td>
                <td className="num" style={{ color: (b.soh ?? 100) < 95 ? 'var(--warn)' : 'var(--tx-2)' }}>
                  {b.soh !== undefined ? `${b.soh}%` : '—'}
                </td>
                <td className="num" style={{ color: (b.pcs_temp ?? 0) > 45 ? 'var(--crit)' : 'var(--tx-2)' }}>
                  {b.pcs_temp !== undefined ? fmt(b.pcs_temp, 1) : '—'}
                </td>
                <td className="num" style={{ color: 'var(--acc)' }}>{fmt(b.available_kw)}</td>
                <td className="num" style={{ color: drActive ? 'var(--crit)' : 'var(--tx-1)' }}>
                  {outputs[b.building_id] !== undefined ? fmt(outputs[b.building_id], 1) : '—'}
                </td>
              </tr>
            ))}
            {!portfolio && (
              <tr><td colSpan={6} style={{ color: 'var(--tx-3)' }}>피드 대기 중</td></tr>
            )}
          </tbody>
        </table>

        <div className="unit-sec">
          <div className="unit-cap">
            ESS UNITS — 실증단지 A
            <span style={{ color: drActive ? 'var(--crit)' : 'var(--tx-3)' }}>
              {drActive ? `방전 ${activeUnits}/20` : '대기 20/20'}
            </span>
          </div>
          <div className="unit-grid">
            {Array.from({ length: 20 }).map((_, i) => (
              <div
                key={i}
                className={`unit ${drActive && i < activeUnits ? 'firing' : ''}`}
                title={`UNIT-${String(i + 1).padStart(2, '0')}`}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="assets-right">
        <div className="oneline-cap">단선 계통도 — 실증단지 A</div>
        <svg viewBox="0 0 100 104" className="oneline">
          {map?.edges.map((e, i) => {
            const a = nodeById(e.from); const b = nodeById(e.to);
            if (!a || !b) return null;
            const essFlow = e.from === 'ess' && drActive;
            return (
              <path
                key={i}
                d={elbow(a.x, a.y, b.x, b.y)}
                fill="none"
                stroke={essFlow ? 'var(--crit)' : 'var(--line-2)'}
                strokeWidth={essFlow ? 0.7 : 0.45}
                className={essFlow ? 'flow' : ''}
              />
            );
          })}
          {map?.nodes.map((n) => {
            const c = NODE_COLOR[n.status] ?? 'var(--ok)';
            const isBus = n.id === 'transformer' || n.id === 'grid-source';
            return (
              <g key={n.id}>
                {isBus ? (
                  <rect x={n.x - 3.4} y={n.y - 2.4} width={6.8} height={4.8}
                    fill="var(--bg-2)" stroke={c} strokeWidth={0.55} />
                ) : (
                  <circle cx={n.x} cy={n.y} r={2.9}
                    fill="var(--bg-2)" stroke={c} strokeWidth={0.55}>
                    {n.id === 'ess' && drActive && (
                      <animate attributeName="r" values="2.9;3.6;2.9" dur="1.2s" repeatCount="indefinite" />
                    )}
                  </circle>
                )}
                <text x={n.x} y={n.y + 0.9} textAnchor="middle" className="nl-val" fill={c}>
                  {n.id === 'ess' ? `${fmt(n.soc ?? 0)}%`
                    : n.id === 'grid-source' ? 'GRID'
                    : `${fmt(n.load_percent)}%`}
                </text>
                <text x={n.x} y={n.y + 6.8} textAnchor="middle" className="nl-name">{n.name}</text>
              </g>
            );
          })}
          {!map && (
            <text x="50" y="52" textAnchor="middle" className="nl-name">계통 데이터 대기 중</text>
          )}
        </svg>
      </div>
    </div>
  );
}
