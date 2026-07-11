import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { vppApi, type VppBuilding } from '../services/vppApi';
import { isMockMode } from '../config/env';

const fallbackPortfolio = {
  total_capacity_kwh: 450,
  available_flexibility_kw: 135,
  building_count: 3,
  note: '연결 대기 (예시)',
  buildings: [
    { building_id: 'building-A', ess_capacity: 100, current_soc: 25, usable_kwh: 5, available_kw: 5, live: true },
    { building_id: 'building-B', ess_capacity: 200, current_soc: 72, usable_kwh: 104, available_kw: 50 },
    { building_id: 'building-C', ess_capacity: 150, current_soc: 85, usable_kwh: 97.5, available_kw: 80 },
  ] as VppBuilding[],
};

function KPI({ label, value, sub, accent = 'text-[#F1F5F9]' }: {
  label: string; value: string; sub?: string; accent?: string;
}) {
  return (
    <div className="rounded-xl border border-[#334155] bg-[#1E293B] p-5">
      <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8]">{label}</p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-[#94A3B8]">{sub}</p>}
    </div>
  );
}

function SocBar({ soc }: { soc: number }) {
  const color = soc < 30 ? 'bg-[#EF4444]' : soc < 60 ? 'bg-[#FBBF24]' : 'bg-[#34D399]';
  return (
    <div className="w-full bg-[#334155] rounded-full h-2">
      <div className={`h-2 rounded-full transition-all duration-700 ${color}`} style={{ width: `${Math.min(100, soc)}%` }} />
    </div>
  );
}

