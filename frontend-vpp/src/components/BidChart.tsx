import type { Bid, BidResultHour } from '../lib/api';

/** 입찰 곡선 차트 — 예상 MCP vs 입찰가 스텝, 물량 바, 낙찰 하이라이트 (SVG). */
export default function BidChart({
  mcp, bids, results,
}: {
  mcp: number[];
  bids: Bid[];
  results: BidResultHour[] | null;
}) {
  const W = 480, H = 132, PAD_T = 8, AXIS = 14, QH = 26;
  const priceH = H - PAD_T - AXIS - QH;
  const maxP = Math.max(250, ...mcp, ...bids.map((b) => b.price)) * 1.08;
  const maxQ = Math.max(100, ...bids.map((b) => b.qty_kw));
  const cw = W / 24;

  const py = (v: number) => PAD_T + priceH - (v / maxP) * priceH;
  const awardedByHour: Record<number, boolean> = {};
  results?.forEach((r) => { awardedByHour[r.hour] = r.awarded; });

  const stepPath = (vals: (number | null)[]) => {
    let d = '';
    vals.forEach((v, h) => {
      if (v === null) return;
      const x0 = h * cw, x1 = x0 + cw, y = py(v);
      d += d && vals[h - 1] !== null ? ` L${x0.toFixed(1)},${y.toFixed(1)}` : ` M${x0.toFixed(1)},${y.toFixed(1)}`;
      d += ` L${x1.toFixed(1)},${y.toFixed(1)}`;
    });
    return d;
  };

  const mcpPath = stepPath(mcp.map((v) => v ?? null));
  const bidPath = stepPath(bids.map((b) => (b.qty_kw > 0 ? b.price : null)));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="bidchart" preserveAspectRatio="none">
      {/* 낙찰 구간 배경 */}
      {results && bids.map((b) =>
        awardedByHour[b.hour] ? (
          <rect key={`a${b.hour}`} x={b.hour * cw} y={PAD_T} width={cw} height={priceH}
            fill="rgba(46,189,133,0.08)" />
        ) : null,
      )}
      {/* 그리드 */}
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1={0} x2={W} y1={PAD_T + priceH * f} y2={PAD_T + priceH * f}
          stroke="#161B22" strokeWidth="1" />
      ))}
      {/* 물량 바 */}
      {bids.map((b) => b.qty_kw > 0 && (
        <rect key={`q${b.hour}`}
          x={b.hour * cw + 1.5} width={cw - 3}
          y={H - AXIS - (b.qty_kw / maxQ) * QH}
          height={(b.qty_kw / maxQ) * QH}
          fill={results && awardedByHour[b.hour] ? 'rgba(46,189,133,0.55)' : 'rgba(76,141,255,0.35)'} />
      ))}
      {/* MCP / 입찰가 스텝 */}
      <path d={mcpPath} fill="none" stroke="#E8A33D" strokeWidth="1.4" />
      <path d={bidPath} fill="none" stroke="#4C8DFF" strokeWidth="1.4" strokeDasharray="4 2" />
      {/* 시간 라벨 */}
      {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
        <text key={h} x={h * cw + 2} y={H - 3} fontSize="7" fill="#5C6673"
          fontFamily="'JetBrains Mono', monospace">{String(h).padStart(2, '0')}</text>
      ))}
      {/* 가격 스케일 */}
      <text x={W - 2} y={PAD_T + 7} fontSize="7" fill="#5C6673" textAnchor="end"
        fontFamily="'JetBrains Mono', monospace">{Math.round(maxP)}₩</text>
    </svg>
  );
}
