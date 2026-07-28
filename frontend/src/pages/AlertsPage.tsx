import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import { acknowledgeAlert, fetchAlerts } from '../services/reportApi';

export default function AlertsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['alerts'],
    queryFn: fetchAlerts,
    refetchInterval: 10_000,
  });

  const ackMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });

  if (isError) {
    return <Card title="오류" subtitle="알림을 불러올 수 없습니다" />;
  }

  return (
    <Card title="알림" subtitle="피크 및 시스템 알림">
      {isLoading || !data ? (
        <LoadingSkeleton rows={4} />
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">활성 알림이 없습니다</p>
      ) : (
        <div className="space-y-2">
          {data.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center justify-between rounded-md border border-panel-border bg-surface px-4 py-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <Badge variant={alert.type === 'peak' ? 'peak' : 'warning'}>
                    {alert.type === 'peak' ? '피크' : '제어'}
                  </Badge>
                  {alert.acknowledged && (
                    <Badge variant="success">확인됨</Badge>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-300">{alert.message}</p>
                <p className="text-xs text-muted">
                  {new Date(alert.timestamp).toLocaleString('ko-KR')}
                </p>
              </div>
              {!alert.acknowledged && (
                <Button
                  variant="secondary"
                  className="shrink-0 text-xs"
                  loading={ackMutation.isPending}
                  onClick={() => ackMutation.mutate(alert.id)}
                >
                  확인
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
