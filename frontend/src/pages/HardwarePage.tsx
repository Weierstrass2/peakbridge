// 하드웨어 실측 탭 — 로컬 게이트웨이(:5181) 대시보드를 클라우드로 이식한 독립 뷰.
// 데이터: 백엔드 dashboard 응답(브리지 ess-runtime 사이드채널). 어느 기기에서도 열람 가능.
import { useEffect, useRef, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { fetchHardwareStatus, setHwThreshold, type HardwareStatus } from '../services/hardwareApi';

const POLL_MS = 1500;
const STALE_MS = 12_000; // 실기 값이 이만큼 끊기면 '연결 대기'
const BUFFER = 160; // 최근 약 4분(1.5초 간격)
const TRIP_C = 50;
const RELEASE_C = 43;

interface Point {
  t: number;
  current: number;
}

const fmt = (t: number): string =>
  new Date(t).toLocaleTimeString('ko-KR', { hour12: false });

/** 라벨-값 한 줄 (없으면 "—"). */
function Kv({ label, value, unit, danger }: { label: string; value: number | null | undefined; unit: string; danger?: boolean }) {
  const missing = value === null || value === undefined;
  return (
    <div className="flex items-center justify-between border-b border-[#1A1F27] py-2 text-sm last:border-0">
      <span className="text-[#98A2B3]">{label}</span>
      {missing ? (
        <span className="text-[#5A6472]">—</span>
      ) : (
        <span className="font-semibold" style={{ color: danger ? '#E5484D' : '#E6EBF2' }}>
          {value.toFixed(unit === '°C' ? 1 : 3)} {unit}
        </span>
      )}
    </div>
  );
}

export default function HardwarePage() {
  const [status, setStatus] = useState<HardwareStatus | null>(null);
  const [history, setHistory] = useState<Point[]>([]);
  const [lastOk, setLastOk] = useState<number>(0);
  const [thrInput, setThrInput] = useState('');
  const [applying, setApplying] = useState(false);
  const [thrMsg, setThrMsg] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const applyThreshold = async () => {
    const v = parseFloat(thrInput);
    if (!Number.isFinite(v) || v <= 0 || v > 1) {
      setThrMsg('0 초과 1 이하의 값(A)을 입력하세요.');
      return;
    }
    setApplying(true);
    setThrMsg(null);
    try {
      await setHwThreshold(v);
      setThrMsg(`요청됨: ${v.toFixed(3)}A — 몇 초 내 하드웨어에 적용됩니다.`);
    } catch {
      setThrMsg('적용 실패 — 로그인/권한 또는 네트워크를 확인하세요.');
    } finally {
      setApplying(false);
    }
  };

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await fetchHardwareStatus();
        if (!alive) return;
        setStatus(s);
        setLastOk(Date.now());
        if (typeof s.grid_current === 'number') {
          setHistory((prev) => [...prev, { t: Date.now(), current: s.grid_current }].slice(-BUFFER));
        }
      } catch {
        /* 폴링 실패 — 마지막 값 유지(화면 유지) */
      }
    };
    tick();
    timer.current = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      if (timer.current) window.clearInterval(timer.current);
    };
  }, []);

  // 브리지가 relay_state를 올리면 하드웨어 연결로 간주(ess-runtime 30초 신선도).
  const hwConnected = status?.relay_state === 'NC' || status?.relay_state === 'NO';
  const stale = !hwConnected || Date.now() - lastOk > STALE_MS;
  const isPeak = status?.relay_state === 'NO';
  const high = status?.hw_threshold_high_a ?? status?.peak_threshold ?? 0.09;
  const locked = status?.thermal_lock === true;

  const bt = status?.ess_battery_temp_c;
  const it = status?.ess_inverter_temp_c;
  const temps = [bt, it].filter((v): v is number => typeof v === 'number');
  const hottest = temps.length ? Math.max(...temps) : null;

  const card = 'rounded-xl border border-[#222933] bg-[#0A0C10] p-5';

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-[#E6EBF2]">하드웨어 실측 (ESS 피크쉐이빙)</h1>
        <p className="text-sm text-[#98A2B3]">
          로컬 게이트웨이 실측을 클라우드로 중계 · 1.5초 폴링 · 판정은 하드웨어 로컬에서 수행
        </p>
      </div>

      {/* 릴레이 상태 배너 */}
      <div
        className="flex items-center justify-between rounded-xl border p-5"
        style={
          stale
            ? { borderColor: '#222933', background: '#0A0C10' }
            : isPeak
              ? { borderColor: 'rgba(232,163,61,0.4)', background: 'rgba(232,163,61,0.10)' }
              : { borderColor: 'rgba(59,130,246,0.4)', background: 'rgba(59,130,246,0.10)' }
        }
      >
        <div>
          <div className="text-base font-bold" style={{ color: stale ? '#98A2B3' : isPeak ? '#E8A33D' : '#3B82F6' }}>
            {stale ? '연결 대기' : isPeak ? '피크 — ESS 공급 (NO)' : '평상시 — 한전 공급 (NC)'}
          </div>
          <div className="mt-1 text-xs text-[#98A2B3]">
            {stale
              ? '하드웨어 텔레메트리 수신 없음 (게이트웨이/브리지 확인)'
              : `절체 임계 I_high ${high.toFixed(3)}A` +
                (status?.hold_remaining_s && status.hold_remaining_s > 0
                  ? ` · 최소 유지 ${Math.round(status.hold_remaining_s)}초 남음`
                  : '')}
          </div>
        </div>
        <div className="text-2xl font-bold text-[#E6EBF2]">
          {status ? `${status.grid_current.toFixed(3)} A` : '—'}
        </div>
      </div>

      {/* 열 차단 경보 스트립 */}
      {locked && (
        <div
          className="rounded-lg px-4 py-3 text-sm font-semibold"
          style={{ background: 'rgba(229,72,77,0.12)', border: '1px solid rgba(229,72,77,0.45)', color: '#E5484D' }}
        >
          🌡 열 차단 발동 — 과열로 ESS 방전을 정지하고 한전으로 고정했습니다.
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* 전류 차트 */}
        <div className={`${card} lg:col-span-2`}>
          <h2 className="mb-3 text-sm font-semibold text-[#E6EBF2]">계통 전류 (최근 실시간)</h2>
          {history.length === 0 ? (
            <div className="flex h-[300px] items-center justify-center text-sm text-[#5A6472]">
              데이터 수신 대기 중…
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={history} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                <CartesianGrid stroke="#1A1F27" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  scale="time"
                  tickFormatter={fmt}
                  stroke="#8b97a8"
                  fontSize={11}
                  minTickGap={50}
                />
                <YAxis
                  stroke="#8b97a8"
                  fontSize={11}
                  width={62}
                  domain={[0, (max: number) => Math.max(max * 1.2, high * 1.3)]}
                  tickFormatter={(v: number) => v.toFixed(3)}
                  unit="A"
                />
                <Tooltip
                  contentStyle={{ background: '#12161d', border: '1px solid #232a35', borderRadius: 8, fontSize: 12 }}
                  labelFormatter={(v) => fmt(Number(v))}
                  formatter={(v: number) => [`${v.toFixed(4)} A`, '계통 전류']}
                />
                <ReferenceLine
                  y={high}
                  stroke="#E8A33D"
                  strokeDasharray="5 4"
                  label={{ value: `I_high ${high.toFixed(3)}A`, fill: '#E8A33D', fontSize: 11, position: 'insideTopRight' }}
                />
                <Line
                  type="monotone"
                  dataKey="current"
                  stroke="#E6EBF2"
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="space-y-5">
          {/* 절체 임계 설정 (하드웨어 config 전파) */}
          <div className={card}>
            <h2 className="mb-2 text-sm font-semibold text-[#E6EBF2]">절체 임계 설정 (하드웨어)</h2>
            <div className="mb-2 text-xs text-[#98A2B3]">
              현재 하드웨어 임계:{' '}
              <span className="font-semibold text-[#E6EBF2]">
                {status?.hw_threshold_high_a != null ? `${status.hw_threshold_high_a.toFixed(3)} A` : '—'}
              </span>
            </div>
            <div className="flex gap-2">
              <input
                type="number"
                step="0.005"
                min="0.001"
                max="1"
                value={thrInput}
                onChange={(e) => setThrInput(e.target.value)}
                placeholder="예: 0.15"
                className="w-full rounded-md border border-[#222933] bg-[#12161d] px-3 py-2 text-sm text-[#E6EBF2] outline-none focus:border-[#4C8DFF]"
              />
              <button
                type="button"
                onClick={applyThreshold}
                disabled={applying}
                className="shrink-0 rounded-md bg-[#4C8DFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {applying ? '적용 중…' : '적용'}
              </button>
            </div>
            {thrMsg && <div className="mt-2 text-xs text-[#98A2B3]">{thrMsg}</div>}
            <p className="mt-2 text-[11px] text-[#5A6472]">
              XIAO로 MQTT config(retained) 전파 · 절체는 CT&gt;임계, 복귀(NO→NC)는 임계가 아니라 INA219(&lt;850mA)로 판정됩니다.
            </p>
          </div>

          {/* ESS 계측 */}
          <div className={card}>
            <h2 className="mb-2 text-sm font-semibold text-[#E6EBF2]">ESS 계측</h2>
            <Kv label="배터리 잔량 (SOC)" value={status?.ess_soc} unit="%" />
            <Kv label="INA219 전류" value={status?.ess_ina_current_ma} unit="mA" />
            <Kv label="잔여 가동시간" value={status?.ess_remain_hours} unit="h" />
            <p className="mt-2 text-[11px] text-[#5A6472]">
              INA219 = 복귀 판단 센서 (인버터→부하 전류). 미장착·미연결 시 「—」.
            </p>
          </div>

          {/* 온도 · 열 차단 */}
          <div className={card}>
            <h2 className="mb-2 text-sm font-semibold text-[#E6EBF2]">온도 · 열 차단 (BME280)</h2>
            <div
              className="mb-2 rounded-md px-3 py-2 text-sm font-semibold"
              style={
                locked
                  ? { background: 'rgba(229,72,77,0.12)', color: '#E5484D', border: '1px solid rgba(229,72,77,0.4)' }
                  : { background: 'rgba(46,189,133,0.10)', color: '#2EBD85', border: '1px solid rgba(46,189,133,0.3)' }
              }
            >
              {locked ? '⚠ 열 차단 발동 (과열, 한전 고정)' : '정상 (열 차단 대기)'}
            </div>
            <Kv label="배터리 옆 온도" value={bt} unit="°C" danger={typeof bt === 'number' && bt >= TRIP_C} />
            <Kv label="인버터 옆 온도" value={it} unit="°C" danger={typeof it === 'number' && it >= TRIP_C} />
            <p className="mt-2 text-[11px] text-[#5A6472]">
              트립 {TRIP_C}°C / 해제 {RELEASE_C}°C · 더 뜨거운 값으로 판정
              {hottest !== null && ` · 현재 최고 ${hottest.toFixed(1)}°C`}
            </p>
          </div>
        </div>
      </div>

      <p className="text-[11px] text-[#5A6472]">
        ※ 절체 이력(이벤트) 그래프 마커는 클라우드에 릴레이 이벤트 저장소가 없어 이 탭에서는 생략됩니다.
        상세 이력은 로컬 게이트웨이 대시보드에서 확인하세요.
      </p>
    </div>
  );
}
