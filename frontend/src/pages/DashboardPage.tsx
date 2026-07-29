import TopMetrics from '../components/dashboard/TopMetrics';
import AiForecastPanel from '../components/dashboard/AiForecastPanel';
import RealtimeChart from '../components/dashboard/RealtimeChart';
import EnergyFlowDiagram from '../components/dashboard/EnergyFlowDiagram';
import PowerSourceLog from '../components/dashboard/PowerSourceLog';
import ChargerGrid from '../components/dashboard/ChargerGrid';
import SavingsCard from '../components/dashboard/SavingsCard';
import EventLogPanel from '../components/dashboard/EventLogPanel';
import Card from '../components/common/Card';
import { useDashboard } from '../hooks/useDashboard';

export default function DashboardPage() {
  const { dashboard, chartData, events, isLoading, isChartLoading, isEventsLoading, isError } =
    useDashboard();

  if (isError) {
    return (
      <Card title="연결 오류" subtitle="대시보드 데이터를 불러올 수 없습니다">
        <p className="text-sm text-[#98A2B3]">
          앱은 계속 실행 중입니다. 백엔드 연결을 확인하거나 모드 모드를 활성화하세요.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Metrics */}
      <TopMetrics data={dashboard} loading={isLoading} />

      {/* AI 피크 예측 + 시연 시각 조정 */}
      <AiForecastPanel data={dashboard} />

      {/* Energy Flow + Chart */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* 전원 절체 로그 — 한전/ESS 방출 상태와 최근 절체 이벤트 */}
          <PowerSourceLog peakActive={dashboard?.peak_active} />
          <RealtimeChart
            data={chartData}
            threshold={dashboard?.peak_threshold ?? 0.095}
            loading={isChartLoading}
          />
        </div>
        <EnergyFlowDiagram data={dashboard} loading={isLoading} />
      </div>

      {/* Chargers */}
      {dashboard && <ChargerGrid chargers={dashboard.chargers} />}

      {/* Forecast (if available) */}
      {dashboard?.forecast && (
        <Card title="피크 예측" subtitle="다음 1시간 (5분 간격)">
          <div className="flex flex-wrap gap-3">
            {dashboard.forecast.map((point) => (
              <div
                key={point.time}
                className={`rounded-md border px-4 py-3 text-center ${
                  point.will_exceed
                    ? 'border-[#E8A33D]/30 bg-[#E8A33D]/10'
                    : 'border-[#222933] bg-[#0A0C10]'
                }`}
              >
                <p className="text-xs text-[#98A2B3]">
                  {new Date(point.time).toLocaleTimeString('ko-KR', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                    timeZone: 'Asia/Seoul',
                  })}
                </p>
                <p className={`text-lg font-bold tabular-nums mt-1 ${
                  point.will_exceed ? 'text-[#E8A33D]' : 'text-[#2EBD85]'
                }`}>
                  {(point.predicted_current ?? 0).toFixed(3)}A
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Savings + Events */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {dashboard && (
            <SavingsCard
              todaySaved={dashboard.today_saved_won}
              monthSaved={dashboard.month_saved_won}
              co2Reduced={dashboard.co2_reduced_kg}
            />
          )}
        </div>
        <EventLogPanel events={events} loading={isEventsLoading} />
      </div>
    </div>
  );
}
