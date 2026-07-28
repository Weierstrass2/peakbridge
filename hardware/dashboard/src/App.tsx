import { useCallback, useEffect, useRef, useState } from 'react';
import { CurrentChart } from './components/CurrentChart';
import { ConfigForm } from './components/ConfigForm';
import { DevicePicker } from './components/DevicePicker';
import { EssPanel } from './components/EssPanel';
import { EventLog } from './components/EventLog';
import { RelayStateBanner } from './components/RelayStateBanner';
import type { Config, DeviceInfo, RelayEvent, Telemetry } from './lib/api';
import { hardwareApi } from './lib/api';

const STALE_MS = 10_000; // 최신 텔레메트리가 10초 이상 끊기면 "연결 대기"

/** 폴링 헬퍼 — 실패해도 화면을 깨뜨리지 않고 마지막 값을 유지한다. */
function usePoll(fn: () => void, intervalMs: number, deps: unknown[] = []) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    saved.current();
    const id = setInterval(() => saved.current(), intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
}

export default function App() {
  const [latest, setLatest] = useState<Telemetry | null>(null);
  const [history, setHistory] = useState<Telemetry[]>([]);
  const [events, setEvents] = useState<RelayEvent[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [device, setDevice] = useState<string | null>(null); // null = 전체
  const [now, setNow] = useState(Date.now());

  const target = device ?? undefined;

  // /api/latest 1초 (배너·hold 카운트다운)
  usePoll(
    () => {
      hardwareApi
        .latest(target)
        .then(setLatest)
        .catch(() => setLatest(null)); // 404 = 아직 수신 없음
      setNow(Date.now());
    },
    1000,
    [target],
  );

  // /api/history 2초 (그래프)
  usePoll(
    () => {
      hardwareApi.history(10, target).then(setHistory).catch(() => undefined);
    },
    2000,
    [target],
  );

  // /api/events 5초 + 디바이스 목록
  usePoll(
    () => {
      hardwareApi.events(target).then(setEvents).catch(() => undefined);
      hardwareApi.devices().then(setDevices).catch(() => undefined);
    },
    5000,
    [target],
  );

  useEffect(() => {
    hardwareApi.getConfig().then(setConfig).catch(() => undefined);
  }, []);

  const handleSaved = useCallback((cfg: Config) => setConfig(cfg), []);

  const stale = latest ? now - latest.received_at * 1000 > STALE_MS : true;
  // 임계선은 해당 디바이스가 실제로 보고한 값을 우선한다.
  // (구성 B(building-A)는 전류 스케일이 달라 데모 config와 임계값이 다르다)
  const high = latest?.threshold_high_a ?? config?.threshold_high_a ?? 0.09;
  const low = latest?.threshold_low_a ?? config?.threshold_low_a ?? 0.055;

  return (
    <div className="app">
      <div className="topbar">
        <h1>PeakBridge — ESS 피크쉐이빙 실증</h1>
        <div className="sub">
          {latest ? `device ${latest.device_id}` : 'device —'} · 로컬 폐쇄망 · 1Hz 텔레메트리
        </div>
      </div>

      <DevicePicker devices={devices} selected={device} onSelect={setDevice} />

      <RelayStateBanner latest={latest} stale={stale} />

      <div className="grid">
        <div className="stack">
          <div className="card">
            <h2>계통 전류 (최근 10분)</h2>
            <CurrentChart history={history} events={events} thresholdHigh={high} thresholdLow={low} />
          </div>
          <div className="card">
            <h2>절체 이력</h2>
            <EventLog events={events} />
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <h2>임계값 설정</h2>
            <ConfigForm onSaved={handleSaved} />
          </div>
          <div className="card">
            <h2>ESS 계측</h2>
            <EssPanel latest={latest} />
          </div>
        </div>
      </div>
    </div>
  );
}
