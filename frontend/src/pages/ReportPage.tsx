import { useQuery } from '@tanstack/react-query';
import Card from '../components/common/Card';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import { formatKRW } from '../mock/mockData';
import { fetchReports } from '../services/reportApi';

export default function ReportPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['reports'],
    queryFn: fetchReports,
  });

  if (isError) {
    return <Card title="Error" subtitle="Failed to load reports" />;
  }

  return (
    <div className="space-y-4">
      <Card title="Monthly Reports" subtitle="Peak shaving performance summary">
        {isLoading || !data ? (
          <LoadingSkeleton rows={3} />
        ) : (
          <div className="space-y-3">
            {data.map((report) => (
              <div
                key={report.period}
                className="rounded-lg border border-panel-border bg-surface p-4"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-white">{report.period}</h3>
                  <span className="text-lg font-bold text-emerald-400">
                    {formatKRW(report.total_saved_won)}
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-4 text-xs text-muted">
                  <div>
                    <p>Peak Events</p>
                    <p className="text-sm font-medium text-white">{report.peak_events}</p>
                  </div>
                  <div>
                    <p>CO₂ Reduced</p>
                    <p className="text-sm font-medium text-white">{report.co2_reduced_kg} kg</p>
                  </div>
                  <div>
                    <p>Avg Grid Current</p>
                    <p className="text-sm font-medium text-white">{report.avg_grid_current} A</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
