"""Cross-instrument propagation (spec section 32).

Builds a point-in-time instrument graph from trailing return correlation and turnover
similarity, then propagates risk one step across it. The propagated value becomes a
feature -- "how much risk is present in the neighbourhood of this instrument" -- and the
paths are retained so a propagation claim can be shown rather than asserted.

Point-in-time: the graph for decision date *t* is estimated on the window ending at
*t - 1*. Using the window ending at *t* would let today's co-movement, which is partly
caused by the very event being detected, define the neighbourhood that then "predicts"
it.

Sector membership is *not* used. It is not present in the bhavcopy and no licence-clear
NSE sector mapping was located, so the graph is purely statistical. That is limitation
L-07, and it means a propagation edge is a co-movement relationship and nothing more --
never a supply-chain or ownership claim.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PROPAGATION_VERSION = "propagation-v1"


@dataclass
class GraphConfig:
    lookback: int = 126
    top_k: int = 8
    min_abs_corr: float = 0.25
    #: How much of a neighbour's risk crosses an edge. One step only: multi-step
    #: diffusion on a correlation graph mostly re-derives the market factor.
    transfer: float = 0.5


def correlation_graph(panel: pd.DataFrame, as_of: pd.Timestamp,
                      cfg: GraphConfig = GraphConfig()) -> pd.DataFrame:
    """Edges for one date. Returns ``(source, target, weight)``, weight in [0, 1]."""
    hist = panel[panel["date"] < as_of]
    if hist.empty:
        return pd.DataFrame(columns=["source", "target", "weight"])
    dates = np.sort(hist["date"].unique())[-cfg.lookback:]
    hist = hist[hist["date"].isin(dates)]
    wide = hist.pivot_table(index="date", columns="symbol", values="logret")
    wide = wide.dropna(axis=1, thresh=int(0.8 * len(wide)))
    if wide.shape[1] < 3:
        return pd.DataFrame(columns=["source", "target", "weight"])
    C = wide.corr(min_periods=int(0.6 * len(wide)))
    syms = list(C.columns)
    # pandas 3 hands back a read-only view, so copy before writing the diagonal.
    A = np.array(C.to_numpy(), dtype=float, copy=True)
    np.fill_diagonal(A, np.nan)
    rows = []
    for i, s in enumerate(syms):
        r = A[i]
        order = np.argsort(-np.abs(np.nan_to_num(r, nan=0.0)))[:cfg.top_k]
        for j in order:
            w = r[j]
            if not np.isfinite(w) or abs(w) < cfg.min_abs_corr:
                continue
            rows.append({"source": syms[j], "target": s, "weight": float(abs(w)),
                         "signed_weight": float(w)})
    return pd.DataFrame(rows)


def propagate(edges: pd.DataFrame, risk: dict[str, float],
              cfg: GraphConfig = GraphConfig()) -> dict[str, float]:
    """One-step weighted-mean propagation of neighbour risk."""
    if edges.empty:
        return dict.fromkeys(risk, 0.0)
    out: dict[str, float] = {}
    for tgt, g in edges.groupby("target"):
        w = g["weight"].to_numpy()
        v = np.array([risk.get(s, np.nan) for s in g["source"]])
        ok = np.isfinite(v)
        out[tgt] = float(cfg.transfer * np.sum(w[ok] * v[ok]) / max(1e-9, w[ok].sum())) \
            if ok.any() else 0.0
    for k in risk:
        out.setdefault(k, 0.0)
    return out


def propagation_paths(edges: pd.DataFrame, target: str, risk: dict[str, float],
                      k: int = 5) -> pd.DataFrame:
    """The neighbours that contributed most to a target's propagated risk."""
    g = edges[edges["target"] == target].copy()
    if g.empty:
        return g
    g["neighbour_risk"] = [risk.get(s, np.nan) for s in g["source"]]
    g["contribution"] = g["weight"] * g["neighbour_risk"]
    return g.sort_values("contribution", ascending=False).head(k)


