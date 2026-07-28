import { useEffect, useState } from 'react';
import type { Config } from '../lib/api';
import { ApiError, hardwareApi, validateConfig } from '../lib/api';

/** 설정 폼.
 *  마운트 시 1회 + 저장 성공 후에만 서버 값을 다시 읽는다.
 *  (폴링으로 덮어쓰면 입력 중인 값이 지워진다) */
export function ConfigForm({ onSaved }: { onSaved: (cfg: Config) => void }) {
  const [high, setHigh] = useState('');
  const [low, setLow] = useState('');
  const [hold, setHold] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = (cfg: Config) => {
    setHigh(String(cfg.threshold_high_a));
    setLow(String(cfg.threshold_low_a));
    setHold(String(cfg.min_hold_s));
  };

  useEffect(() => {
    hardwareApi
      .getConfig()
      .then(load)
      .catch(() => setMsg({ kind: 'err', text: '서버에서 설정을 읽지 못했습니다.' }));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = {
      threshold_high_a: Number(high),
      threshold_low_a: Number(low),
      min_hold_s: Number(hold),
    };

    // 클라이언트 검증 = 서버·펌웨어와 동일 규칙
    const reason = validateConfig(body);
    if (reason) {
      setMsg({ kind: 'err', text: reason });
      return;
    }

    setSaving(true);
    try {
      const saved = await hardwareApi.putConfig(body);
      load(saved);
      onSaved(saved);
      setMsg({ kind: 'ok', text: '저장되었습니다. 다음 통신에서 ESP32에 반영됩니다.' });
    } catch (err) {
      const text =
        err instanceof ApiError ? `${err.status === 422 ? '' : `[${err.status}] `}${err.message}` : '저장 실패';
      setMsg({ kind: 'err', text });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="high">절체 임계값 I_high (A)</label>
        <input id="high" value={high} onChange={(e) => setHigh(e.target.value)} inputMode="decimal" />
      </div>
      <div className="field">
        <label htmlFor="low">복귀 임계값 I_low (A)</label>
        <input id="low" value={low} onChange={(e) => setLow(e.target.value)} inputMode="decimal" />
      </div>
      <div className="field">
        <label htmlFor="hold">최소 유지시간 (초, 5~300)</label>
        <input id="hold" value={hold} onChange={(e) => setHold(e.target.value)} inputMode="numeric" />
      </div>
      <button type="submit" disabled={saving}>
        {saving ? '저장 중…' : '설정 저장'}
      </button>
      {msg && <div className={`msg ${msg.kind === 'ok' ? 'ok' : 'err'}`}>{msg.text}</div>}
    </form>
  );
}
