import { useState } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData } from '../../types';
import { controlApi } from '../../services/controlApi';
import { formatCo2Kg, formatWon } from '../../utils/format';
import { MetricSkeleton } from '../common/LoadingSkeleton';

interface TopMetricsProps {
  data?: DashboardData;
  loading?: boolean;
}

function KPICard({
  label,
  value,
  sub,
  accent = 'text-white',
  isHighlight = false,
  children,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  isHighlight?: boolean;
  children?: ReactNode;
}) {
  return (
    <div
      className={`rounded-md border bg-[#0E1116] p-5 ${
        isHighlight ? 'border-[#E8A33D]/50 bg-[#E8A33D]/[0.06]' : 'border-[#222933]'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">{label}</p>
      <p className={`mt-2 text-2xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-[#98A2B3]">{sub}</p>}
      {children}
    </div>
  );
}

export default function TopMetrics({ data, loading }: TopMetricsProps) {
  const qc = useQueryClient();
  const [resetBusy, setResetBusy] = useState(false);
  const [resetFailed, setResetFailed] = useState(false);

  const resetEssSoc = async () => {
    setResetBusy(true);
    setResetFailed(false);
    try {
      await controlApi.resetEssSoc();
      await qc.invalidateQueries({ queryKey: ['dashboard'] });
    } catch {
      setResetFailed(true); // 관리자 로그인 안 됐거나 서버 오류
    } finally {
      setResetBusy(false);
    }
  };

  if (loading || !data) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricSkeleton key={i} />
        ))}
      </div>
    );
  }

  const battTemp = data.ess_battery_temp_c;
  const invTemp = data.ess_inverter_temp_c;
  const thermalLock = data.thermal_lock === true;
  const temps = [battTemp, invTemp].filter((v): v is number => typeof v === 'number');

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KPICard
        label="오늘 절감액"
        value={formatWon(data.today_saved_won)}
        accent="text-[#E8A33D]"
        isHighlight={true}
      />
      <KPICard
        label="이번달 절감액"
        value={formatWon(data.month_saved_won)}
        accent="text-[#E8ECF1]"
      />
      <KPICard
        label="ESS 잔량"
        value={`${(data.ess_soc ?? 0).toFixed(1)}%`}
        sub={
          data.ess_remain_hours != null && data.ess_remain_hours > 0
            ? `현재 방전율로 ${data.ess_remain_hours.toFixed(1)}시간 공급 가능`
            : undefined
        }
        accent={(data.ess_soc ?? 0) < 20 ? 'text-[#E5484D]' : 'text-[#2EBD85]'}
      >
        <div className="mt-2 w-full bg-[#222933] rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${
              (data.ess_soc ?? 0) < 20 ? 'bg-[#E5484D]' : 'bg-[#2EBD85]'
            }`}
            style={{ width: `${data.ess_soc ?? 0}%` }}
          />
        </div>
        <button
          onClick={resetEssSoc}
          disabled={resetBusy}
          title="쿨롱 카운팅 기준값을 만충(100%)으로 보정합니다 — 배터리 교체·재충전 후 사용"
          className="mt-3 w-full rounded-md bg-[#222933] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[#303947] disabled:opacity-40"
        >
          {resetBusy ? '리셋 중…' : '100%로 리셋'}
        </button>
        {resetFailed && (
          <p className="mt-1 text-[11px] text-[#E5484D]">리셋 실패 — 관리자 로그인 필요</p>
        )}
      </KPICard>
      <KPICard
        label="CO2 절감"
        value={formatCo2Kg(data.co2_reduced_kg)}
        accent="text-[#2EBD85]"
      />
      </div>

      {thermalLock || temps.length > 0 ? (
        <div
          className={`rounded-md border p-5 ${
            thermalLock ? 'border-[#E5484D]/50 bg-[#E5484D]/[0.08]' : 'border-[#222933] bg-[#0E1116]'
          }`}
        >
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm font-medium uppercase tracking-wider text-[#98A2B3]">
              🌡 온도 · 열 차단 (BME280)
            </p>
            <span
              className={`rounded-full px-4 py-1.5 text-base font-semibold ${
                thermalLock ? 'bg-[#E5484D]/20 text-[#E5484D]' : 'bg-[#2EBD85]/15 text-[#2EBD85]'
              }`}
            >
              {thermalLock ? '⚠ 열 차단 발동' : '정상'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-[#98A2B3]">배터리 옆</p>
              <p
                className={`mt-1 text-4xl font-bold tabular-nums ${
                  battTemp != null && battTemp >= 50 ? 'text-[#E5484D]' : 'text-white'
                }`}
              >
                {battTemp != null ? `${battTemp.toFixed(1)}°C` : '—'}
              </p>
            </div>
            <div>
              <p className="text-sm text-[#98A2B3]">인버터 옆</p>
              <p
                className={`mt-1 text-4xl font-bold tabular-nums ${
                  invTemp != null && invTemp >= 50 ? 'text-[#E5484D]' : 'text-white'
                }`}
              >
                {invTemp != null ? `${invTemp.toFixed(1)}°C` : '—'}
              </p>
            </div>
          </div>
          {thermalLock && (
            <p className="mt-4 text-base font-medium text-[#E5484D]">
              과열로 ESS 방전을 정지하고 한전으로 고정했습니다.
              {temps.length > 0 && ` (최고 ${Math.max(...temps).toFixed(1)}°C)`}
            </p>
          )}
          <p className="mt-3 text-xs text-[#98A2B3]">
            트립 50°C / 해제 43°C · 둘 중 더 뜨거운 값으로 판정 (히스테리시스)
          </p>
        </div>
      ) : null}
    </div>
  );
}
