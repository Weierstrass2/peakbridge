import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import Card from '../components/common/Card';

const scheduleData = Array.from({ length: 24 }, (_, i) => {
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
  
  return {
    hour: i,
    rate,
    type,
  };
});

const scenarios = [
  { icon: '⚡', name: '일반 피크 감지', status: 'standby', description: '피크 시간대 감지 시 자동 대응' },
  { icon: '🌡️', name: '폭염 대응 모드', status: 'active', description: '고온 시 ESS 우선 방전' },
  { icon: '🔋', name: '심야 최적 충전', status: 'standby', description: '경부하 시간대 최대 충전' },
  { icon: '🏗️', name: '변압기 한계 감시', status: 'standby', description: '변압기 과부하 방지' },
  { icon: '🌐', name: 'VPP 수요반응 대기', status: 'standby', description: '전력거래소 신호 대기' },
];

const tradingStats = [
  { label: '오늘 충전량', value: '45.2 kWh' },
  { label: '충전 단가', value: '42.5원/kWh' },
  { label: '충전 비용', value: '₩1,921' },
  { label: '오늘 방전량', value: '38.1 kWh' },
  { label: '방전 절감', value: '147.0원/kWh' },
  { label: '방전 절감액', value: '₩5,600' },
  { label: '순 차익', value: '₩3,679', highlight: true },
  { label: '이번달 누적', value: '₩89,400' },
];

function KPICard({
  label,
  value,
  sub,
  accent = 'text-white',
  highlight,
  isHighlight = false,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  highlight?: boolean;
  isHighlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border bg-[#1E293B] p-5 ${
        isHighlight ? 'border-[#34D399]/40 shadow-[0_0_20px_rgba(52,211,153,0.15)]' : 'border-[#334155]'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8]">{label}</p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-[#94A3B8]">{sub}</p>}
    </div>
  );
}

function Badge({ type, label }: { type: 'normal' | 'high' | 'critical'; label: string }) {
  const colors = {
    normal: 'bg-[#34D399]/20 text-[#34D399]',
    high: 'bg-[#FBBF24]/20 text-[#FBBF24]',
    critical: 'bg-[#EF4444]/20 text-[#EF4444]',
  };
  
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors[type]}`}>
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: 'active' | 'standby' }) {
  const colors = status === 'active' 
    ? 'bg-[#34D399]/20 text-[#34D399]' 
    : 'bg-[#334155]/50 text-[#94A3B8]';
    
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors}`}>
      {status === 'active' ? '발동중' : '대기중'}
    </span>
  );
}

export default function EnergyTradingPage() {
  const currentHour = new Date().getHours();
  
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#F1F5F9]">에너지 거래 현황</h1>
        <p className="mt-1 text-sm text-[#94A3B8]">실시간 요금, AI 권고, 차익 실적을 확인하세요</p>
      </div>
      
      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KPICard
          label="현재 요금"
          value="42.5원/kWh"
          sub="경부하 • 다음 구간까지 266분"
          accent="text-[#3B82F6]"
        />
        <KPICard
          label="AI 권고"
          value="충전 권장"
          sub='"경부하 시간대, 충전 유리"'
          accent="text-[#34D399]"
          isHighlight={true}
        >
          <div className="mt-2">
            <Badge type="normal" label="normal" />
          </div>
        </KPICard>
        <KPICard
          label="오늘 차익"
          value="₩7,220"
          sub="충전비용 vs 방전절감 차이"
          accent="text-[#34D399]"
          isHighlight={true}
        />
        <KPICard
          label="VPP 예상 수익"
          value="₩340,000"
          sub="전력거래소 수요반응 기준"
          accent="text-[#F1F5F9]"
        />
      </div>
      
      {/* Schedule Chart */}
      <Card title="24시간 충방전 스케줄">
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={scheduleData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
              <XAxis 
                dataKey="hour" 
                stroke="#94A3B8" 
                tick={{ fontSize: 12 }}
                tickFormatter={(hour) => `${hour}시`}
              />
              <YAxis 
                stroke="#94A3B8" 
                tick={{ fontSize: 12 }}
                tickFormatter={(rate) => `${rate}원`}
              />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1E293B', border: '1px solid #334155', borderRadius: '8px' }}
                labelStyle={{ color: '#F1F5F9' }}
                formatter={(value: number) => [`${value}원/kWh`, '요금']}
                labelFormatter={(hour) => `${hour}시`}
              />
              <ReferenceLine x={currentHour} stroke="#FBBF24" strokeWidth={2} label={{ value: '현재', fill: '#FBBF24', position: 'top' }} />
              <Bar 
                dataKey="rate" 
                radius={[4, 4, 0, 0]}
                fill={(data) => {
                  if (data.type === 'light') return '#3B82F6';
                  if (data.type === 'medium') return '#FBBF24';
                  return '#EF4444';
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 flex items-center justify-center gap-6">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-[#3B82F6]" />
            <span className="text-xs text-[#94A3B8]">경부하 (충전)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-[#FBBF24]" />
            <span className="text-xs text-[#94A3B8]">중간부하 (대기)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-[#EF4444]" />
            <span className="text-xs text-[#94A3B8]">최대부하 (방전)</span>
          </div>
        </div>
      </Card>
      
      {/* Bottom Section */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left - Trading Stats */}
        <Card title="에너지 거래 실적">
          <div className="divide-y divide-[#334155]">
            {tradingStats.map((stat, index) => (
              <div key={index} className={`flex justify-between py-3 ${stat.highlight ? 'text-[#34D399]' : 'text-[#F1F5F9]'}`}>
                <span className="text-sm text-[#94A3B8]">{stat.label}</span>
                <span className={`text-sm font-semibold ${stat.highlight ? 'text-[#34D399]' : 'text-[#F1F5F9]'}`}>{stat.value}</span>
              </div>
            ))}
          </div>
        </Card>
        
        {/* Right - AI Scenarios */}
        <Card title="AI 시나리오 현황">
          <div className="space-y-3">
            {scenarios.map((scenario, index) => (
              <div key={index} className="flex items-start justify-between rounded-lg border border-[#334155] bg-[#0F172A] p-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{scenario.icon}</span>
                    <span className="font-medium text-[#F1F5F9]">{scenario.name}</span>
                  </div>
                  <p className="mt-1 text-xs text-[#94A3B8]">{scenario.description}</p>
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
