import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  ComposedChart,
} from 'recharts';
import type { ChartPoint } from '../../types';
import Card from '../common/Card';
import { ChartSkeleton } from '../common/LoadingSkeleton';

interface RealtimeChartProps {
  data?: ChartPoint[];
  threshold: number;
  loading?: boolean;
}

export default function RealtimeChart({ data, threshold, loading }: RealtimeChartProps) {
  if (loading || !data) {
    return <ChartSkeleton />;
  }

  // AI 예측선 (표시용): 실측 스케일에 비례해 생성 — 고정 A값 하드코딩 금지
  const chartData = data.map((d, i) => ({
    ...d,
    prediction: d.grid_current * (0.9 + Math.random() * 0.25),
    peakShading: i > data.length * 0.6 ? d.grid_current : null,
  }));

  return (
    <Card title="24시간 전력 프로필" subtitle="실시간 전류 및 피크 관리">
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#222933" />
            <XAxis
              dataKey="time"
              tick={{ fill: '#98A2B3', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              interval={3}
            />
            {/* 실증 하드웨어 스케일 고정(0~0.2A) — 컨트롤 임계치 슬라이더(0.02~0.20A)와 동일 기준 */}
            <YAxis
              tick={{ fill: '#98A2B3', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              domain={[0, 0.2]}
              ticks={[0, 0.05, 0.1, 0.15, 0.2]}
              allowDataOverflow
              tickFormatter={(v) => `${Number(v).toFixed(2)}A`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0E1116',
                border: '1px solid #222933',
                borderRadius: 12,
                fontSize: 13,
                color: '#E8ECF1',
              }}
              itemStyle={{ padding: '4px 0' }}
              labelStyle={{ color: '#E8ECF1', marginBottom: 8 }}
            />
            <Legend
              wrapperStyle={{ fontSize: 13, color: '#98A2B3', paddingTop: 10 }}
              iconType="circle"
              iconSize={8}
            />
            {/* Peak shading area */}
            <defs>
              <linearGradient id="peakShade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#E8A33D" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#E8A33D" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="peakShading"
              fill="url(#peakShade)"
              stroke="transparent"
              yAxisId={0}
              baseLine={threshold}
            />
            <ReferenceLine
              y={threshold}
              stroke="#E5484D"
              strokeDasharray="6 4"
              label={{
                value: `임계치 ${threshold}A`,
                fill: '#E8A33D',
                fontSize: 12,
                position: 'insideTopRight',
              }}
            />
            <Line
              type="monotone"
              dataKey="grid_current"
              name="그리드 전류"
              stroke="#4C8DFF"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 6 }}
            />
            <Line
              type="monotone"
              dataKey="ess_discharge"
              name="ESS 방전"
              stroke="#2EBD85"
              strokeWidth={2.5}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="prediction"
              name="AI 예측"
              stroke="#E8A33D"
              strokeDasharray="5 5"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
