/** CO2 절감량(kg) 표시 포맷 — 실증 스케일에선 g 단위가 나온다.
 *  백엔드가 원시 부동소수점(예: 0.00033648140624999986)을 그대로 주므로
 *  여기서 자릿수를 정리하지 않으면 KPI 카드 폭을 넘친다. */
export function formatCo2Kg(kg: number | null | undefined): string {
  const v = kg ?? 0;
  if (v <= 0) return '0kg';
  if (v >= 1) return `${v.toFixed(1)}kg`;
  const g = v * 1000;
  return `${g.toFixed(g >= 10 ? 0 : 2)}g`;
}
