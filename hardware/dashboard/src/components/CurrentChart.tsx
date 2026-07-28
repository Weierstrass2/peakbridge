import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { RelayEvent, Telemetry } from '../lib/api';
import { formatTime } from '../lib/api';

interface Props {
  history: Telemetry[];
  events: RelayEvent[];
  thresholdHigh: number;
  thresholdLow: number;
}

export function CurrentChart({ history, events, thresholdHigh, thresholdLow }: Props) {
  if (history.length === 0) {
    return <div className="empty">데이터 수신 대기 중…</div>;
  }

  const data = history.map((t) => ({
    t: t.received_at,
    label: formatTime(t.received_at),
    current: t.grid_current_a,
  }));

  const from = data[0].t;
  const to = data[data.length - 1].t;
  // 차트 구간 안에 들어오는 절체 이벤트만 세로 마커로 표시
  const marks = events.filter((e) => e.received_at >= from && e.received_at <= to);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid stroke="#232a35" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          scale="time"
          tickFormatter={(v: number) => formatTime(v)}
          stroke="#8b97a8"
          fontSize={11}
          minTickGap={50}
        />
        <YAxis
          stroke="#8b97a8"
          fontSize={11}
          width={62}
          domain={[0, (max: number) => Math.max(max * 1.2, thresholdHigh * 1.3)]}
          tickFormatter={(v: number) => v.toFixed(3)}
          unit="A"
        />
        <Tooltip
          contentStyle={{ background: '#12161d', border: '1px solid #232a35', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => formatTime(Number(v))}
          formatter={(v: number) => [`${v.toFixed(4)} A`, '계통 전류']}
        />

        {/* 임계선: I_high 주황 점선 / I_low 파랑 점선 */}
        <ReferenceLine
          y={thresholdHigh}
          stroke="#f59e0b"
          strokeDasharray="5 4"
          label={{ value: `I_high ${thresholdHigh}A`, fill: '#f59e0b', fontSize: 11, position: 'insideTopRight' }}
        />
        <ReferenceLine
          y={thresholdLow}
          stroke="#3b82f6"
          strokeDasharray="5 4"
          label={{ value: `I_low ${thresholdLow}A`, fill: '#3b82f6', fontSize: 11, position: 'insideBottomRight' }}
        />

        {/* 절체 순간 세로 마커 — 그래프에서 전환 시점이 보이게 */}
        {marks.map((e) => (
          <ReferenceLine
            key={e.id}
            x={e.received_at}
            stroke={e.to_state === 'NO' ? '#f59e0b' : '#3b82f6'}
            strokeWidth={1.5}
            strokeOpacity={0.75}
            label={{
              value: `${e.from_state}→${e.to_state}`,
              fill: e.to_state === 'NO' ? '#f59e0b' : '#3b82f6',
              fontSize: 10,
              position: 'top',
            }}
          />
        ))}

        <Line
          type="monotone"
          dataKey="current"
          stroke="#e6ebf2"
          strokeWidth={1.8}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
