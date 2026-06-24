import { useMemo } from 'react';
import { useDashboard } from './useDashboard';

export function usePeakAlert() {
  const { dashboard } = useDashboard();

  return useMemo(() => {
    if (!dashboard) {
      return {
        isActive: false,
        gridCurrent: 0,
        threshold: 15,
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
        ? `Grid ${dashboard.grid_current.toFixed(1)}A exceeds threshold ${dashboard.peak_threshold.toFixed(1)}A`
        : 'Operating within normal limits',
    };
  }, [dashboard]);
}
