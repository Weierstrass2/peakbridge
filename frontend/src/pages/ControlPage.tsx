import { useState } from 'react';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import { useDashboard } from '../hooks/useDashboard';
import { sendControlAction } from '../services/dashboardApi';

export default function ControlPage() {
  const { dashboard } = useDashboard();
  const [threshold, setThreshold] = useState(dashboard?.peak_threshold ?? 15);
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  const runAction = async (action: string, payload?: Record<string, unknown>) => {
    setLoading(action);
    setMessage('');
    try {
      await sendControlAction(action, payload);
      setMessage(`Action "${action}" sent successfully`);
    } catch {
      setMessage(`Failed to send "${action}"`);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-4">
      <Card title="Peak Threshold" subtitle="Set grid current limit for peak shaving">
        <div className="flex items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted">Threshold (A)</label>
            <input
              type="number"
              step="0.1"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-32 rounded-lg border border-panel-border bg-surface px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
            />
          </div>
          <Button
            loading={loading === 'set_threshold'}
            onClick={() => runAction('set_threshold', { value: threshold })}
          >
            Apply
          </Button>
        </div>
      </Card>

      <Card title="Charger Control" subtitle="Manual override for individual chargers">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {dashboard?.chargers.map((c) => (
            <div key={c.device_id} className="rounded-lg border border-panel-border bg-surface p-3">
              <p className="text-sm font-medium text-white">{c.device_id}</p>
              <div className="mt-2 flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1 px-2 py-1 text-xs"
                  loading={loading === `pause_${c.device_id}`}
                  onClick={() => runAction('pause_charger', { device_id: c.device_id })}
                >
                  Pause
                </Button>
                <Button
                  variant="secondary"
                  className="flex-1 px-2 py-1 text-xs"
                  loading={loading === `resume_${c.device_id}`}
                  onClick={() => runAction('resume_charger', { device_id: c.device_id })}
                >
                  Resume
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {message && (
        <p className="text-sm text-muted">{message}</p>
      )}
    </div>
  );
}
