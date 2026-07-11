import { useEffect, useState } from 'react';
import { feature } from 'topojson-client';
import type { FeatureCollection, Geometry, Position } from 'geojson';
import type { Portfolio, StreamSnapshot } from '../lib/api';

const TOPO_URL = 'https://cdn.jsdelivr.net/npm/datamaps@0.5.10/src/js/data/kor.topo.json';

/* 한반도 남부 선형 투영: lon 124.5~131.0, lat 33.0~38.8 → 100×128 */
const project = ([lon, lat]: Position): [number, number] => [
  ((lon - 124.5) / 6.5) * 100,
  ((38.8 - lat) / 5.8) * 128,
];

function ringPath(ring: Position[]): string {
  return ring
    .map((pt, i) => {
      const [x, y] = project(pt);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join('') + 'Z';
}

function geomPath(geom: Geometry): string {
  if (geom.type === 'Polygon') return geom.coordinates.map(ringPath).join('');
  if (geom.type === 'MultiPolygon')
    return geom.coordinates.map((poly) => poly.map(ringPath).join('')).join('');
  return '';
}

const SITES = [
  { id: 'building-A', name: '실증단지 A', region: '부산', lon: 129.07, lat: 35.18, live: true },
  { id: 'building-B', name: '단지 B', region: '수도권', lon: 126.98, lat: 37.57, live: false },
  { id: 'building-C', name: '단지 C', region: '대전', lon: 127.38, lat: 36.35, live: false },
];

export default function MapPanel({
  portfolio, snap,
}: {
  portfolio: Portfolio | null;
  snap: StreamSnapshot | null;
}) {
  const [paths, setPaths] = useState<string[]>([]);
  const [topoErr, setTopoErr] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(TOPO_URL);
        if (!res.ok) throw new Error(String(res.status));
        const topo = await res.json();
        const objKey = Object.keys(topo.objects)[0];
        const fc = feature(topo, topo.objects[objKey]) as unknown as FeatureCollection;
        if (!alive) return;
        setPaths(fc.features.map((f) => geomPath(f.geometry)).filter(Boolean));
      } catch {
        if (alive) setTopoErr(true);
      }
    })();
    return () => { alive = false; };
  }, []);

  const drActive = snap?.dr_active ?? false;
  const outputs: Record<string, number> = {};
  snap?.buildings.forEach((b) => { outputs[b.id] = b.output_kw; });
  const socOf = (id: string) =>
    portfolio?.buildings.find((b) => b.building_id === id)?.current_soc;

  return (
    <div className="mapmod">
      <div className="map-canvas">
        {topoErr ? (
          <div className="map-offline">지형 데이터 오프라인</div>
        ) : (
          <svg viewBox="8 6 84 120">
            {paths.map((d, i) => (
              <path key={i} d={d} fill="var(--bg-2)" stroke="var(--line-1)" strokeWidth="0.25" />
            ))}
            {SITES.map((s) => {
              const [x, y] = project([s.lon, s.lat]);
              const firing = s.live ? drActive : drActive; // DR 시 전 사이트 대응
              const color = firing ? 'var(--crit)' : s.live ? 'var(--ok)' : 'var(--acc)';
              return (
                <g key={s.id}>
                  {s.live && (
                    <circle cx={x} cy={y} r="3" fill="none" stroke={color} strokeWidth="0.4" opacity="0.7">
                      <animate attributeName="r" values="2;5.5" dur="2s" repeatCount="indefinite" />
                      <animate attributeName="opacity" values="0.7;0" dur="2s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <circle cx={x} cy={y} r="1.7" fill={color} stroke="var(--bg-0)" strokeWidth="0.4" />
                  <text x={x + 3.2} y={y + 1} className="site-lb">{s.region}</text>
                </g>
              );
            })}
          </svg>
        )}
      </div>

      <div className="site-list">
        {SITES.map((s) => (
          <div key={s.id} className="site-row">
            <span className={`sdot ${drActive ? 'crit' : s.live ? 'ok' : 'acc'}`} />
            <span className="sname">{s.name}</span>
            <span className={`mode ${s.live ? 'live' : ''}`}>{s.live ? 'LIVE' : 'SIM'}</span>
            <span className="sval">
              {socOf(s.id) !== undefined ? `SOC ${Math.round(socOf(s.id)!)}%` : '—'}
            </span>
            <span className="sval out">
              {outputs[s.id] !== undefined ? `${outputs[s.id].toFixed(1)}kW` : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
