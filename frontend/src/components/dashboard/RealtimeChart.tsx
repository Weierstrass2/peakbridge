import {
  LineChart,
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

  // Add AI prediction data (mock)
  const chartData = data.map((d, i) => ({
    ...d,
    prediction: Math.max(d.grid_current - 2 + (Math.random() * 4), 5),
    peakShading: i > data.length * 0.6 ? d.grid_current : null,
  }));

  return (
    <Card title="24시간 전력 프로필" subtitle="실시간 전류 및 피크 관리">
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="time"
              tick={{ fill: '#94A3B8', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              interval={3}
            />
            <YAxis
              tick={{ fill: '#94A3B8', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              domain={[0, 30]}
              tickFormatter={(v) => `${v}A`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1E293B',
                border: '1px solid #334155',
                borderRadius: 12,
                fontSize: 13,
                color: '#F1F5F9',
              }}
              itemStyle={{ padding: '4px 0' }}
              labelStyle={{ color: '#F1F5F9', marginBottom: 8 }}
            />
            <Legend
              wrapperStyle={{ fontSize: 13, color: '#94A3B8', paddingTop: 10 }}
              iconType="circle"
              iconSize={8}
            />
            {/* Peak shading area */}
            <defs>
              <linearGradient id="peakShade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#F97316" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#F97316" stopOpacity={0.05} />
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
              stroke="#EF4444"
              strokeDasharray="6 4"
              label={{
                value: `임계치 ${threshold}A`,
                fill: '#F97316',
                fontSize: 12,
                position: 'insideTopRight',
              }}
            />
            <Line
              type="monotone"
              dataKey="grid_current"
              name="그리드 전류"
              stroke="#3B82F6"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 6 }}
            />
            <Line
              type="monotone"
              dataKey="ess_discharge"
              name="ESS 방전"
              stroke="#34D399"
              strokeWidth={2.5}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="prediction"
              name="AI 예측"
              stroke="#F97316"
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
