import { useEffect, useState } from 'react';
import axios from 'axios';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import { useDashboard } from '../hooks/useDashboard';
import { sendControlAction } from '../services/dashboardApi';
import { controlApi } from '../services/controlApi';

export default function ControlPage() {
  const { dashboard, events } = useDashboard();
  const qc = useQueryClient();

  const logsQ = useQuery({
    queryKey: ['control', 'logs'],
    queryFn: controlApi.getLogs,
    refetchInterval: 10_000,
    retry: false,
  });
  const [threshold, setThreshold] = useState(dashboard?.peak_threshold ?? 15);
  const [autoControl, setAutoControl] = useState(true);

  useEffect(() => {
    controlApi.getAutoMode().then(setAutoControl).catch(() => undefined);
  }, []);
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const runAction = async (action: string, payload?: Record<string, unknown>) => {
    setLoading(action);
    setMessage(null);
    try {
      await sendControlAction(action, payload);
      setMessage(`'${action}' 명령이 전송되었습니다.`);
      setTimeout(() => setMessage(null), 3000);
    } catch (err) {
      const isDuplicate = axios.isAxiosError(err) && err.response?.status === 409;
      setMessage(
        isDuplicate
          ? `⏳ '${action}' 명령이 30초 이내에 이미 전송됐습니다. 잠시 후 다시 시도하세요.`
          : `❌ '${action}' 명령 전송에 실패했습니다.`,
      );
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
              <span className="text-sm text-[#98A2B3]">10A</span>
              <span className="text-2xl font-bold text-[#E8A33D]">{threshold.toFixed(1)}A</span>
              <span className="text-sm text-[#98A2B3]">30A</span>
            </div>
            <input
              type="range"
              min={10}
              max={30}
              step={0.5}
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full accent-[#E8A33D]"
            />
            <Button
              loading={loading === 'threshold'}
              onClick={async () => {
                setLoading('threshold');
                try {
                  await controlApi.setThreshold(threshold);
                  setMessage(`임계치 ${threshold.toFixed(1)}A 적용됨`);
                  qc.invalidateQueries({ queryKey: ['dashboard'] });
                } catch {
                  setMessage('❌ 임계치 적용 실패 (로그인 확인)');
                } finally {
                  setLoading(null);
                  setTimeout(() => setMessage(null), 3000);
                }
              }}
            >
              적용
            </Button>
          </div>
        </Card>

        {/* AI Control Toggle */}
        <Card title="AI 자동 제어" subtitle="피크쉐이빙 자동화">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[#E8ECF1] mb-1">자동 제어</p>
              <p className="text-xs text-[#98A2B3]">{autoControl ? 'ON — 피크쉐이빙·시나리오 자동' : 'OFF — 수동 전용'}</p>
            </div>
            <button
              onClick={async () => {
                const next = !autoControl;
                setAutoControl(next);
                try {
                  await controlApi.setAutoMode(next);
                  setMessage(`AI 자동 제어 ${next ? 'ON' : 'OFF'}`);
                } catch {
                  setAutoControl(!next);
                  setMessage('❌ 자동 제어 변경 실패 (로그인 확인)');
                }
                setTimeout(() => setMessage(null), 3000);
              }}
              className={`w-16 h-8 rounded-full transition-colors relative ${
                autoControl ? 'bg-[#2EBD85]' : 'bg-[#222933]'
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
              className="rounded-md border border-[#222933] bg-[#0A0C10] p-4"
            >
              <p className="text-sm font-semibold text-[#E8ECF1] mb-3">{c.device_id}</p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1 px-2 py-1.5 text-xs"
                  loading={loading === `pause_${c.device_id}`}
                  onClick={async () => {
                    setLoading(`pause_${c.device_id}`);
                    try {
                      await controlApi.controlCharger(c.device_id, 'pause');
                      setMessage(`${c.device_id} 일시 정지 명령 전송`);
                      qc.invalidateQueries({ queryKey: ['control', 'logs'] });
                    } catch { setMessage('❌ 명령 실패 (로그인 확인)'); }
                    finally { setLoading(null); setTimeout(() => setMessage(null), 3000); }
                  }}
                >
                  일시 정지
                </Button>
                <Button
                  variant="secondary"
                  className="flex-1 px-2 py-1.5 text-xs"
                  loading={loading === `resume_${c.device_id}`}
                  onClick={async () => {
                    setLoading(`resume_${c.device_id}`);
                    try {
                      await controlApi.controlCharger(c.device_id, 'resume');
                      setMessage(`${c.device_id} 재개 명령 전송`);
                      qc.invalidateQueries({ queryKey: ['control', 'logs'] });
                    } catch { setMessage('❌ 명령 실패 (로그인 확인)'); }
                    finally { setLoading(null); setTimeout(() => setMessage(null), 3000); }
                  }}
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
          <Card title="실시간 제어 로그" subtitle={logsQ.data ? '제어 이력 (10초 갱신)' : '알림 이벤트 기반'}>
            <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
              {logsQ.data && logsQ.data.length > 0 ? (
                logsQ.data.map((log) => {
                  const src = log.triggered_by ?? '';
                  const badge = src === 'ai_auto'
                    ? { t: 'AI 자동', c: 'bg-[#4C8DFF]/10 text-[#4C8DFF]' }
                    : src === 'manual'
                      ? { t: '수동', c: 'bg-[#9B8AFB]/10 text-[#9B8AFB]' }
                      : src.startsWith('scenario')
                        ? { t: '시나리오', c: 'bg-[#E8A33D]/10 text-[#E8A33D]' }
                        : src === 'openadr'
                          ? { t: 'DR', c: 'bg-[#E5484D]/10 text-[#E5484D]' }
                          : { t: src || '시스템', c: 'bg-[#222933]/50 text-[#98A2B3]' };
                  return (
                    <div
                      key={log.id}
                      className="flex items-start gap-3 rounded-md border border-[#222933] bg-[#0A0C10] px-4 py-3"
                    >
                      <div className="mt-1">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${badge.c}`}>
                          {badge.t}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-xs text-[#98A2B3]">
                          {log.created_at ? new Date(log.created_at).toLocaleTimeString('ko-KR', { hour12: false }) : '—'}
                          {' · '}{log.device_id}
                        </p>
                        <p className="text-sm text-[#E8ECF1]">
                          {log.action === 'discharge' ? 'ESS 방전'
                            : log.action === 'charge' ? 'ESS 충전'
                            : log.action === 'standby' ? '대기 전환'
                            : log.action === 'pause' ? '충전기 일시 정지'
                            : log.action === 'resume' ? '충전기 재개'
                            : log.action}
                          {log.ess_soc_before != null && ` (SOC ${log.ess_soc_before}%)`}
                        </p>
                      </div>
                    </div>
                  );
                })
              ) : (events ?? []).length === 0 ? (
                <p className="text-sm text-[#98A2B3]">아직 기록된 이벤트가 없습니다.</p>
              ) : (
                (events ?? []).map((log) => (
                  <div
                    key={log.id}
                    className="flex items-start gap-3 rounded-md border border-[#222933] bg-[#0A0C10] px-4 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-xs text-[#98A2B3]">{log.timestamp}</p>
                      <p className="text-sm text-[#E8ECF1]">{log.message}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>

        {/* Status Panel */}
        <div className="space-y-6">
          {message && (
            <Card>
              <p className="text-sm text-[#E8ECF1]">{message}</p>
            </Card>
          )}

          <Card title="시스템 상태">
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#98A2B3]">그리드 전류</span>
                <span className="text-lg font-bold text-[#4C8DFF]">{dashboard?.grid_current.toFixed(1) || '0.0'}A</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#98A2B3]">ESS SOC</span>
                <span className="text-lg font-bold text-[#2EBD85]">{dashboard?.ess_soc || 0}%</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-[#98A2B3]">피크 상태</span>
                <span className={`text-sm font-semibold ${
                  dashboard?.peak_active ? 'text-[#E8A33D]' : 'text-[#2EBD85]'
                }`}>
                  {dashboard?.peak_active ? '활성' : '정상'}
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
