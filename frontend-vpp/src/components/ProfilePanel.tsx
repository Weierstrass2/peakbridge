import { useEffect, useState } from 'react';
import { consoleApi, type MarketProfile, type MarketProfileCompare } from '../lib/api';

/** 시장 프로파일 — 같은 자원을 어느 시장 문법으로 참여시키는가.
 *
 *  이 화면을 두는 이유는 명확하다.
 *  콘솔에는 '24구간 가격입찰' 화면이 있는데, **현행 육지 시장에는 가격입찰이 없다.**
 *  KPX가 변동비 순으로 SMP를 정해 통보하는 구조(CBP)이기 때문이다.
 *  그 사실을 우리가 먼저 밝히지 않으면, 심사에서 지적당했을 때 방어가 안 된다.
 *
 *  그래서 여기서 두 시장의 문법 차이를 명시적으로 보여주고,
 *  "엔진은 하나, 시장 문법만 갈아끼운다"는 구조를 드러낸다. */
export default function ProfilePanel() {
  const [d, setD] = useState<MarketProfileCompare | null>(null);
  const [sel, setSel] = useState<string>('inland_cbp');

  useEffect(() => {
    consoleApi.marketProfiles().then((r) => setD(r.data)).catch(() => { /* 조용히 */ });
  }, []);

  if (!d) return <div className="prof"><p className="prof-load">시장 프로파일 불러오는 중…</p></div>;

  const inland = d.profiles.find((p) => p.key === 'inland_cbp');
  const jeju = d.profiles.find((p) => p.key === 'jeju_pilot');
  const cur: MarketProfile | undefined = d.profiles.find((p) => p.key === sel);

  return (
    <div className="prof">
      {/* ── 핵심 경고: 육지엔 가격입찰이 없다 ── */}
      <div className="prof-alert">
        <b>현행 육지 시장(CBP)에는 가격입찰이 없습니다.</b>
        <span>
          발전사는 공급가능용량만 제출하고 KPX가 변동비 순으로 급전순위와 SMP를 결정해 통보합니다.
          콘솔의 24구간 가격입찰 화면은 <b>제주 시범사업 · 향후 가격입찰제(PBP)</b> 기준입니다.
        </span>
      </div>

      {/* ── 두 시장 나란히 ── */}
      <div className="prof-two">
        {[inland, jeju].map((p) =>
          p ? (
            <button
              key={p.key}
              type="button"
              className={`prof-card ${sel === p.key ? 'on' : ''}`}
              onClick={() => setSel(p.key)}
            >
              <div className="pc-head">
                <b>{p.name}</b>
                <span className={`pc-st ${p.status}`}>
                  {p.status === 'live' ? '운영 중' : p.status === 'pilot' ? '시범사업' : '예정'}
                </span>
              </div>
              <dl className="pc-dl">
                <dt>자원 지위</dt><dd>{p.role}</dd>
                <dt>입찰 문법</dt><dd>{p.bidding}</dd>
                <dt>가격 예측 용도</dt><dd>{p.price_use}</dd>
                <dt>정산</dt><dd>{p.settlement}</dd>
                <dt>미이행</dt><dd>{p.penalty}</dd>
              </dl>
            </button>
          ) : null,
        )}
      </div>

      {/* ── 선택 프로파일의 수익원 ── */}
      {cur && (
        <div className="prof-sect">
          <div className="js-head">
            <b>수익원 — {cur.name}</b>
            <span className="js-sub">현행 제도에서 지금 가능한 것과 아닌 것</span>
          </div>
          <table className="jeju-tb">
            <thead>
              <tr>
                <th>수익원</th>
                <th>정산 근거</th>
                <th className="r">현재 가능</th>
              </tr>
            </thead>
            <tbody>
              {cur.streams.map((s) => (
                <tr key={s.key}>
                  <td>
                    <b>{s.label}</b>
                    {s.note && <div className="pc-note">{s.note}</div>}
                  </td>
                  <td>{s.basis}</td>
                  <td className="r">
                    <span className={`pc-flag ${s.available ? 'yes' : 'no'}`}>
                      {s.available ? '가능' : '자격 필요'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 공용 엔진 ── */}
      <div className="prof-sect">
        <div className="js-head">
          <b>두 시장이 공유하는 엔진</b>
          <span className="js-sub">시장 문법만 갈아끼운다 — 자산이 어디 있든 같은 두뇌</span>
        </div>
        <div className="prof-eng">
          {d.shared_engine.map((e) => (
            <span className="pe-chip" key={e}>{e}</span>
          ))}
        </div>
        <p className="jeju-verdict">{d.note}</p>
      </div>

      {/* ── 항목별 대조표 ── */}
      <div className="prof-sect">
        <div className="js-head"><b>항목별 대조</b></div>
        <table className="jeju-tb">
          <thead>
            <tr><th>항목</th><th>육지 (현행 CBP)</th><th>제주 (시범사업)</th></tr>
          </thead>
          <tbody>
            {d.comparison.map((c) => (
              <tr key={c.item}>
                <td><b>{c.item}</b></td>
                <td>{c.inland}</td>
                <td>{c.jeju}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
