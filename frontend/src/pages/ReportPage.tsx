import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';
import type { TooltipProps } from 'recharts';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { useQuery } from '@tanstack/react-query';
import { mockReports } from '../mock/mockData';
import { fetchReports } from '../services/reportApi';
import { api } from '../services/api';
import { BUILDING_ID, isMockMode } from '../config/env';
import { formatCo2Kg, formatWon } from '../utils/format';

// 예시 일별 절감 데이터 (오늘 기준 최근 30일, 실데이터 누적 전까지 표시용)
// 실측 스케일 정렬: 실제 하루 절감이 0.1~0.4원 수준(초과전류 0.02A × 220V × 5분
// × 피크단가 250원 × 피크 수 회)이므로 예시도 같은 자릿수로 생성한다.
// 아파트 스케일(만원대) 예시를 쓰면 실측 카드(0.19원)와 모순돼 신뢰를 깎는다.
const fallbackDaily = Array.from({ length: 30 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() - (29 - i));
  const peakCount = Math.floor(Math.random() * 6);
  return {
    day: `${d.getMonth() + 1}/${d.getDate()}`,
    savings: Number((peakCount * (0.03 + Math.random() * 0.04)).toFixed(3)),
    peakCount,
    isToday: i === 29,
  };
});

interface DailyPoint {
  day: string;
  savings: number;
  peakCount: number;
  isToday: boolean;
}

// 커스텀 툴팁 — recharts 기본 툴팁은 라벨이 검정색이라 어두운 배경에서 안 보이고,
// formatter의 name 인자는 dataKey가 아닌 표시명이라 분기가 어긋났었다.
function DailyTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload as DailyPoint;
  return (
    <div
      style={{
        backgroundColor: '#0E1116',
        border: '1px solid #222933',
        borderRadius: 12,
        padding: '10px 14px',
        fontSize: 13,
      }}
    >
      <p style={{ color: '#E8ECF1', fontWeight: 600, marginBottom: 6 }}>{label}</p>
      <p style={{ color: '#4C8DFF' }}>절감액 {formatWon(point.savings)}</p>
      <p style={{ color: '#E8A33D', marginTop: 2 }}>피크쉐이빙 {point.peakCount}회</p>
    </div>
  );
}

// ROI 시나리오 (보수 가정 — 결과값 하드코딩 금지, 아래 상수에서만 계산)
// 프레임: 노후 아파트가 EV 충전 부하로 변압기 용량 한계에 도달했을 때
//   대안 A) 변압기 증설·교체 공사  vs  대안 B) PeakBridge ESS 피크쉐이빙
// 보수 원칙: 도입비는 상한으로, 회피비는 통상 범위 하한으로, 요금 절감·보조금·
// VPP 수익은 계산에서 제외(업사이드로만 언급) — 숫자를 부풀릴 여지를 없앤다.
const ROI_ASSUMPTIONS = {
  transformerCostWon: 300_000_000, // 대안 A: 변압기 교체 + 정전 수반 공사 (통상 범위 하한)
  essCostWon: 180_000_000,         // 대안 B: 100kW/200kWh급 ESS 도입 상한 (설치 포함)
  maintenanceWonPerYear: 5_000_000, // ESS 유지보수 — 보수적으로 비용에 반영
  horizonYears: 10,                 // 배터리 보증 수명 내 비교 기간
};
const roiCapexSavePct = Math.round(
  (1 - ROI_ASSUMPTIONS.essCostWon / ROI_ASSUMPTIONS.transformerCostWon) * 100,
);
const roiTotalSaveWon =
  ROI_ASSUMPTIONS.transformerCostWon -
  (ROI_ASSUMPTIONS.essCostWon +
    ROI_ASSUMPTIONS.maintenanceWonPerYear * ROI_ASSUMPTIONS.horizonYears);

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
              <Tooltip content={<DailyTooltip />} cursor={{ fill: '#222933', opacity: 0.4 }} />
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
        <Card title="ROI 시나리오" subtitle="변압기 증설 대비 · 보수 가정">
          <div className="rounded-md bg-[#0A0C10] p-6 border border-[#222933] space-y-4">
            <div className="flex items-baseline justify-between">
              <p className="text-sm text-[#98A2B3]">대안 A · 변압기 교체 공사</p>
              <p className="text-lg font-bold text-[#E8ECF1]">
                {(ROI_ASSUMPTIONS.transformerCostWon / 100_000_000).toFixed(1)}억원
              </p>
            </div>
            <div className="flex items-baseline justify-between">
              <p className="text-sm text-[#98A2B3]">대안 B · ESS 도입 (상한)</p>
              <p className="text-lg font-bold text-[#E8ECF1]">
                {(ROI_ASSUMPTIONS.essCostWon / 100_000_000).toFixed(1)}억원
                <span className="ml-1 text-xs font-normal text-[#98A2B3]">
                  +유지 연 {(ROI_ASSUMPTIONS.maintenanceWonPerYear / 10_000).toLocaleString()}만원
                </span>
              </p>
            </div>
            <div className="border-t border-[#222933] pt-4">
              <p className="text-sm text-[#98A2B3] mb-1">초기 투자 절감 (즉시)</p>
              <p className="text-2xl font-bold text-[#E8A33D]">{roiCapexSavePct}%</p>
              <p className="mt-1 text-xs text-[#98A2B3]">
                {ROI_ASSUMPTIONS.horizonYears}년 유지보수 반영 순절감{' '}
                {(roiTotalSaveWon / 100_000_000).toFixed(1)}억원
              </p>
            </div>
            <p className="text-[11px] leading-relaxed text-[#5A6472]">
              보수 가정: 요금 절감·정부 보조금·VPP 수익 미반영 (전부 업사이드).
              실증이 검증하는 것은 감축 메커니즘(실측 절체 이력)이며, 금액은
              단지 규모·요금제에 따라 본 가정으로 재산출.
            </p>
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