export default function VPPPage() {
  const live = !isMockMode();
  const qc = useQueryClient();
  const [lastResult, setLastResult] = useState<string | null>(null);

  const portfolioQ = useQuery({
    queryKey: ['vpp', 'portfolio'],
    queryFn: vppApi.getPortfolio,
    enabled: live, retry: false, refetchInterval: 15_000,
  });
  const drRevQ = useQuery({
    queryKey: ['vpp', 'dr-revenue'],
    queryFn: vppApi.getDrRevenue,
    enabled: live, retry: false, refetchInterval: 30_000,
  });
  const arbQ = useQuery({
    queryKey: ['vpp', 'arbitrage'],
    queryFn: vppApi.getArbitrage,
    enabled: live, retry: false, refetchInterval: 60_000,
  });
  const statusQ = useQuery({
    queryKey: ['vpp', 'dr-status'],
    queryFn: vppApi.getDrStatus,
    enabled: live, retry: false, refetchInterval: 10_000,
  });
  const historyQ = useQuery({
    queryKey: ['vpp', 'dr-history'],
    queryFn: vppApi.getDrHistory,
    enabled: live, retry: false, refetchInterval: 10_000,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['vpp'] });
  };

  const drMutation = useMutation({
    mutationFn: ({ type, value }: { type: string; value: number }) =>
      vppApi.issueDrEvent(type, value),
    onSuccess: (ev) => {
      setLastResult(`✅ ${ev.label} — 이벤트 ${ev.event_id}, VEN 대응: ${ev.action}`);
      refresh();
    },
    onError: () => setLastResult('❌ 이벤트 발령 실패 (백엔드 연결 확인)'),
  });

  const scenarioMutation = useMutation({
    mutationFn: (scenario: string) => vppApi.triggerScenario(scenario),
    onSuccess: (r) => {
      setLastResult(`✅ ${r.message}`);
      refresh();
    },
    onError: () => setLastResult('❌ 시나리오 실행 실패 (백엔드 연결 확인)'),
  });

  const p = portfolioQ.data ?? fallbackPortfolio;
  const drRev = drRevQ.data;
  const arb = arbQ.data;
  const venState = statusQ.data?.ven.state ?? 'idle';
  const activeEvent = statusQ.data?.active_event ?? null;
  const events = historyQ.data?.events ?? [];
  const busy = drMutation.isPending || scenarioMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold text-[#F1F5F9]">VPP 통합 관제</h1>
          <p className="mt-1 text-sm text-[#94A3B8]">
            가상발전소 포트폴리오 · OpenADR 수요반응 · 수익 현황
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/control-room"
            className="rounded-lg bg-[#3B82F6] px-4 py-2 text-sm font-semibold text-white hover:bg-[#2563EB]"
          >
            🖥 관제센터 모드
          </Link>
          <span className={`h-2.5 w-2.5 rounded-full ${venState === 'responding' ? 'bg-[#F97316] animate-pulse' : 'bg-[#34D399]'}`} />
          <span className="text-sm text-[#94A3B8]">
            VEN {venState === 'responding' ? '대응 중' : '대기'} · VTN 온라인
          </span>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KPI label="총 ESS 용량" value={`${p.total_capacity_kwh.toLocaleString()} kWh`} sub={`${p.building_count}개 단지 통합`} />
        <KPI label="가용 유연성" value={`${p.available_flexibility_kw.toLocaleString()} kW`} sub="전력거래소 입찰 가능량" accent="text-[#3B82F6]" />
        <KPI
          label="DR 1회 순수익"
          value={drRev ? `₩${Math.round(drRev.net_revenue).toLocaleString()}` : '₩—'}
          sub={drRev ? `SMP ${drRev.smp_price}원 × ${drRev.reduction_kwh}kWh` : '연결 대기'}
          accent="text-[#34D399]"
        />
        <KPI
          label="월 예상 수익"
          value={
            drRev || arb
              ? `₩${Math.round((drRev?.monthly_projection ?? 0) + (arb?.monthly_projection ?? 0)).toLocaleString()}`
              : '₩—'
          }
          sub="수요반응 + 차익거래 합산"
          accent="text-[#FBBF24]"
        />
      </div>

      {/* Portfolio */}
      <Card title="단지 포트폴리오" subtitle={p.note ?? ''}>
        <div className="grid gap-4 md:grid-cols-3">
          {p.buildings.map((b) => (
            <div key={b.building_id} className="rounded-xl border border-[#334155] bg-[#0F172A] p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-[#F1F5F9]">{b.building_id}</p>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  b.live ? 'bg-[#34D399]/15 text-[#34D399]' : 'bg-[#3B82F6]/15 text-[#3B82F6]'
                }`}>
                  {b.live ? 'LIVE 실측' : '시뮬레이션'}
                </span>
              </div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-[#94A3B8]">SOC</span>
                <span className="font-semibold text-[#F1F5F9] tabular-nums">{b.current_soc}%</span>
              </div>
              <SocBar soc={b.current_soc} />
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                <div>
                  <p className="text-xs text-[#94A3B8]">용량</p>
                  <p className="font-semibold text-[#F1F5F9] tabular-nums">{b.ess_capacity} kWh</p>
                </div>
                <div>
                  <p className="text-xs text-[#94A3B8]">가용 출력</p>
                  <p className="font-semibold text-[#3B82F6] tabular-nums">{b.available_kw} kW</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Control + Revenue */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="VTN 수요반응 발령" subtitle="OpenADR 2.0b 신호 체계">
          <div className="grid grid-cols-2 gap-3">
            <Button variant="secondary" disabled={busy} onClick={() => drMutation.mutate({ type: 'SIMPLE', value: 1 })}>
              SIMPLE 1 · 30% 방전
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => drMutation.mutate({ type: 'SIMPLE', value: 2 })}>
              SIMPLE 2 · 70% 방전
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => drMutation.mutate({ type: 'SIMPLE', value: 3 })}>
              SIMPLE 3 · 긴급 100%
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => drMutation.mutate({ type: 'SIMPLE', value: 0 })}>
              해제 · 대기 복귀
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => drMutation.mutate({ type: 'PRICE', value: 210 })}>
              고가격 210원 · 방전
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => drMutation.mutate({ type: 'PRICE', value: 50 })}>
              저가격 50원 · 충전
            </Button>
          </div>

          <div className="mt-4 border-t border-[#334155] pt-4">
            <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-3">발표 시연 시나리오</p>
            <div className="grid grid-cols-2 gap-3">
              <Button disabled={busy} onClick={() => scenarioMutation.mutate('peak_discharge')}>
                ⚡ 피크 방전 시연
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => scenarioMutation.mutate('midnight_charge')}>
                🌙 심야 충전 시연
              </Button>
            </div>
          </div>

          {lastResult && (
            <div className="mt-4 rounded-lg border border-[#334155] bg-[#0F172A] px-4 py-3 text-sm text-[#F1F5F9]">
              {lastResult}
            </div>
          )}
          {activeEvent && (
            <div className="mt-3 rounded-lg border border-[#F97316]/40 bg-[#F97316]/10 px-4 py-3 text-sm text-[#F97316]">
              활성 이벤트: {activeEvent.label} ({activeEvent.event_id})
            </div>
          )}
        </Card>

        <Card title="수익 현황" subtitle="수요반응 · 차익거래">
          <div className="divide-y divide-[#334155]">
            <div className="pb-3">
              <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">수요반응 (DR)</p>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-[#94A3B8]">감축량</span><span className="text-[#F1F5F9] font-semibold">{drRev ? `${drRev.reduction_kwh} kWh` : '—'}</span></div>
                <div className="flex justify-between"><span className="text-[#94A3B8]">총수익</span><span className="text-[#F1F5F9] font-semibold">{drRev ? `₩${Math.round(drRev.gross_revenue).toLocaleString()}` : '—'}</span></div>
                <div className="flex justify-between"><span className="text-[#94A3B8]">플랫폼 수수료 (15%)</span><span className="text-[#94A3B8]">{drRev ? `-₩${Math.round(drRev.peakbridge_fee).toLocaleString()}` : '—'}</span></div>
                <div className="flex justify-between"><span className="text-[#94A3B8]">월 환산</span><span className="text-[#34D399] font-bold">{drRev ? `₩${Math.round(drRev.monthly_projection).toLocaleString()}` : '—'}</span></div>
              </div>
            </div>
            <div className="pt-3">
              <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">차익거래 (경부하 충전 → 최대부하 방전)</p>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-[#94A3B8]">단가 차이</span><span className="text-[#F1F5F9] font-semibold">{arb ? `${arb.charge_price ?? 42.5} → ${arb.discharge_price ?? 147}원/kWh` : '—'}</span></div>
                <div className="flex justify-between"><span className="text-[#94A3B8]">1일 차익</span><span className="text-[#F1F5F9] font-semibold">{arb ? `₩${Math.round(arb.arbitrage).toLocaleString()}` : '—'}</span></div>
                <div className="flex justify-between"><span className="text-[#94A3B8]">ROI</span><span className="text-[#F1F5F9] font-semibold">{arb ? `${arb.roi_percent}%` : '—'}</span></div>
                <div className="flex justify-between"><span className="text-[#94A3B8]">월 환산</span><span className="text-[#34D399] font-bold">{arb ? `₩${Math.round(arb.monthly_projection).toLocaleString()}` : '—'}</span></div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Event history */}
      <Card title="수요반응 이벤트 이력" subtitle="최근 발령 기록">
        {events.length === 0 ? (
          <p className="text-sm text-[#94A3B8]">아직 발령된 이벤트가 없습니다. 위 버튼으로 발령해보세요.</p>
        ) : (
          <div className="space-y-2">
            {events.map((ev) => (
              <div key={ev.event_id} className="flex items-center justify-between rounded-lg border border-[#334155] bg-[#0F172A] px-4 py-2.5 text-sm">
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold shrink-0 ${
                    ev.action === 'discharge' ? 'bg-[#F97316]/15 text-[#F97316]'
                    : ev.action === 'charge' ? 'bg-[#3B82F6]/15 text-[#3B82F6]'
                    : 'bg-[#334155]/60 text-[#94A3B8]'
                  }`}>
                    {ev.signal_type} {ev.value}
                  </span>
                  <span className="text-[#F1F5F9] truncate">{ev.label}</span>
                </div>
                <span className="font-mono text-xs text-[#94A3B8] shrink-0 ml-3">
                  {new Date(ev.issued_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
