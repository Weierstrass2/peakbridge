import { useQuery } from '@tanstack/react-query';
import { fetchChartHistory, fetchDashboard, fetchEvents } from '../services/dashboardApi';
import { useDashboardStore } from '../store/dashboardStore';
import type { DashboardData } from '../types';

export function useDashboard() {
  const liveData = useDashboardStore((s) => s.liveData);

  const dashboardQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 3_000,   // 실물 시연 반응성 — 부하/시각 조정이 3초 내 반영
    staleTime: 1_000,
  });

  const chartQuery = useQuery({
    queryKey: ['dashboard', 'chart'],
    queryFn: fetchChartHistory,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const eventsQuery = useQuery({
    queryKey: ['dashboard', 'events'],
    queryFn: fetchEvents,
    refetchInterval: 15_000,
    staleTime: 5_000,
  });

  const dashboard: DashboardData | undefined = dashboardQuery.data
    ? { ...dashboardQuery.data, ...liveData }
    : undefined;

  return {
    dashboard,
    chartData: chartQuery.data,
    events: eventsQuery.data,
    isLoading: dashboardQuery.isLoading,
    isChartLoading: chartQuery.isLoading,
    isEventsLoading: eventsQuery.isLoading,
    isError: dashboardQuery.isError,
    error: dashboardQuery.error,
    refetch: dashboardQuery.refetch,
  };
}
