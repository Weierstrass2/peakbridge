import { useMemo } from 'react';
import { useDashboard } from './useDashboard';

export function usePeakAlert() {
  const { dashboard } = useDashboard();

  return useMemo(() => {
    if (!dashboard) {
      return {
        isActive: false,
        gridCurrent: 0,
        threshold: 0.095,
        overBy: 0,
        message: '',
      };
    }

    const overBy = Math.max(0, dashboard.grid_current - dashboard.peak_threshold);

    return {
      isActive: dashboard.peak_active,
      gridCurrent: dashboard.grid_current,
      threshold: dashboard.peak_threshold,
      overBy,
      message: dashboard.peak_active
        ? `그리드 ${dashboard.grid_current.toFixed(3)}A — 임계치 ${dashboard.peak_threshold.toFixed(3)}A 초과`
        : '정상 범위 내 운전 중',
    };
  }, [dashboard]);
}