def build_propagation_feature(panel: pd.DataFrame, scored: pd.DataFrame,
                              cfg: GraphConfig = GraphConfig(),
                              score_col: str = "integrity_risk") -> pd.DataFrame:
    """Add ``propagated_risk`` to a scored frame, one graph per distinct date.

    Cost is one correlation matrix per date; on the research universe that is a few
    hundred columns, which is cheap. On a wider universe this should be moved to a
    rolling update.
    """
    out = []
    for date, g in scored.groupby("date", sort=True):
        edges = correlation_graph(panel, pd.Timestamp(date), cfg)
        risk = dict(zip(g["symbol"], g[score_col]))
        prop = propagate(edges, risk, cfg)
        gg = g.copy()
        gg["propagated_risk"] = [prop.get(s, 0.0) for s in gg["symbol"]]
        gg["n_neighbours"] = [int((edges["target"] == s).sum()) if len(edges) else 0
                              for s in gg["symbol"]]
        out.append(gg)
    return pd.concat(out).sort_index() if out else scored.assign(propagated_risk=0.0)


#: Feature columns contributed by this module.
PROPAGATION_FEATURES = ["prop_stress", "prop_stress_max", "prop_n_neighbours",
                        "prop_mean_abs_corr", "prop_disagreement"]


def build_stress_features(panel_feat: pd.DataFrame, wanted_dates,
                          cfg: GraphConfig = GraphConfig()) -> pd.DataFrame:
    """Neighbour-stress features, one row per (symbol, date).

    Deliberately built from **observable neighbour stress**, not from the model's own
    risk score. Propagating the model's output would be circular -- the feature would
    partly contain the label the model is trying to predict, and a leakage test would be
    right to fail it. Stress here is the neighbourhood's mean absolute abnormal return
    and turnover z-score, quantities that exist independently of the model.

    The graph for date *t* uses returns strictly before *t*; the stress values are read
    at *t*, which is legitimate because both are available at the decision time.
    """
    need = {"symbol", "date", "logret", "abnormal_ret_21", "turnover_z_21"}
    missing = need - set(panel_feat.columns)
    if missing:
        raise ValueError("panel_feat missing columns: %s" % sorted(missing))

    out_rows = []
    dates = sorted(pd.Timestamp(d) for d in set(wanted_dates))
    # dict(GroupBy) does not work: pandas exposes `GroupBy.keys` as the grouping key
    # name -- a string -- so dict() tries to call it and raises. The comprehension is
    # not redundant, whatever a linter thinks.
    by_date = {d: g for d, g in panel_feat.groupby("date")}  # noqa: C416
    for d in dates:
        g = by_date.get(d)
        if g is None or g.empty:
            continue
        edges = correlation_graph(panel_feat, d, cfg)
        stress = dict(zip(
            g["symbol"],
            0.6 * g["abnormal_ret_21"].abs().fillna(0.0)
            + 0.4 * g["turnover_z_21"].fillna(0.0).clip(lower=0)))
        if edges.empty:
            for s in g["symbol"]:
                out_rows.append({"symbol": s, "date": d, "prop_stress": 0.0,
                                 "prop_stress_max": 0.0, "prop_n_neighbours": 0.0,
                                 "prop_mean_abs_corr": 0.0, "prop_disagreement": 0.0})
            continue
        for tgt, e in edges.groupby("target"):
            w = e["weight"].to_numpy()
            v = np.array([stress.get(s, np.nan) for s in e["source"]])
            ok = np.isfinite(v)
            if not ok.any():
                mean = mx = dis = 0.0
            else:
                mean = float(cfg.transfer * np.sum(w[ok] * v[ok])
                             / max(1e-9, w[ok].sum()))
                mx = float(np.max(v[ok]))
                own = stress.get(tgt, 0.0)
                dis = float(abs(own - mean))
            out_rows.append({"symbol": tgt, "date": d, "prop_stress": mean,
                             "prop_stress_max": mx,
                             "prop_n_neighbours": float(len(e)),
                             "prop_mean_abs_corr": float(w.mean()),
                             "prop_disagreement": dis})
    return pd.DataFrame(out_rows)


def to_networkx(edges: pd.DataFrame, risk: dict[str, float] | None = None):
    import networkx as nx
    G = nx.DiGraph()
    for r in edges.itertuples(index=False):
        G.add_edge(r.source, r.target, weight=float(r.weight))
    if risk:
        for n in G.nodes:
            G.nodes[n]["risk"] = float(risk.get(n, 0.0))
    return G
