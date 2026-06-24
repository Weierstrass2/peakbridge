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

  return (
    <Card title="24-Hour Power Profile" subtitle="Grid, ESS discharge, and charger load">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a3140" />
            <XAxis
              dataKey="time"
              tick={{ fill: '#8b95a8', fontSize: 10 }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: '#8b95a8', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              domain={[0, 25]}
              tickFormatter={(v) => `${v}A`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1a1f26',
                border: '1px solid #2a3140',
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: '#e2e8f0' }}
              formatter={(value: number, name: string) => [`${value.toFixed(1)} A`, name]}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, color: '#8b95a8' }}
              iconType="circle"
              iconSize={8}
            />
            <ReferenceLine
              y={threshold}
              stroke="#f97316"
              strokeDasharray="6 4"
              label={{
                value: `Threshold ${threshold}A`,
                fill: '#fb923c',
                fontSize: 10,
                position: 'insideTopRight',
              }}
            />
            <Line
              type="monotone"
              dataKey="grid_current"
              name="Grid Current"
              stroke="#60a5fa"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="ess_discharge"
              name="ESS Discharge"
              stroke="#34d399"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="charger_total"
              name="Charger Total"
              stroke="#a78bfa"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
