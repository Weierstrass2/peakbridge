"""과최적화 진단 — "이겼다"와 "운이 좋았다"를 구분한다.

퀀트에서 백테스트 성과를 그대로 믿지 않는 이유는 단순하다.
**전략을 여러 개 시험하면, 그중 하나는 우연히 좋아 보인다.**
11개 전략을 돌려 1등을 고르는 행위 자체가 성과를 부풀린다.

두 가지 표준 진단을 구현한다.

1) Deflated Sharpe Ratio (DSR)
   시행 횟수 N을 반영해 "이 정도 Sharpe는 우연히도 나올 수 있는가"를 확률로 답한다.
   기대 최대 Sharpe(SR0)를 구하고, 관측 Sharpe가 그보다 유의하게 큰지 검정한다.

2) PBO (Probability of Backtest Overfitting)
   조합적 교차검증(CSCV): 기간을 S조각으로 나눠 절반을 학습(IS), 절반을 검증(OOS)으로
   삼는 모든 조합에서 "IS 1등이 OOS에서 중앙값 아래로 떨어지는 비율"을 센다.
   이 비율이 높으면 순위가 우연이라는 뜻이다.

참고: Bailey & López de Prado의 정의를 따르되, scipy 없이 numpy만으로 계산한다
      (배포 경량화 원칙).
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np

EULER = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """표준정규 분위수 — Acklam 근사 (scipy 대체)."""
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def sharpe(pnl: np.ndarray) -> float:
    sd = float(pnl.std(ddof=1))
    return float(pnl.mean() / sd) if sd > 0 else 0.0


def deflated_sharpe(pnl: list[float], n_trials: int, periods_per_year: int = 365) -> dict:
    """시행 횟수를 보정한 Sharpe 유의성.

    n_trials: 실제로 시험한 전략(또는 파라미터 조합) 개수.
              우리는 리더보드에 올린 전략 수를 넣는다.
    """
    p = np.asarray(pnl, dtype=float)
    n = len(p)
    if n < 10:
        return {"error": "표본 부족 (10일 이상 필요)"}

    sr = sharpe(p)                                   # 일 단위 Sharpe
    sr_ann = sr * math.sqrt(periods_per_year)

    # 왜도·첨도 — 비정규 분포를 보정하는 항
    mu, sd = float(p.mean()), float(p.std(ddof=1)) or 1e-9
    z = (p - mu) / sd
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())

    # 기대 최대 Sharpe: N번 시험하면 우연만으로도 이 정도는 나온다
    if n_trials > 1:
        e_max = ((1 - EULER) * _norm_ppf(1 - 1 / n_trials)
                 + EULER * _norm_ppf(1 - 1 / (n_trials * math.e)))
    else:
        e_max = 0.0
    sr0 = e_max / math.sqrt(periods_per_year)        # 일 단위로 환산한 기준선

    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    dsr = _norm_cdf((sr - sr0) * math.sqrt(n - 1) / denom)

    return {
        "observed_sharpe_daily": round(sr, 4),
        "observed_sharpe_annual": round(sr_ann, 2),
        "trials": n_trials,
        "expected_max_sharpe_annual": round(e_max, 2),
        "deflated_sharpe_prob": round(dsr, 4),
        "significant": bool(dsr > 0.95),
        "skew": round(skew, 3),
        "kurtosis": round(kurt, 3),
        "samples": n,
        "verdict": (
            "우연으로 설명하기 어려움 (유의)" if dsr > 0.95
            else "우연일 가능성 배제 못함" if dsr > 0.75
            else "우연히 이겼을 가능성이 큼"
        ),
    }


def pbo(pnl_matrix: dict[str, list[float]], n_splits: int = 8) -> dict:
    """조합적 교차검증(CSCV) 기반 과최적화 확률.

    pnl_matrix: {전략명: 일별 손익 리스트} — 모든 전략이 같은 기간이어야 한다.
    n_splits:   기간 분할 수 (짝수). 조합 수는 C(S, S/2).
    """
    names = list(pnl_matrix.keys())
    if len(names) < 2:
        return {"error": "전략이 2개 이상 필요"}
    m = np.asarray([pnl_matrix[k] for k in names], dtype=float)   # (전략수, 일수)
    n_days = m.shape[1]
    if n_days < n_splits * 3:
        n_splits = max(4, (n_days // 3) // 2 * 2)
    if n_days < 12:
        return {"error": "표본 부족"}

    blocks = np.array_split(np.arange(n_days), n_splits)
    half = n_splits // 2
    logits = []
    lose_count = 0
    total = 0

    for combo in combinations(range(n_splits), half):
        is_idx = np.concatenate([blocks[i] for i in combo])
        oos_idx = np.concatenate([blocks[i] for i in range(n_splits) if i not in combo])

        is_sr = np.array([sharpe(m[k, is_idx]) for k in range(len(names))])
        oos_sr = np.array([sharpe(m[k, oos_idx]) for k in range(len(names))])

        best = int(np.argmax(is_sr))                  # 학습 구간 1등
        # 그 전략이 검증 구간에서 몇 등인가 (상대순위 0~1)
        rank = float((oos_sr < oos_sr[best]).sum()) / max(1, len(names) - 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(rank / (1 - rank)))
        if rank < 0.5:
            lose_count += 1
        total += 1

    arr = np.asarray(logits)
    return {
        "pbo": round(lose_count / total, 3),
        "combinations": total,
        "splits": n_splits,
        "strategies": len(names),
        "median_logit": round(float(np.median(arr)), 3),
        "verdict": (
            "과최적화 위험 낮음" if lose_count / total < 0.25
            else "주의 — 순위가 기간에 따라 흔들림" if lose_count / total < 0.5
            else "과최적화 강하게 의심됨"
        ),
    }
