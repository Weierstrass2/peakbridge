import { useEffect, useState } from 'react';
import { consoleApi, type DataSource } from '../lib/api';

/** 데이터 출처 배지 — 지금 화면의 숫자가 실측인지 모델인지 항상 드러낸다.
 *
 *  이 배지를 두는 이유는 방어가 아니라 규율이다.
 *  실제로 이 프로젝트에서 '시간별 SMP'라는 이름의 더미 파일(완전한 직선)을
 *  실측으로 오인한 적이 있다. 사람이 매번 확인하는 방식은 실패한다.
 *  화면이 스스로 출처를 말하게 해야 한다. */
export default function SourceBadge() {
  const [ds, setDs] = useState<DataSource | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const load = async () => {
      try { setDs((await consoleApi.dataSource()).data); } catch { /* 조용히 숨김 */ }
    };
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  if (!ds) return null;
  const live = ds.source === 'kpx';

  return (
    <div className="srcb-wrap">
      <button
        type="button"
        className={`srcb ${live ? 'live' : 'model'}`}
        onClick={() => setOpen((v) => !v)}
        title="가격 데이터 출처"
      >
        <span className="srcb-dot" />
        {live ? 'KPX 실측' : '모델 데이터'}
      </button>

      {open && (
        <div className="srcb-pop">
          <div className="srcb-row">
            <span>가격 출처</span>
            <b style={{ color: live ? 'var(--ok)' : 'var(--warn)' }}>{ds.label}</b>
          </div>
          <div className="srcb-row">
            <span>지역 기준</span>
            <b>{ds.region === 'jeju' ? '제주' : '육지'}</b>
          </div>
          <div className="srcb-row">
            <span>SMP CSV</span>
            <b>{ds.csv_exists ? '있음' : '없음'}</b>
          </div>
          {ds.calibration && (
            <div className="srcb-row">
              <span>보정 기간</span>
              <b>{ds.calibration}</b>
            </div>
          )}
          {ds.last_error && <p className="srcb-err">{ds.last_error}</p>}

          <p className="srcb-note">
            <b>실측</b> — 단지 계측(ESP32), KPX 월별 SMP 301개월, KPX 수요 10년, 한전 요금표<br />
            <b>모델</b> — 시장 체결가·낙찰·정산. 실측값으로 캘리브레이션한 시뮬레이션이며
            시장 참여 자격이 없어 실거래 데이터는 확보 불가.
          </p>
          <p className="srcb-note dim">{ds.hint}</p>
        </div>
      )}
    </div>
  );
}
