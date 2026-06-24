import { useState } from 'react';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import { useDashboard } from '../hooks/useDashboard';
import { sendControlAction } from '../services/dashboardApi';

const controlLogs = [
  { id: 1, time: '19:02:34', type: 'AI 자동', message: 'ESS 방전 시작' },
  { id: 2, time: '18:55:12', type: '수동', message: 'ESS 충전 시작' },
  { id: 3, time: '18:30:05', type: 'AI 자동', message: '피크 임계치 조정 (15A → 14A)' },
];

export default function ControlPage() {
  const { dashboard } = useDashboard();
  const [threshold, setThreshold] = useState(dashboard?.peak_threshold ?? 15);
  const [autoControl, setAutoControl] = useState(true);
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const runAction = async (action: string, payload?: Record<string, unknown>) => {
    setLoading(action);
    setMessage(null);
    try {
      await sendControlAction(action, payload);
      setMessage(`✅ '${action}' 명령이 전송되었습니다.`);
      setTimeout(() => setMessage(null), 3000);
    } catch {
      setMessage(`❌ '${action}' 명령 전송에 실패했습니다.`);
      setTimeout(() => setMessage(null), 3000);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Control Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ESS Control */}
        <Card title="ESS 제어" subtitle="수동 제어">
          <div className="grid grid-cols-3 gap-3">
            <Button
              variant="secondary"
              loading={loading === 'discharge'}
              onClick={() => runAction('discharge')}
            >
              강제 방전
            </Button>
            <Button
              variant="secondary"
              loading={loading === 'charge'}
              onClick={() => runAction('charge')}
            >
              강제 충전
            </Button>
            <Button
              variant="secondary"
              loading={loading === 'standby'}
              onClick={() => runAction('standby')}
            >
              대기
            </Button>
          </div>
        </Card>

        {/* Peak Threshold Slider */}
        <Card title="피크 임계치" subtitle="그리드 전류 제한">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#94A3B8]">10A</span>
              <span className="text-2xl font-bold text-[#FBBF24]">{threshold.toFixed(1)}A</span>
              <span className="text-sm text-[#94A3B8]">30A</span>
            </div>
            <input
              type="range"
              min={10}
              max={30}
              step={0.5}
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full accent-[#F97316]"
            />
            <Button
              loading={loading === 'set_threshold'}
              onClick={() => runAction('set_threshold', { value: threshold })}
            >
              적용
            </Button>
          </div>
        </Card>

        {/* AI Control Toggle */}
        <Card title="AI 자동 제어" subtitle="피크쉐이빙 자동화">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[#F1F5F9] mb-1">자동 제어</p>
              <p className="text-xs text-[#94A3B8]">{autoControl ? 'ON' : 'OFF'}</p>
            </div>
            <button
              onClick={() => setAutoControl(!autoControl)}
              className={`w-16 h-8 rounded-full transition-colors relative ${
                autoControl ? 'bg-[#10B981]' : 'bg-[#334155]'
              }`}
            >
              <div
                className={`absolute top-1 left-1 bg-white w-6 h-6 rounded-full transition-transform ${
                  autoControl ? 'translate-x-8' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </Card>
      </div>

      {/* Charger Controls */}
      <Card title="충전기 제어" subtitle="개별 충전기 관리">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {dashboard?.chargers.map((c) => (
            <div
              key={c.device_id}
              className="rounded-xl border border-[#334155] bg-[#0F172A] p-4"
            >
              <p className="text-sm font-semibold text-[#F1F5F9] mb-3">{c.device_id}</p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1 px-2 py-1.5 text-xs"
                  loading={loading === `pause_${c.device_id}`}
                  onClick={() => runAction('pause_charger', { device_id: c.device_id })}
                >
                  일시 정지
                </Button>
                <Button
                  variant="secondary"
                  className="flex-1 px-2 py-1.5 text-xs"
                  loading={loading === `resume_${c.device_id}`}
                  onClick={() => runAction('resume_charger', { device_id: c.device_id })}
                >
                  재개
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Message + Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card title="실시간 제어 로그">
            <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
              {controlLogs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-start gap-3 rounded-xl border border-[#334155] bg-[#0F172A] px-4 py-3"
                >
                  <div className="mt-1">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                        log.type === 'AI 자동'
                          ? 'bg-[#3B82F6]/10 text-[#3B82F6]'
                          : 'bg-[#A78BFA]/10 text-[#A78BFA]'
                      }`}
                    >
                      {log.type}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-xs text-[#94A3B8]">{log.time}</p>
                    <p className="text-sm text-[#F1F5F9]">{log.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Status Panel */}
        <div className="space-y-6">
          {message && (
            <Card>
              <p className="text-sm text-[#F1F5F9]">{message}</p>
            </Card>
          )}

          <Card title="시스템 상태">
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#94A3B8]">그리드 전류</span>
                <span className="text-lg font-bold text-[#3B82F6]">{dashboard?.grid_current.toFixed(1) || '0.0'}A</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#94A3B8]">ESS SOC</span>
                <span className="text-lg font-bold text-[#34D399]">{dashboard?.ess_soc || 0}%</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#94A3B8]">피크 상태</span>
                <span className={`text-sm font-semibold ${
                  dashboard?.peak_active ? 'text-[#F97316]' : 'text-[#10B981]'
                }`}>
                  {dashboard?.peak_active ? '⚡ 활성' : '✅ 정상'}
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
