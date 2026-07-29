import { useEffect, useState } from 'react';
import axios from 'axios';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import { useDashboard } from '../hooks/useDashboard';
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
  const [threshold, setThreshold] = useState(dashboard?.peak_threshold ?? 0.095);
  const [autoControl, setAutoControl] = useState(true);

  useEffect(() => {
    controlApi.getAutoMode().then(setAutoControl).catch(() => undefined);
  }, []);
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // 강제 방전 on/off — 실증 하드웨어(XIAO)로 실제 전파되는 명령.
  // on: 부하3 유무와 무관하게 릴레이 NO(ESS) 유지 / off: 자동 판단 복귀.
  const runForceDischarge = async (on: boolean) => {
    setLoading(on ? 'discharge' : 'standby');
    setMessage(null);
    try {
      await controlApi.setForceDischarge(on);
      setMessage(
        on
          ? '강제 방전 ON — 부하 무관 ESS(NO) 유지 명령 전송'
          : '강제 방전 해제 — 자동 판단 복귀',
      );
      setTimeout(() => setMessage(null), 3000);
    } catch (err) {
      const isAuth = axios.isAxiosError(err) && err.response?.status === 401;
      setMessage(isAuth ? '❌ 관리자 로그인이 필요합니다.' : '❌ 명령 전송에 실패했습니다.');
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
        <Card title="ESS 제어" subtitle="실증 하드웨어 직접 제어">
          <div className="grid grid-cols-2 gap-3">
            <Button
              loading={loading === 'discharge'}
              onClick={() => runForceDischarge(true)}
            >
              강제 방전
            </Button>
            <Button
              variant="secondary"
              loading={loading === 'standby'}
              onClick={() => runForceDischarge(false)}
            >
              대기
            </Button>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-[#5A6472]">
            강제 방전: 부하 유무와 무관하게 릴레이를 ESS(NO)로 전환·유지합니다.
            대기: 자동 판단으로 복귀(부하 없으면 한전으로). SOC 15% 미만 시 안전 자동 해제.
          </p>
        </Card>

        {/* Peak Threshold Slider */}
        <Card title="피크 임계치" subtitle="그리드 전류 제한">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#98A2B3]">0.02A</span>
              <span className="text-2xl font-bold text-[#E8A33D]">{threshold.toFixed(3)}A</span>
              <span className="text-sm text-[#98A2B3]">0.20A</span>
            </div>
            <input
              type="range"
              min={0.02}
              max={0.2}
              step={0.005}
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
                  setMessage(`임계치 ${threshold.toFixed(3)}A 적용됨`);
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
