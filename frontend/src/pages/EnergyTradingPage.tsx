import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import Card from '../components/common/Card';
import { energyApi, unwrap } from '../services/energyApi';
import { BUILDING_ID, isMockMode } from '../config/env';

interface RateInfo {
  rate: number;
  period: string;
  season: string;
  next_period: string;
  next_period_in_minutes: number;
}

interface Recommendation {
  action: string;
  reason: string;
  urgency?: string;
  expected_benefit?: string;
  model?: string;
}

interface ArbitrageInfo {
  charge_cost?: number;
  discharge_savings?: number;
  arbitrage?: number;
  roi?: number;
}

interface ScheduleItem {
  time: string;
  rate: number;
  period: string;
  action?: string;
}

interface ScenarioItem {
  id: string;
  name: string;
  active: boolean;
  value?: number | string | null;
}

interface KepcoStatus {
  smp_price: number;
  smp_is_live?: boolean;
  smp_source?: 'api' | 'inject' | 'csv' | 'estimate';
  tariff_period: string;
  source: string;
}

/** SMP 출처를 짧은 배지 문구로 (구버전 백엔드는 smp_source가 없어 smp_is_live로 폴백) */
function smpSourceLabel(smp: KepcoStatus): string {
  const source = smp.smp_source ?? (smp.smp_is_live ? 'api' : 'estimate');
  if (source === 'api') return '전력거래소 실시간';
  if (source === 'inject') return 'KPX 확정가 (당일·자동 중계)';
  if (source === 'csv') return 'KPX 실데이터 (전일 확정가)';
  return '요금표 추정 (실데이터 미연동)';
}

type BarEntry = { hour: number; rate: number; type: 'light' | 'medium' | 'heavy' };

const fallbackSchedule: BarEntry[] = Array.from({ length: 24 }, (_, i) => {
  let type: 'light' | 'medium' | 'heavy';
  let rate: number;

  if (i >= 0 && i < 8) {
    type = 'light';
    rate = 42.5;
  } else if (i >= 8 && i < 11) {
    type = 'heavy';
    rate = 147.0;
  } else if (i >= 11 && i < 17) {
    type = 'medium';
    rate = 85.0;
  } else if (i >= 17 && i < 22) {
    type = 'heavy';
    rate = 147.0;
  } else {
    type = 'light';
    rate = 42.5;
  }

  return { hour: i, rate, type };
});

const SCENARIO_META: Record<string, { icon: string; description: string }> = {
  peak_detect: { icon: 'PEAK', description: '피크 시간대 감지 시 자동 대응' },
  heatwave: { icon: 'TEMP', description: '고온 시 ESS 우선 방전' },
  night_charge: { icon: 'CHG', description: '경부하 시간대 최대 충전' },
  transformer_guard: { icon: 'TR', description: '변압기 과부하 방지' },
  vpp_dr: { icon: 'VPP', description: '전력거래소 신호 대기' },
};

const fallbackScenarios = [
  { icon: 'PEAK', name: '일반 피크 감지', status: 'standby' as const, description: '피크 시간대 감지 시 자동 대응' },
  { icon: 'TEMP', name: '폭염 대응 모드', status: 'standby' as const, description: '고온 시 ESS 우선 방전' },
  { icon: 'CHG', name: '심야 최적 충전', status: 'standby' as const, description: '경부하 시간대 최대 충전' },
  { icon: 'TR', name: '변압기 한계 감시', status: 'standby' as const, description: '변압기 과부하 방지' },
  { icon: 'VPP', name: 'VPP 수요반응 대기', status: 'standby' as const, description: '전력거래소 신호 대기' },
];

function periodToType(period: string): 'light' | 'medium' | 'heavy' {
  if (period === '경부하') return 'light';
  if (period === '중간부하') return 'medium';
  return 'heavy';
}

const ACTION_LABEL: Record<string, string> = {
  charge: '충전 권장',
  discharge: '방전 권장',
  standby: '대기',
};

