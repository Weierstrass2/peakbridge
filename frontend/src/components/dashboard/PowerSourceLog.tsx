import { useQuery } from '@tanstack/react-query';
import { fetchPowerEvents } from '../../services/reportApi';
import type { PowerEvent } from '../../services/reportApi';

interface PowerSourceLogProps {
  /** 현재 피크(절체) 상태 — true면 ESS 방출 중, false면 한전 공급 중 */
  peakActive?: boolean;
}

// 백엔드 created_at이 타임존 없이 오면 UTC로 간주해 KST로 표시
function kstTime(iso: string): string {
  const normalized = /Z|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return new Date(normalized).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  });
}

const EVENT_STYLE: Record<
  PowerEvent['kind'],
  { label: string; dot: string; text: string }
> = {
  switch_to_ess: { label: '한전 → ESS 방출 (절체)', dot: 'bg-[#E8A33D]', text: 'text-[#E8A33D]' },
  return_to_grid: { label: 'ESS → 한전 복귀', dot: 'bg-[#4C8DFF]', text: 'text-[#4C8DFF]' },
  peak_detected: { label: '피크 감지', dot: 'bg-[#E5484D]', text: 'text-[#E5484D]' },
};

export default function PowerSourceLog({ peakActive }: PowerSourceLogProps) {
  const { data: events } = useQuery({
    queryKey: ['power-events'],
    queryFn: () => fetchPowerEvents(6),
    refetchInterval: 5_000,
    staleTime: 2_000,
  });

  return (
    <div className="rounded-md border border-[#222933] bg-[#0E1116] px-5 py-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {/* 현재 전원 상태 배지 */}
        <div
          className={`flex shrink-0 items-center gap-2 rounded-md border px-3 py-1.5 ${
            peakActive
              ? 'border-[#E8A33D]/50 bg-[#E8A33D]/[0.08]'
              : 'border-[#4C8DFF]/40 bg-[#4C8DFF]/[0.06]'
          }`}
        >
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              peakActive ? 'animate-pulse-dot bg-[#E8A33D]' : 'bg-[#4C8DFF]'
            }`}
          />
          <span
            className={`text-sm font-semibold ${
              peakActive ? 'text-[#E8A33D]' : 'text-[#4C8DFF]'
            }`}
          >
            {peakActive ? 'ESS 방출 중' : '한전 공급 중'}
          </span>
        </div>

        {/* 최근 절체 이벤트 (최신순) */}
        <div className="flex min-w-0 flex-1 items-center gap-4 overflow-x-auto whitespace-nowrap text-xs">
          {events && events.length > 0 ? (
            events.map((e) => (
              <span key={e.id} className="flex shrink-0 items-center gap-1.5">
                <span className={`h-1.5 w-1.5 rounded-full ${EVENT_STYLE[e.kind].dot}`} />
                <span className="tabular-nums text-[#98A2B3]">{kstTime(e.timestamp)}</span>
                <span className={`font-medium ${EVENT_STYLE[e.kind].text}`}>
                  {EVENT_STYLE[e.kind].label}
                </span>
                {e.kind === 'peak_detected' && e.gridCurrent != null && (
                  <span className="text-[#98A2B3]">{e.gridCurrent.toFixed(3)}A</span>
                )}
              </span>
            ))
          ) : (
            <span className="text-[#5A6472]">절체 이벤트 없음 — 한전 정상 공급</span>
          )}
        </div>
      </div>
    </div>
  );
}
