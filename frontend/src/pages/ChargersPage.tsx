import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChargerGrid from '../components/dashboard/ChargerGrid';
import DriverFlexPanel from '../components/dashboard/DriverFlexPanel';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { CardSkeleton } from '../components/common/LoadingSkeleton';
import { useDashboard } from '../hooks/useDashboard';
import { api } from '../services/api';
import { apiPaths } from '../config/apiPaths';
import { controlApi } from '../services/controlApi';

interface HistoryItem { time: string; avg_value: number; unit: string; }
interface Wrapped<T> { success: boolean; data: T; }

type StatusFilter = 'all' | 'charging' | 'idle';

export default function ChargersPage() {
  const { dashboard, isLoading, isError } = useDashboard();
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [selectedCharger, setSelectedCharger] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const chargers = dashboard?.chargers ?? [];
  const details = chargers.map((c) => ({
    id: c.device_id,
    current: c.current,
    charging: c.current > 0,
  }));
  const filtered = details.filter((c) =>
    statusFilter === 'all' ? true : statusFilter === 'charging' ? c.charging : !c.charging,
  );
  const selectedId = selectedCharger ?? details[0]?.id ?? null;
  const selected = details.find((c) => c.id === selectedId) ?? null;

  // 선택 충전기 24시간 실전류 이력
  const historyQ = useQuery({
    queryKey: ['charger-history', selectedId],
    queryFn: async () => {
      const { data } = await api.get<Wrapped<{ history: HistoryItem[] }>>(
        apiPaths.sensorHistory(selectedId as string),
        { params: { interval: '1hour' } },
      );
      return (data.data.history ?? []).map((h) => ({
        time: new Date(h.time).toLocaleTimeString('ko-KR', {
          hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Seoul',
        }),
        current: Math.round(h.avg_value * 10) / 10,
      }));
    },
    enabled: !!selectedId,
    retry: false,
    refetchInterval: 60_000,
  });

  if (isError) {
    return <Card title="오류" subtitle="충전기 데이터를 불러올 수 없습니다" />;
  }
  if (isLoading || !dashboard) {
    return <CardSkeleton />;
  }

  const chargingCount = details.filter((c) => c.charging).length;
  const totalCurrent = details.reduce((a, c) => a + c.current, 0);

  const doControl = async (id: string, action: 'pause' | 'resume') => {
    setBusy(`${action}_${id}`);
    try {
      await controlApi.controlCharger(id, action);
      setMessage(`${id} ${action === 'pause' ? '일시 정지' : '재개'} 명령 전송`);
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    } catch {
      setMessage('❌ 명령 실패 (admin 로그인 필요)');
    } finally {
      setBusy(null);
      setTimeout(() => setMessage(null), 3000);
    }
  };

  return (
    <div className="space-y-6">
      {/* Summary KPIs */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="rounded-md border border-[#222933] bg-[#0E1116] p-5">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">등록 충전기</p>
          <p className="mt-2 text-2xl font-bold text-[#E8ECF1] tabular-nums">{details.length}대</p>
        </div>
        <div className="rounded-md border border-[#222933] bg-[#0E1116] p-5">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">충전 중</p>
          <p className="mt-2 text-2xl font-bold text-[#2EBD85] tabular-nums">{chargingCount}대</p>
        </div>
        <div className="rounded-md border border-[#222933] bg-[#0E1116] p-5">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">합계 전류</p>
          <p className="mt-2 text-2xl font-bold text-[#9B8AFB] tabular-nums">{totalCurrent.toFixed(1)}A</p>
        </div>
        <div className="rounded-md border border-[#222933] bg-[#0E1116] p-5">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">정격 용량</p>
          <p className="mt-2 text-2xl font-bold text-[#4C8DFF] tabular-nums">{details.length * 7}kW</p>
          <p className="mt-1 text-xs text-[#98A2B3]">7kW × {details.length}기</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <label className="text-xs text-[#98A2B3] mb-1 block">단지 선택 (다중 단지 확장 예정)</label>
          <select
            className="rounded-md border border-[#222933] bg-[#0E1116] px-4 py-2 text-sm text-[#E8ECF1] outline-none focus:border-[#4C8DFF]"
            defaultValue="A단지"
          >
            <option value="A단지">A단지 — 부산 실증</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-[#98A2B3] mb-1 block">상태 필터</label>
          <div className="flex gap-2">
            {([
              { v: 'all', t: `전체 ${details.length}` },
              { v: 'charging', t: `충전 중 ${chargingCount}` },
              { v: 'idle', t: `대기 ${details.length - chargingCount}` },
            ] as { v: StatusFilter; t: string }[]).map((f) => (
              <button
                key={f.v}
                onClick={() => setStatusFilter(f.v)}
                className={`rounded-md border px-4 py-2 text-sm transition-colors ${
                  statusFilter === f.v
                    ? 'border-[#4C8DFF] bg-[#4C8DFF]/15 text-[#4C8DFF] font-semibold'
                    : 'border-[#222933] bg-[#0E1116] text-[#98A2B3] hover:text-[#E8ECF1]'
                }`}
              >
                {f.t}
              </button>
            ))}
          </div>
        </div>
        {message && <p className="text-sm text-[#E8ECF1] self-end pb-2">{message}</p>}
      </div>

      {/* 차주 예약 · 유연성 재고 (폰 /drive 에서 들어온 실데이터) */}
      <DriverFlexPanel />

      {/* Charger Grid (filtered) */}
      <ChargerGrid chargers={chargers.filter((c) =>
        statusFilter === 'all' ? true : statusFilter === 'charging' ? c.current > 0 : c.current <= 0,
      )} />

      {/* Table + Detail */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card title="충전기 목록" subtitle={`${filtered.length}대 표시`}>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[#222933]">
                  <th className="pb-3 pr-4 text-xs font-semibold text-[#98A2B3]">충전기 ID</th>
                  <th className="pb-3 pr-4 text-xs font-semibold text-[#98A2B3]">전류</th>
                  <th className="pb-3 pr-4 text-xs font-semibold text-[#98A2B3]">상태</th>
                  <th className="pb-3 text-xs font-semibold text-[#98A2B3]">제어</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={4} className="py-4 text-sm text-[#98A2B3]">해당 상태의 충전기가 없습니다</td></tr>
                )}
                {filtered.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => setSelectedCharger(c.id)}
                    className={`border-b border-[#222933]/50 cursor-pointer transition-all hover:bg-[#222933]/20 ${
                      selectedId === c.id ? 'bg-[#222933]/30' : ''
                    }`}
                  >
                    <td className="py-4 pr-4 font-medium text-[#E8ECF1]">{c.id}</td>
                    <td className="py-4 pr-4 tabular-nums text-[#9B8AFB] font-semibold">{c.current.toFixed(1)}A</td>
                    <td className="py-4 pr-4">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                        c.charging ? 'bg-[#2EBD85]/10 text-[#2EBD85]' : 'bg-[#222933]/50 text-[#98A2B3]'
                      }`}>
                        {c.charging ? '충전 중' : '대기'}
                      </span>
                    </td>
                    <td className="py-4">
                      <div className="flex gap-2">
                        <Button
                          variant="secondary" className="px-3 py-1 text-xs"
                          loading={busy === `pause_${c.id}`}
                          onClick={() => doControl(c.id, 'pause')}
                        >정지</Button>
                        <Button
                          variant="secondary" className="px-3 py-1 text-xs"
                          loading={busy === `resume_${c.id}`}
                          onClick={() => doControl(c.id, 'resume')}
                        >재개</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title={`${selectedId ?? '—'} — 24시간 전류 이력`} subtitle="센서 실데이터 (1시간 집계)">
            <div className="h-56">
              {historyQ.data && historyQ.data.length > 1 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={historyQ.data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#222933" vertical={false} />
                    <XAxis dataKey="time" tick={{ fill: '#98A2B3', fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: '#98A2B3', fontSize: 11 }} tickLine={false} axisLine={false}
                      tickFormatter={(v) => `${v}A`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0E1116', border: '1px solid #222933', borderRadius: 8, fontSize: 12 }}
                      formatter={(v: number) => [`${v}A`, '전류']}
                    />
                    <Area type="monotone" dataKey="current" stroke="#9B8AFB" strokeWidth={2}
                      fill="#9B8AFB" fillOpacity={0.15} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-1">
                  <p className="text-sm text-[#98A2B3]">아직 수집된 전류 이력이 없습니다</p>
                  <p className="text-xs text-[#5C6673]">ESP32가 측정값을 전송하면 자동으로 채워집니다</p>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Detail / Telemetry */}
        <div className="space-y-6">
          {selected && (
            <Card title={`${selected.id} 상세`} subtitle="기기 텔레메트리">
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-[#98A2B3]">현재 전류</span>
                  <span className="font-bold text-[#9B8AFB] tabular-nums">{selected.current.toFixed(1)}A</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#98A2B3]">상태</span>
                  <span className={selected.charging ? 'text-[#2EBD85] font-semibold' : 'text-[#98A2B3]'}>
                    {selected.charging ? '충전 중' : '대기'}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#98A2B3]">정격 출력</span>
                  <span className="text-[#E8ECF1] tabular-nums">7.0 kW</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#98A2B3]">전압</span>
                  <span className="text-[#E8ECF1] tabular-nums">{selected.charging ? '220V' : '—'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#98A2B3]">통신</span>
                  <span className="text-[#E8ECF1]">MQTT · ESP32</span>
                </div>
                <div className="border-t border-[#222933] pt-3">
                  <p className="text-xs text-[#98A2B3] mb-1">센서 토픽</p>
                  <p className="font-mono text-[11px] text-[#5C6673] break-all">
                    peakbridge/building-A/charger/{selected.id}/current
                  </p>
                  <p className="text-xs text-[#98A2B3] mt-2 mb-1">제어 토픽</p>
                  <p className="font-mono text-[11px] text-[#5C6673] break-all">
                    peakbridge/building-A/charger/{selected.id}/control
                  </p>
                </div>
              </div>
            </Card>
          )}
          <Card title="확장 로드맵" subtitle="다중 브랜드 연동">
            <p className="text-sm text-[#98A2B3] leading-relaxed">
              현재 자체 ESP32 충전기 1기로 실증 중입니다.
              OCPP 표준 연동으로 차지비·에버온·파워큐브 등
              상용 충전기를 동일 파이프라인에 수용하는 것이 확장 계획입니다.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
