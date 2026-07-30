import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchChartHistory, fetchDashboard, fetchEvents } from '../services/dashboardApi';
import { useDashboardStore } from '../store/dashboardStore';
import type { ChartPoint, DashboardData } from '../types';

export function useDashboard() {
  const liveData = useDashboardStore((s) => s.liveData);

  const dashboardQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 3_000,   // 실물 시연 반응성 — 부하/시각 조정이 3초 내 반영
    staleTime: 1_000,
  });

  // 1분 이력 — 이제 실시간 라이브 테일의 '시드/폴백' 역할만 한다(주 라인은 아래 liveRef).
  const chartQuery = useQuery({
    queryKey: ['dashboard', 'chart'],
    queryFn: fetchChartHistory,
    refetchInterval: 15_000,
    staleTime: 10_000,
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

  // ── 실시간 라이브 테일 ───────────────────────────────────────────────
  // 5분/1분 평균 이력 대신, 3초마다 갱신되는 dashboard.grid_current(순간 실측값)를
  // 클라이언트에 누적해 진짜 실시간 라인을 만든다(로컬 :8010 대시보드와 같은 원리).
  // 백엔드 무변경. 처음엔 1분 이력 꼬리로 시드해 빈 화면·점프를 막는다.
  const liveRef = useRef<ChartPoint[]>([]);
  const seededRef = useRef(false);
  const MAX_LIVE_POINTS = 200; // 3초 × 200 ≈ 최근 10분

  useEffect(() => {
    const d = dashboardQuery.data;
    if (d?.grid_current == null) return;
    if (!seededRef.current) {
      liveRef.current = (chartQuery.data ?? []).slice(-20);
      seededRef.current = true;
    }
    const time = new Date().toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    liveRef.current = [
      ...liveRef.current,
      {
        time,
        grid_current: d.grid_current,
        ess_discharge: d.ess_discharge ?? 0,
        charger_total: 0,
      },
    ].slice(-MAX_LIVE_POINTS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardQuery.dataUpdatedAt]);

  // 라이브 포인트가 충분히 쌓이기 전에는 1분 이력을 보여주고, 이후엔 실시간 라인으로.
  const chartData = liveRef.current.length >= 5 ? liveRef.current : chartQuery.data;

  return {
    dashboard,
    chartData,
    events: eventsQuery.data,
    isLoading: dashboardQuery.isLoading,
    isChartLoading: chartQuery.isLoading,
    isEventsLoading: eventsQuery.isLoading,
    isError: dashboardQuery.isError,
    error: dashboardQuery.error,
    refetch: dashboardQuery.refetch,
  };
}
