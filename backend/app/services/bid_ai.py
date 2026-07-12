"""학습된 입찰 정책 서빙 — CEM 학습 가중치(models/bid_policy.json), numpy 추론."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import structlog
from app.core.resources import MARKET_RULES, ess_resources

logger = structlog.get_logger(__name__)
_MODEL: dict | None = None

def _load():
    global _MODEL
    if _MODEL is None:
        p = Path(__file__).resolve().parents[2] / "models" / "bid_policy.json"
        _MODEL = json.load(open(p))
        logger.info("bid_policy_loaded", eval=_MODEL.get("eval"))
    return _MODEL

def ai_bids(forecast: list[float], soc: dict[str, float] | None = None) -> dict:
    m = _load()
    n_in, n_h, _ = m["arch"]
    th = np.array(m["weights"])
    W1 = th[:n_in*n_h].reshape(n_in, n_h); b1 = th[n_in*n_h:n_in*n_h+n_h]
    o = n_in*n_h+n_h; W2 = th[o:o+n_h*2].reshape(n_h, 2); b2 = th[o+n_h*2:]
    power = sum(r["max_discharge_kw"] for r in ess_resources().values())
    res = ess_resources()
    e_use = sum(
        max(0.0, ((soc or {}).get(k, 60.0) - r["soc_min"])) / 100 * r["capacity_kwh"]
        for k, r in res.items()
    )
    cap = MARKET_RULES["price_cap"]
    mx = max(forecast); rank = np.argsort(np.argsort(forecast)) / 23.0
    bids = []
    for h in range(24):
        x = np.array([forecast[h]/mx, math.sin(2*math.pi*h/24), math.cos(2*math.pi*h/24),
                      rank[h], e_use/(power*24)])
        hdn = np.tanh(x @ W1 + b1); q, p = 1/(1+np.exp(-(hdn @ W2 + b2)))
        qty = round(float(q) * power / 10) * 10 if q > 0.35 else 0
        bids.append({"hour": h, "qty_kw": float(qty),
                     "price": round(min(cap, forecast[h]*(0.75+0.24*float(p))), 1)})
    return {"model": "CEM-RL bid policy (10yr KPX)", "eval": m["eval"],
            "usable_kwh": round(e_use, 1), "bids": bids}