function KPICard({
  label,
  value,
  sub,
  accent = 'text-white',
  isHighlight = false,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  isHighlight?: boolean;
}) {
  return (
    <div
      className={`rounded-md border bg-[#0E1116] p-5 ${
        isHighlight ? 'border-[#2EBD85]/50 bg-[#2EBD85]/[0.06]' : 'border-[#222933]'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">{label}</p>
      <p className={`mt-2 text-2xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-[#98A2B3]">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status }: { status: 'active' | 'standby' }) {
  const colors = status === 'active'
    ? 'bg-[#2EBD85]/20 text-[#2EBD85]'
    : 'bg-[#222933]/50 text-[#98A2B3]';

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors}`}>
      {status === 'active' ? '발동중' : '대기중'}
    </span>
  );
}

export default function EnergyTradingPage() {
  const currentHour = new Date().getHours();
  const live = !isMockMode();

  const rateQ = useQuery({
    queryKey: ['energy', 'rate'],
    queryFn: async () => unwrap<RateInfo>((await energyApi.getCurrentRate()).data),
    enabled: live,
    retry: false,
    refetchInterval: 60_000,
  });

  const recQ = useQuery({
    queryKey: ['energy', 'recommend'],
    queryFn: async () => {
      try {
        return unwrap<Recommendation>((await energyApi.getAiRecommend(BUILDING_ID)).data);
      } catch {
        return unwrap<Recommendation>((await energyApi.getRecommendation(BUILDING_ID)).data);
      }
    },
    enabled: live,
    retry: false,
    refetchInterval: 30_000,
  });

  const arbQ = useQuery({
    queryKey: ['energy', 'arbitrage'],
    queryFn: async () => unwrap<ArbitrageInfo>((await energyApi.getArbitrage(BUILDING_ID)).data),
    enabled: live,
    retry: false,
    refetchInterval: 60_000,
  });

  const schedQ = useQuery({
    queryKey: ['energy', 'schedule'],
    queryFn: async () => {
      const raw = unwrap<{ schedule?: ScheduleItem[] }>((await energyApi.getSchedule(BUILDING_ID)).data);
      return raw.schedule ?? [];
    },
    enabled: live,
    retry: false,
    refetchInterval: 300_000,
  });

  const scenQ = useQuery({
    queryKey: ['energy', 'scenarios'],
    queryFn: async () => unwrap<ScenarioItem[]>((await energyApi.getAiScenarios(BUILDING_ID)).data),
    enabled: live,
    retry: false,
    refetchInterval: 30_000,
  });

  const smpQ = useQuery({
    queryKey: ['energy', 'smp'],
    queryFn: async () => unwrap<KepcoStatus>((await energyApi.getKepcoStatus()).data),
    enabled: live,
    retry: false,
    refetchInterval: 60_000,
  });

  const rate = rateQ.data;
  const rec = recQ.data;
  const arb = arbQ.data;
  const smp = smpQ.data;

  const scheduleData: BarEntry[] =
    schedQ.data && schedQ.data.length > 0
      ? schedQ.data
          .filter((item) => new Date(item.time).getMinutes() === 0)
          .slice(0, 24)
          .map((item) => ({
            hour: new Date(item.time).getHours(),
            rate: item.rate,
            type: periodToType(item.period),
          }))
      : fallbackSchedule;

  const scenarios =
    scenQ.data && scenQ.data.length > 0
      ? scenQ.data.map((s) => ({
          icon: SCENARIO_META[s.id]?.icon ?? 'AI',
          name: s.name,
          status: (s.active ? 'active' : 'standby') as 'active' | 'standby',
          description: SCENARIO_META[s.id]?.description ?? '',
        }))
      : fallbackScenarios;

  const tradingStats = arb
    ? [
        { label: '충전 비용', value: `₩${Math.round(arb.charge_cost ?? 0).toLocaleString()}` },
        { label: '방전 절감액', value: `₩${Math.round(arb.discharge_savings ?? 0).toLocaleString()}` },
        { label: '순 차익', value: `₩${Math.round(arb.arbitrage ?? 0).toLocaleString()}`, highlight: true },
        { label: 'ROI', value: `${(arb.roi ?? 0).toFixed(1)}%` },
      ]
    : [
        { label: '오늘 충전량', value: '45.2 kWh' },
        { label: '충전 단가', value: '42.5원/kWh' },
        { label: '충전 비용', value: '₩1,921' },
        { label: '오늘 방전량', value: '38.1 kWh' },
        { label: '방전 절감', value: '147.0원/kWh' },
        { label: '방전 절감액', value: '₩5,600' },
        { label: '순 차익', value: '₩3,679', highlight: true },
        { label: '이번달 누적', value: '₩89,400' },
      ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#E8ECF1]">에너지 거래 현황</h1>
        <p className="mt-1 text-sm text-[#98A2B3]">실시간 요금, AI 권고, 차익 실적을 확인하세요</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <KPICard
          label="SMP (시장가)"
          value={smp ? `${smp.smp_price.toFixed(1)}원/kWh` : '연결 대기'}
          sub={smp ? smpSourceLabel(smp) : 'KPX 전날 결정가'}
          accent="text-[#9B8AFB]"
        />
        <KPICard
          label="현재 요금"
          value={rate ? `${rate.rate}원/kWh` : '42.5원/kWh'}
          sub={rate ? `${rate.period} • 다음 구간까지 ${rate.next_period_in_minutes}분` : '요금표 기준 (연결 대기)'}
          accent="text-[#4C8DFF]"
        />
        <KPICard
          label={rec?.model ? `AI 권고 (${rec.model})` : 'AI 권고'}
          value={rec ? (ACTION_LABEL[rec.action] ?? rec.action) : '충전 권장'}
          sub={rec ? rec.reason : '"경부하 시간대, 충전 유리"'}
          accent="text-[#2EBD85]"
          isHighlight={true}
        />
        <KPICard
          label="오늘 차익"
          value={arb ? `₩${Math.round(arb.arbitrage ?? 0).toLocaleString()}` : '₩7,220'}
          sub="충전비용 vs 방전절감 차이"
          accent="text-[#2EBD85]"
          isHighlight={true}
        />
        <KPICard
          label="VPP 예상 수익"
          value="₩340,000"
          sub="전력거래소 수요반응 기준"
          accent="text-[#E8ECF1]"
        />
      </div>

      {/* Schedule Chart */}
      <Card title="24시간 충방전 스케줄">
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={scheduleData} margin={{ top: 28, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222933" vertical={false} />
              <XAxis
                dataKey="hour"
                stroke="#98A2B3"
                tick={{ fontSize: 12 }}
                tickFormatter={(hour) => `${hour}시`}
              />
              <YAxis
                stroke="#98A2B3"
                tick={{ fontSize: 12 }}
                tickFormatter={(r) => `${r}원`}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#0E1116', border: '1px solid #222933', borderRadius: '8px' }}
                labelStyle={{ color: '#E8ECF1' }}
                formatter={(value: number) => [`${value}원/kWh`, '요금']}
                labelFormatter={(hour) => `${hour}시`}
              />
              <ReferenceLine x={currentHour} stroke="#E8A33D" strokeWidth={2} label={{ value: '현재', fill: '#E8A33D', position: 'top' }} />
              <Bar dataKey="rate" radius={[4, 4, 0, 0]}>
                {scheduleData.map((entry) => (
                  <Cell
                    key={entry.hour}
                    fill={
                      entry.type === 'light'
                        ? '#4C8DFF'
                        : entry.type === 'medium'
                          ? '#E8A33D'
                          : '#E5484D'
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 flex items-center justify-center gap-6">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-[#4C8DFF]" />
            <span className="text-xs text-[#98A2B3]">경부하 (충전)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-[#E8A33D]" />
            <span className="text-xs text-[#98A2B3]">중간부하 (대기)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-[#E5484D]" />
            <span className="text-xs text-[#98A2B3]">최대부하 (방전)</span>
          </div>
        </div>
      </Card>

      {/* Bottom Section */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left - Trading Stats */}
        <Card title="에너지 거래 실적" subtitle={arb ? '실시간 계산' : '예시 데이터'}>
          <div className="divide-y divide-[#222933]">
            {tradingStats.map((stat, index) => (
              <div key={index} className={`flex justify-between py-3 ${stat.highlight ? 'text-[#2EBD85]' : 'text-[#E8ECF1]'}`}>
                <span className="text-sm text-[#98A2B3]">{stat.label}</span>
                <span className={`text-sm font-semibold ${stat.highlight ? 'text-[#2EBD85]' : 'text-[#E8ECF1]'}`}>{stat.value}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Right - AI Scenarios */}
        <Card title="AI 시나리오 현황" subtitle={scenQ.data ? '실시간 상태' : '연결 대기'}>
          <div className="space-y-3">
            {scenarios.map((scenario, index) => (
              <div key={index} className="flex items-start justify-between rounded-md border border-[#222933] bg-[#0A0C10] p-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="num rounded-sm border border-[#222933] bg-[#13171E] px-1.5 py-0.5 text-[10px] tracking-wider text-[#98A2B3]">{scenario.icon}</span>
                    <span className="font-medium text-[#E8ECF1]">{scenario.name}</span>
                  </div>
                  <p className="mt-1 text-xs text-[#98A2B3]">{scenario.description}</p>
                </div>
                <StatusBadge status={scenario.status} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
