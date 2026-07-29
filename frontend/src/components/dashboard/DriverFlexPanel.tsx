/**
 * 차주 예약 · 유연성 재고 패널 (관제 운영자용)
 *
 * 차주가 폰(/drive)에서 등록한 충전 세션과, 그로부터 집계된 유연성 재고를
 * 실시간으로 보여준다. 목업이 아니라 백엔드 /api/v1/drive 를 그대로 읽는다 —
 * 같은 재고를 VPP OS(/console) 제주 플러스DR 배분이 함께 참조한다.
 */
import { useQuery } from '@tanstack/react-query';

import Card from '../common/Card';
import { api } from '../../services/api';
import { apiPaths } from '../../config/apiPaths';
import { BUILDING_ID } from '../../config/env';

interface DriveSession {
  code: string;
  household: string;
  building_id: string;
  need_kwh: number;
  depart: string;
  depart_hour: number | null;
  mode: 'eco' | 'now';
  mode_label: string;
  status: 'active' | 'cancelled' | 'done';
  is_flexible: boolean;
  created_at: string;
}

interface Flexibility {
  building_id: string;
  flex_kwh: number;
  flex_session_count: number;
  immediate_kwh: number;
  immediate_session_count: number;
  updated_at: string;
}

interface Wrapped<T> {
  success: boolean;
  data: T;
}

interface DriverFlexPanelProps {
  /** 조회 대상 단지. 미지정 시 환경설정의 기본 단지. */
  buildingId?: string;
  /** 폴링 주기(ms). 시연 중 즉시성이 중요해 기본 4초. */
  refetchIntervalMs?: number;
}

export default function DriverFlexPanel({
  buildingId = BUILDING_ID,
  refetchIntervalMs = 4000,
}: DriverFlexPanelProps) {
  const flexQ = useQuery({
    queryKey: ['drive-flexibility', buildingId],
    queryFn: async () => {
      const { data } = await api.get<Wrapped<Flexibility>>(apiPaths.driveFlexibility, {
        params: { building_id: buildingId },
      });
      return data.data;
    },
    refetchInterval: refetchIntervalMs,
    retry: false,
  });

  const sessionsQ = useQuery({
    queryKey: ['drive-sessions', buildingId],
    queryFn: async () => {
      const { data } = await api.get<Wrapped<{ sessions: DriveSession[]; count: number }>>(
        apiPaths.driveSessions,
        { params: { building_id: buildingId } },
      );
      return data.data.sessions ?? [];
    },
    refetchInterval: refetchIntervalMs,
    retry: false,
  });

  const flex = flexQ.data;
  const sessions = sessionsQ.data ?? [];
  const active = sessions.filter((s) => s.status === 'active');

  return (
    <Card
      title="차주 예약 · 유연성 재고"
      subtitle="입주민이 폰(/drive)에서 등록한 충전 세션 — 실시간"
      action={
        <span className="flex items-center gap-1.5 text-xs text-[#98A2B3]">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#2EBD85]" />
          {flex?.updated_at ?? '연결 중'}
        </span>
      }
    >
      <div className="mt-4 grid grid-cols-3 gap-3">
        <div className="rounded-md border border-[#2EBD85]/35 bg-[#2EBD85]/[0.07] p-4">
          <p className="text-xs text-[#98A2B3]">유연성 재고</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[#2EBD85]">
            {(flex?.flex_kwh ?? 0).toFixed(1)}
            <span className="ml-1 text-sm font-medium">kWh</span>
          </p>
          <p className="mt-1 text-xs text-[#5C6673]">알뜰 충전 {flex?.flex_session_count ?? 0}건</p>
        </div>
        <div className="rounded-md border border-[#222933] bg-[#0E1116] p-4">
          <p className="text-xs text-[#98A2B3]">즉시 충전</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[#FFB020]">
            {(flex?.immediate_kwh ?? 0).toFixed(1)}
            <span className="ml-1 text-sm font-medium">kWh</span>
          </p>
          <p className="mt-1 text-xs text-[#5C6673]">
            {flex?.immediate_session_count ?? 0}건 · 이동 불가
          </p>
        </div>
        <div className="rounded-md border border-[#222933] bg-[#0E1116] p-4">
          <p className="text-xs text-[#98A2B3]">활성 예약</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[#E8ECF1]">{active.length}건</p>
          <p className="mt-1 text-xs text-[#5C6673]">누적 {sessions.length}건</p>
        </div>
      </div>

      <div className="mt-5">
        {sessionsQ.isError && (
          <p className="text-sm text-[#98A2B3]">세션 정보를 불러오지 못했습니다.</p>
        )}
        {!sessionsQ.isError && sessions.length === 0 && (
          <div className="rounded-md border border-dashed border-[#222933] px-4 py-6 text-center">
            <p className="text-sm text-[#98A2B3]">아직 등록된 차주 예약이 없습니다</p>
            <p className="mt-1 text-xs text-[#5C6673]">
              입주민이 QR로 <span className="font-mono">/drive</span> 접속 후 예약하면 즉시 표시됩니다
            </p>
          </div>
        )}
        {sessions.length > 0 && (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-[#222933]">
                <th className="pb-2 pr-4 text-xs font-semibold text-[#98A2B3]">세대</th>
                <th className="pb-2 pr-4 text-xs font-semibold text-[#98A2B3]">필요 전력</th>
                <th className="pb-2 pr-4 text-xs font-semibold text-[#98A2B3]">출발</th>
                <th className="pb-2 pr-4 text-xs font-semibold text-[#98A2B3]">방식</th>
                <th className="pb-2 pr-4 text-xs font-semibold text-[#98A2B3]">접수</th>
                <th className="pb-2 text-xs font-semibold text-[#98A2B3]">코드</th>
              </tr>
            </thead>
            <tbody>
              {sessions.slice(0, 12).map((s) => (
                <tr
                  key={s.code}
                  className={`border-b border-[#222933]/50 ${
                    s.status === 'active' ? '' : 'opacity-40 line-through'
                  }`}
                >
                  <td className="py-3 pr-4 font-medium text-[#E8ECF1]">{s.household}</td>
                  <td className="py-3 pr-4 font-semibold tabular-nums text-[#9B8AFB]">
                    {s.need_kwh.toFixed(1)}kWh
                  </td>
                  <td className="py-3 pr-4 tabular-nums text-[#98A2B3]">{s.depart || '—'}</td>
                  <td className="py-3 pr-4">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                        s.mode === 'eco'
                          ? 'bg-[#2EBD85]/10 text-[#2EBD85]'
                          : 'bg-[#FFB020]/10 text-[#FFB020]'
                      }`}
                    >
                      {s.mode_label}
                    </span>
                  </td>
                  <td className="py-3 pr-4 tabular-nums text-[#5C6673]">{s.created_at}</td>
                  <td className="py-3 font-mono text-[11px] text-[#5C6673]">{s.code}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="mt-4 border-t border-[#222933] pt-3 text-xs leading-relaxed text-[#5C6673]">
        알뜰 충전으로 등록된 전력량은 출발 시각 전까지 이동 가능한 부하이며, 그대로 유연성
        재고가 되어 VPP OS의 플러스DR 배분에 투입됩니다.
      </p>
    </Card>
  );
}
