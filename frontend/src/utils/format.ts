/** CO2 절감량(kg) 표시 포맷 — 실증 스케일에선 g 단위가 나온다.
 *  백엔드가 원시 부동소수점(예: 0.00033648140624999986)을 그대로 주므로
 *  여기서 자릿수를 정리하지 않으면 KPI 카드 폭을 넘친다. */
/** 절감액(원) 표시 포맷 — 실측 스케일(1원 미만 소수)부터 아파트 스케일까지.
 *  toLocaleString은 소수를 최대 3자리 그대로 노출해(예: 0.187원) 지저분하다. */
export function formatWon(won: number | null | undefined): string {
  const v = won ?? 0;
  if (v >= 1000) return `${Math.round(v).toLocaleString('ko-KR')}원`;
  if (v > 0) return `${Number(v.toFixed(2))}원`;
  return '0원';
}

export function formatCo2Kg(kg: number | null | undefined): string {
  const v = kg ?? 0;
  if (v <= 0) return '0kg';
  if (v >= 1) return `${v.toFixed(1)}kg`;
  const g = v * 1000;
  return `${g.toFixed(g >= 10 ? 0 : 2)}g`;
}
