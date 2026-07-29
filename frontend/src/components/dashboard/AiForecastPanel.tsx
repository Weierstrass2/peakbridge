import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData } from '../../types';
import { controlApi } from '../../services/controlApi';
import Card from '../common/Card';

interface AiForecastPanelProps {
  data?: DashboardData;
}

const KST_LABEL = (iso: string) =>
  new Date(iso).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  });

export default function AiForecastPanel({ data }: AiForecastPanelProps) {
  const qc = useQueryClient();
  const [demoHour, setDemoHour] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  // 서버가 알려준 데모 시각(KST hour)으로 슬라이더 초기 동기화
  useEffect(() => {
    if (data?.demo_time) {
      const h = new Date(data.demo_time).getUTCHours();
      setDemoHour((h + 9) % 24);
    } else {
      setDemoHour(null);
    }
    // data.demo_time이 바뀔 때만
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.demo_time]);

  const applyDemoHour = async (hour: number | null) => {
    setBusy(true);
    try {
      await controlApi.setDemoTime(hour);
      await qc.invalidateQueries({ queryKey: ['dashboard'] });
    } catch {
      /* 로그인 안 됐으면 무시 — 배지 표시엔 영향 없음 */
    } finally {
      setBusy(false);
    }
  };

  const nextPeak = data?.next_peak ?? null;
  const isDemo = !!data?.demo_time;
  const sliderValue = demoHour ?? new Date().getHours();

  return (
    <Card title="AI 피크 예측" subtitle="XGBoost 수요예측 · 실측 스케일 정렬">
      <div className="space-y-5">
        {/* 다음 피크 예상 배지 */}
        {nextPeak ? (
          <div className="animate-slide-in rounded-md border border-[#E8A33D]/40 bg-[#E8A33D]/[0.08] p-4">
            <div className="flex items-center gap-3">
              <span className="animate-pulse-dot h-2.5 w-2.5 rounded-full bg-[#E8A33D]" />
              <div>
                <p className="text-sm font-semibold text-[#E8A33D]">
                  ⚠️ {nextPeak.minutes_ahead}분 뒤 피크 예상
                </p>
                <p className="mt-0.5 text-xs text-[#98A2B3]">
                  {KST_LABEL(nextPeak.time)} 경 예측 전류{' '}
                  <span className="font-bold text-[#E8ECF1]">
                    {nextPeak.predicted_current.toFixed(3)}A
                  </span>{' '}
                  — 임계치 {(data?.peak_threshold ?? 0).toFixed(3)}A 초과 예상
                </p>
              </div>
            </div>
            <p className="mt-2 text-xs text-[#2EBD85]">
              → ESS 선제 방전 준비 (하드웨어 임계치 자동 하향 대상)
            </p>
          </div>
        ) : (
          <div className="rounded-md border border-[#222933] bg-[#0A0C10] p-4">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 rounded-full bg-[#2EBD85]" />
              <p className="text-sm text-[#98A2B3]">
                향후 1시간 내 피크 예상 없음 — 정상 범위
              </p>
            </div>
          </div>
        )}

        {/* 데모 시간 조정 (시연용) */}
        <div className="rounded-md border border-[#222933] bg-[#0A0C10] p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">
              시연 시각 조정
            </span>
            <span className="text-sm font-bold tabular-nums text-[#4C8DFF]">
              {isDemo ? `가상 ${String(sliderValue).padStart(2, '0')}:00 (KST)` : '실시간'}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={23}
            step={1}
            value={sliderValue}
            disabled={busy}
            onChange={(e) => setDemoHour(parseInt(e.target.value))}
            onMouseUp={(e) => applyDemoHour(parseInt((e.target as HTMLInputElement).value))}
            onTouchEnd={(e) => applyDemoHour(parseInt((e.target as HTMLInputElement).value))}
            className="w-full accent-[#4C8DFF]"
          />
          <div className="mt-1 flex justify-between text-[10px] text-[#5A6472]">
            <span>0시</span>
            <span>피크대 (18~21시)</span>
            <span>23시</span>
          </div>
          <button
            onClick={() => {
              setDemoHour(null);
              applyDemoHour(null);
            }}
            disabled={busy || !isDemo}
            className="mt-3 w-full rounded-md bg-[#222933] px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-[#303947] disabled:opacity-40"
          >
            실시간으로 복원
          </button>
          <p className="mt-2 text-[11px] leading-relaxed text-[#5A6472]">
            시각을 피크 시간대(18~21시)로 옮기면 AI 예측선이 상승해 피크 예상이 뜹니다.
            실제 피크 판정·제어는 실시간 기준으로 동작합니다.
          </p>
        </div>
      </div>
    </Card>
  );
}
