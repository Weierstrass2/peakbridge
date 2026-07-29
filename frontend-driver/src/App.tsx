/**
 * 차주 화면 (/drive) — 폰으로 QR 접속해 충전 세션을 등록한다.
 *
 * 로그인 없음(시연 마찰 제거) · 세대 코드로만 식별.
 * 등록 즉시 백엔드 유연성 재고에 반영되고, 그 재고를 관제(/app)와
 * VPP OS(/console)가 같은 API로 읽는다 — 목업 데이터 없음.
 */
import { useCallback, useEffect, useState } from 'react';

import { api, type ChargeMode, type DriveSession } from './lib/api';

/** 새로고침해도 세션이 유지되도록 코드만 로컬에 남긴다. */
const STORE_KEY = 'peakbridge.drive.code';
const readStored = (): string => {
  try {
    return localStorage.getItem(STORE_KEY) ?? '';
  } catch {
    return '';
  }
};
const writeStored = (code: string) => {
  try {
    code ? localStorage.setItem(STORE_KEY, code) : localStorage.removeItem(STORE_KEY);
  } catch {
    /* 사파리 프라이빗 모드 등 — 무시 */
  }
};

/** 기본 출발 시각: 지금부터 8시간 뒤(정시) — 대부분 '내일 아침 출근'. */
function defaultDepart(): string {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:00`;
}

function BrandBar() {
  return (
    <div className="brandbar">
      {/* 화이트라벨: 제휴 CPO 브랜드가 들어갈 자리 */}
      <div className="logo-slot">제휴 CPO 로고 자리</div>
      <div className="powered">
        powered by
        <br />
        <b>PeakBridge</b>
      </div>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<DriveSession | null>(null);
  const [household, setHousehold] = useState('');
  const [depart, setDepart] = useState(defaultDepart);
  const [needKwh, setNeedKwh] = useState(40);
  const [mode, setMode] = useState<ChargeMode>('eco');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [flexKwh, setFlexKwh] = useState<number | null>(null);

  /* 새로고침 복구 — 저장된 코드가 살아있는 세션이면 완료 화면으로 */
  useEffect(() => {
    const code = readStored();
    if (!code) return;
    api
      .getSession(code)
      .then((s) => {
        if (s?.code && s.status === 'active') setSession(s);
        else writeStored('');
      })
      .catch(() => writeStored(''));
  }, []);

  /* 완료 화면에서만 유연성 재고를 폴링 — "내 40kWh가 시장에 잡혔다"를 눈으로 */
  const pollFlex = useCallback(() => {
    api
      .flexibility(session?.building_id)
      .then((f) => setFlexKwh(f.flex_kwh))
      .catch(() => undefined);
  }, [session?.building_id]);

  useEffect(() => {
    if (!session) return;
    pollFlex();
    const t = setInterval(pollFlex, 4000);
    return () => clearInterval(t);
  }, [session, pollFlex]);

  async function submit() {
    setBusy(true);
    setError('');
    try {
      const s = await api.createSession({ household, need_kwh: needKwh, depart, mode });
      if (s.error) throw new Error(s.error);
      writeStored(s.code);
      setSession(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : '등록에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!session) return;
    setBusy(true);
    try {
      await api.cancelSession(session.code);
    } catch {
      /* 취소 실패해도 화면은 되돌린다 — 시연 중 막히지 않게 */
    } finally {
      writeStored('');
      setSession(null);
      setFlexKwh(null);
      setBusy(false);
    }
  }

  /* ── 완료 화면 ── */
  if (session) {
    const eco = session.mode === 'eco';
    return (
      <div className="shell">
        <BrandBar />
        <div className="done-mark">✓</div>
        <div className="center">
          <div className="sub" style={{ margin: 0 }}>충전 예약 완료</div>
          <div className="code">{session.code}</div>
          <div className="sub">{session.household}세대 · {session.created_at} 접수</div>
        </div>

        <div className="card">
          <div className="row"><span className="k">필요 전력량</span><span className="v">{session.need_kwh} kWh</span></div>
          <div className="row"><span className="k">출발 시각</span><span className="v">{session.depart || '미지정'}</span></div>
          <div className="row"><span className="k">충전 방식</span><span className="v">{session.mode_label}</span></div>
        </div>

        {eco ? (
          <div className="card live">
            <div className="k" style={{ fontSize: 12, color: 'var(--muted)' }}>
              <span className="pulse" />단지 유연성 재고 (실시간)
            </div>
            <div className="big">{flexKwh === null ? '—' : flexKwh.toFixed(1)} <span style={{ fontSize: 16 }}>kWh</span></div>
            <div className="d" style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>
              내 <b style={{ color: 'var(--text)' }}>{session.need_kwh}kWh</b>가 단지 유연성으로 잡혔습니다.
              관제실과 VPP 전력시장 화면에 지금 반영되어 있습니다.
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="d" style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.6 }}>
              즉시 충전은 바로 전력을 채우므로 유연성 재고에는 잡히지 않습니다.
              다음엔 알뜰 충전을 선택하면 요금 절감에 참여할 수 있습니다.
            </div>
          </div>
        )}

        <div className="spacer" />
        <button className="ghost" onClick={cancel} disabled={busy}>
          예약 취소
        </button>
      </div>
    );
  }

  /* ── 입력 화면 ── */
  const valid = needKwh > 0 && household.trim().length > 0;
  return (
    <div className="shell">
      <BrandBar />
      <h1>충전 예약</h1>
      <p className="sub">출발 시각까지만 채우면 되는 전력은 단지 전체의 요금 절감에 쓰입니다.</p>

      {error && <div className="err">{error}</div>}

      <div className="field">
        <label className="label" htmlFor="hh">세대 (동·호수)</label>
        <input
          id="hh"
          type="text"
          inputMode="numeric"
          placeholder="예: 1203"
          value={household}
          maxLength={20}
          onChange={(e) => setHousehold(e.target.value)}
        />
      </div>

      <div className="field">
        <label className="label" htmlFor="dp">출발 시각</label>
        <input id="dp" type="time" value={depart} onChange={(e) => setDepart(e.target.value)} />
      </div>

      <div className="field">
        <span className="label">필요 전력량</span>
        <div className="stepper">
          <button type="button" aria-label="감소" onClick={() => setNeedKwh((v) => Math.max(5, v - 5))}>−</button>
          <div className="val">{needKwh}<small>kWh</small></div>
          <button type="button" aria-label="증가" onClick={() => setNeedKwh((v) => Math.min(200, v + 5))}>+</button>
        </div>
      </div>

      <div className="field">
        <span className="label">충전 방식</span>
        <div className="modes">
          <button
            type="button"
            className="mode"
            data-kind="eco"
            data-on={mode === 'eco'}
            onClick={() => setMode('eco')}
          >
            <div className="t">알뜰 충전</div>
            <div className="d">출발 전까지만 채웁니다. 단지 유연성으로 잡혀 요금 절감에 참여합니다.</div>
          </button>
          <button
            type="button"
            className="mode"
            data-kind="now"
            data-on={mode === 'now'}
            onClick={() => setMode('now')}
          >
            <div className="t">즉시 충전</div>
            <div className="d">지금 바로 최대 출력으로 채웁니다. 유연성에는 잡히지 않습니다.</div>
          </button>
        </div>
      </div>

      <div className="spacer" />
      <button className="cta" onClick={submit} disabled={!valid || busy}>
        {busy ? '등록 중…' : '예약하기'}
      </button>
    </div>
  );
}
