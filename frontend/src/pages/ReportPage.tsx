import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { useQuery } from '@tanstack/react-query';
import { mockReports, formatKRW } from '../mock/mockData';
import { fetchReports } from '../services/reportApi';
import { api } from '../services/api';
import { BUILDING_ID, isMockMode } from '../config/env';
import { formatCo2Kg, formatWon } from '../utils/format';

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
            // 실측 스케일 절감액은 1원 미만 소수 — 반올림하면 전부 0으로 소실된다
            savings: Number((parseFloat(savedWon) || 0).toFixed(3)),
            peakCount: parseInt(peakCount, 10) || 0,
            isToday: dateStr === today,
          };
        });
    },
    enabled: !isMockMode(),
    retry: false,
    refetchInterval: 60_000,
  });

  // 실데이터가 5일 이상 쌓이기 전엔 예시 프로파일 표시 (빈 차트 방지).
  // 백엔드 CSV는 값 0인 날도 행으로 주므로 "행 수"가 아니라 "절감액>0인 날 수"로 판정.
  const realDayCount = dailyQ.data?.filter((d) => d.savings > 0).length ?? 0;
  const usingRealDaily = !!dailyQ.data && realDayCount >= 5;
  const dailySavingsData = usingRealDaily ? dailyQ.data! : fallbackDaily;
  const monthSaved = reports?.[0]?.total_saved_won ?? 0;
  const annualProjection = monthSaved * 12;

  // y축 단위: 실측 스케일(1원 미만)부터 아파트 스케일(만원대)까지 자동 대응
  const yTickWon = (v: number) =>
    v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${Number(v.toFixed(2))}원`;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">이번 달 절감</p>
            <p className="text-2xl font-bold text-[#E8A33D]">{formatWon(reports?.[0]?.total_saved_won)}</p>
          </div>
        </Card>
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">피크쉐이빙 횟수</p>
            <p className="text-2xl font-bold text-[#4C8DFF]">{reports?.[0]?.peak_events ?? 0}회</p>
          </div>
        </Card>
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">CO₂ 절감</p>
            <p className="text-2xl font-bold text-[#2EBD85]">{formatCo2Kg(reports?.[0]?.co2_reduced_kg)}</p>
          </div>
        </Card>
        <Card padding={false}>
          <div className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">연간 예상 절감</p>
            <p className="text-2xl font-bold text-[#9B8AFB]">{formatWon(annualProjection)}</p>
            <p className="mt-1 text-xs text-[#98A2B3]">이번 달 실적 × 12 기준</p>
          </div>
        </Card>
      </div>

      {/* Daily Savings Chart */}
      <Card
        title="일별 절감액"
        subtitle={
          usingRealDaily
            ? '최근 30일 (실데이터)'
            : '최근 30일 — 예시 프로파일 (실데이터 5일 이상 축적 시 자동 전환)'
        }
      >
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dailySavingsData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222933" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fill: '#98A2B3', fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                interval={3}
              />
              <YAxis
                tick={{ fill: '#98A2B3', fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={yTickWon}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0E1116',
                  border: '1px solid #222933',
                  borderRadius: 12,
                  fontSize: 13,
                  color: '#E8ECF1',
                }}
                formatter={(value: number, name: string) => [
                  name === 'savings' ? `${formatKRW(value)}` : `${value}회`,
                  name === 'savings' ? '절감액' : '피크 횟수',
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 13, color: '#98A2B3' }} />
              <Bar dataKey="savings" name="절감액" radius={[8, 8, 0, 0]} barSize={30}>
                {dailySavingsData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.isToday ? '#E8A33D' : '#4C8DFF'} />
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
                  <tr className="border-b border-[#222933]">
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#98A2B3]">단지명</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#98A2B3]">세대수</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#98A2B3]">이번 달 절감</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#98A2B3]">피크 횟수</th>
                    <th className="pb-4 text-xs font-semibold text-[#98A2B3]">절감률</th>
                  </tr>
                </thead>
                <tbody>
                  {buildingData.map((b) => (
                    <tr key={b.name} className="border-b border-[#222933]/50">
                      <td className="py-4 pr-4 font-medium text-[#E8ECF1]">{b.name}</td>
                      <td className="py-4 pr-4 text-[#98A2B3]">{b.households}</td>
                      <td className="py-4 pr-4 text-[#E8A33D] font-semibold">{b.savings.toLocaleString()}원</td>
                      <td className="py-4 pr-4 text-[#98A2B3]">{b.peakCount}회</td>
                      <td className="py-4">
                        <span className="rounded-full bg-[#2EBD85]/10 px-2.5 py-1 text-xs font-semibold text-[#2EBD85]">{b.rate}%</span>
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
          <div className="rounded-md bg-[#0A0C10] p-6 border border-[#222933]">
            <p className="text-sm text-[#98A2B3] mb-2">변압기 교체 비용</p>
            <p className="text-2xl font-bold text-[#E8ECF1] mb-6">3억원</p>
            <div className="border-t border-[#222933] pt-6">
              <p className="text-sm text-[#98A2B3] mb-2">PeakBridge 도입 시 회수 기간</p>
              <p className="text-2xl font-bold text-[#E8A33D]">2.3년</p>
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
