import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { useQuery } from '@tanstack/react-query';
import { mockReports, formatKRW } from '../mock/mockData';
import { fetchReports } from '../services/reportApi';
import { api } from '../services/api';
import { BUILDING_ID, isMockMode } from '../config/env';

// 예시 일별 절감 데이터 (오늘 기준 최근 30일, 실데이터 누적 전까지 표시용)
const fallbackDaily = Array.from({ length: 30 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() - (29 - i));
  return {
    day: `${d.getMonth() + 1}/${d.getDate()}`,
    savings: Math.floor(Math.random() * 50000) + 10000,
    peakCount: Math.floor(Math.random() * 5),
    isToday: i === 29,
  };
});

// 다중 단지 확장 예시 데이터 (전시용)
const buildingData = [
  { name: 'A단지', households: 500, savings: 64200000, peakCount: 156, rate: 32 },
  { name: 'B단지', households: 320, savings: 41088000, peakCount: 98, rate: 28 },
  { name: 'C단지', households: 180, savings: 23112000, peakCount: 54, rate: 25 },
];

export default function ReportPage() {
  const { data: reports } = useQuery({
    queryKey: ['reports'],
    queryFn: async () => {
      try {
        return await fetchReports();
      } catch {
        return mockReports;
      }
    },
    refetchInterval: 60_000,
  });

  // 일별 절감 실데이터 (백엔드 CSV export 파싱, 없으면 예시 폴백)
  const dailyQ = useQuery({
    queryKey: ['reports', 'daily'],
    queryFn: async () => {
      const res = await api.get<string>(`/api/v1/reports/${BUILDING_ID}/export`, {
        params: { days: 30 },
        responseType: 'text',
        transformResponse: [(d) => d],
      });
      const today = new Date().toISOString().slice(0, 10);
      return String(res.data)
        .trim()
        .split('\n')
        .slice(1)
        .filter(Boolean)
        .map((line) => {
          const [dateStr, , savedWon, , peakCount] = line.split(',');
          const dt = new Date(dateStr);
          return {
            day: `${dt.getMonth() + 1}/${dt.getDate()}`,
            savings: Math.round(parseFloat(savedWon) || 0),
            peakCount: parseInt(peakCount, 10) || 0,
            isToday: dateStr === today,
          };
        });
    },
    enabled: !isMockMode(),
    retry: false,
    refetchInterval: 60_000,
  });

  // 실데이터가 5일 이상 쌓이기 전엔 예시 프로파일 표시 (빈 차트 방지)
  const dailySavingsData = dailyQ.data && dailyQ.data.length >= 5 ? dailyQ.data : fallbackDaily;
  const monthSaved = reports?.[0]?.total_saved_won ?? 0;
  const annualProjection = monthSaved * 12;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">이번 달 절감</p>
            <p className="text-3xl font-bold text-[#FBBF24]">{(reports?.[0]?.total_saved_won ?? 0).toLocaleString()}원</p>
          </div>
        </Card>
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">피크쉐이빙 횟수</p>
            <p className="text-3xl font-bold text-[#3B82F6]">{reports?.[0]?.peak_events ?? 0}회</p>
          </div>
        </Card>
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">CO₂ 절감</p>
            <p className="text-3xl font-bold text-[#34D399]">{reports?.[0]?.co2_reduced_kg ?? 0}kg</p>
          </div>
        </Card>
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">연간 예상 절감</p>
            <p className="text-3xl font-bold text-[#A78BFA]">{annualProjection.toLocaleString()}원</p>
            <p className="mt-1 text-xs text-[#94A3B8]">이번 달 실적 × 12 기준</p>
          </div>
        </Card>
      </div>

      {/* Daily Savings Chart */}
      <Card title="일별 절감액" subtitle="최근 30일">
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dailySavingsData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fill: '#94A3B8', fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                interval={3}
              />
              <YAxis
                tick={{ fill: '#94A3B8', fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1E293B',
                  border: '1px solid #334155',
                  borderRadius: 12,
                  fontSize: 13,
                  color: '#F1F5F9',
                }}
                formatter={(value: number, name: string) => [
                  name === 'savings' ? `${formatKRW(value)}` : `${value}회`,
                  name === 'savings' ? '절감액' : '피크 횟수',
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 13, color: '#94A3B8' }} />
              <Bar dataKey="savings" name="절감액" radius={[8, 8, 0, 0]} barSize={30}>
                {dailySavingsData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.isToday ? '#FBBF24' : '#3B82F6'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Building Comparison + ROI Calculator */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Building Comparison Table */}
        <div className="lg:col-span-2">
          <Card title="단지별 비교" subtitle="다중 단지 확장 예시 (전시용 데이터)">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-[#334155]">
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">단지명</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">세대수</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">이번 달 절감</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">피크 횟수</th>
                    <th className="pb-4 text-xs font-semibold text-[#94A3B8]">절감률</th>
                  </tr>
                </thead>
                <tbody>
                  {buildingData.map((b) => (
                    <tr key={b.name} className="border-b border-[#334155]/50">
                      <td className="py-4 pr-4 font-medium text-[#F1F5F9]">{b.name}</td>
                      <td className="py-4 pr-4 text-[#94A3B8]">{b.households}</td>
                      <td className="py-4 pr-4 text-[#FBBF24] font-semibold">{b.savings.toLocaleString()}원</td>
                      <td className="py-4 pr-4 text-[#94A3B8]">{b.peakCount}회</td>
                      <td className="py-4">
                        <span className="rounded-full bg-[#10B981]/10 px-2.5 py-1 text-xs font-semibold text-[#10B981]">{b.rate}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* ROI Calculator */}
        <Card title="ROI 계산기" subtitle="투자 회수 기간">
          <div className="rounded-xl bg-[#0F172A] p-6 border border-[#334155]">
            <p className="text-sm text-[#94A3B8] mb-2">변압기 교체 비용</p>
            <p className="text-2xl font-bold text-[#F1F5F9] mb-6">3억원</p>
            <div className="border-t border-[#334155] pt-6">
              <p className="text-sm text-[#94A3B8] mb-2">PeakBridge 도입 시 회수 기간</p>
              <p className="text-3xl font-bold text-[#FBBF24]">2.3년</p>
            </div>
          </div>
          <div className="mt-6">
            <Button className="w-full">
              CSV 내보내기
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
