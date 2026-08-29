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

PLAIN ENGLISH -- what this whole file is about:

TROUBLE SPREADS. This file works out who a company's "neighbours" are, and how much
trouble is going round in that neighbourhood.

Think of a school. If half a class has a cold, a child in that class is more likely to
catch one -- not because of anything about them personally, but because of who they sit
near. Companies are the same: if everything a company moves with is in difficulty, that is
worth knowing about the company itself.

WHO COUNTS AS A NEIGHBOUR? We have no list of which companies actually do business with
each other, so we work it out from behaviour: two companies are neighbours if their share
prices have tended to move up and down TOGETHER over the past six months.

THREE PIECES OF HONESTY IN THIS FILE, all important.

HONESTY 1 -- "CORRELATION IS NOT A SUPPLY CHAIN".
The last paragraph of the docstring is emphatic, and rightly so. We know these companies
MOVE TOGETHER. We do NOT know why. It could be that one supplies the other. It could be
that they are both in the same industry. It could be that they are both affected by the
oil price. Or it could be complete coincidence.
So an edge in this graph means exactly one thing: "these two have tended to move
together". It never means "this one supplies that one" or "this one owns that one". Saying
so would be inventing a relationship we have no evidence for at all.

HONESTY 2 -- THE TIMING TRAP, and it is a subtle one.
To judge who a company's neighbours are TODAY, we use price movements up to YESTERDAY.
Why not include today? Because if something dramatic happens to a group of companies
today, they will all move together today -- so including today would let the event itself
define the neighbourhood that then goes on to "predict" the event. You would have built a
beautiful circular argument, and it would look like a real finding.

HONESTY 3 -- DO NOT SPREAD THE MODEL'S OWN OPINION.
The obvious design would be: take the model's risk score for each neighbour and pass it
along. That would be circular in a different way -- the model's input would partly contain
the model's own output. Instead we spread OBSERVABLE stress: how oddly the neighbours'
prices actually moved, and how unusual their trading actually was. Real facts about the
world, which exist whether or not our model does.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types.
from dataclasses import dataclass

# Fast maths over big piles of numbers.
import numpy as np
# Tables of data.
import pandas as pd

# A label for this version.
PROPAGATION_VERSION = "propagation-v1"


@dataclass
# The settings for building the neighbour graph.
class GraphConfig:
    # How many past trading days to judge co-movement over. 126 is about six months.
    lookback: int = 126
    # How many neighbours each company may have. Capped at 8 so the graph stays sparse and
    # meaningful -- if everybody were connected to everybody, the graph would say nothing.
    top_k: int = 8
    # How strongly two companies must move together to count as neighbours at all. 0.25 is
    # a modest but real relationship; below that it is mostly noise.
    min_abs_corr: float = 0.25
    #: How much of a neighbour's risk crosses an edge. One step only: multi-step
    #: diffusion on a correlation graph mostly re-derives the market factor.
    # PLAIN ENGLISH: only half of a neighbour's trouble carries across, and it travels ONE
    # step -- from your neighbour to you, and no further. Why not let it spread further?
    # Because on a correlation graph everything is eventually connected to everything, so
    # after a few steps you have simply measured "how is the market doing overall" -- which
    # we already know and which tells you nothing specific about this company.
    transfer: float = 0.5


# Work out who is next to whom, on one particular date.
def correlation_graph(panel: pd.DataFrame, as_of: pd.Timestamp,
                      cfg: GraphConfig = GraphConfig()) -> pd.DataFrame:
    """Edges for one date. Returns ``(source, target, weight)``, weight in [0, 1]."""
    # STRICTLY BEFORE the date in question. This one `<` (rather than `<=`) is the entire
    # timing protection described above.
    hist = panel[panel["date"] < as_of]
    if hist.empty:
        # No history at all: hand back an empty table with the right columns, so callers can
        # treat it normally rather than having to guard against a different shape.
        return pd.DataFrame(columns=["source", "target", "weight"])
    # The most recent 126 trading days. `[-cfg.lookback:]` takes the last that many.
    dates = np.sort(hist["date"].unique())[-cfg.lookback:]
    hist = hist[hist["date"].isin(dates)]
    # Reshape: dates down the side, companies across the top, daily returns in the middle.
    wide = hist.pivot_table(index="date", columns="symbol", values="logret")
    # Drop companies missing more than 20% of the window. A correlation computed from a
    # handful of scattered days is not a relationship, it is an accident.
    wide = wide.dropna(axis=1, thresh=int(0.8 * len(wide)))
    # Fewer than three companies left: no meaningful graph exists.
    if wide.shape[1] < 3:
        return pd.DataFrame(columns=["source", "target", "weight"])
    # How much every pair moved together. `min_periods` requires at least 60% overlap for
    # any individual pair, so two companies that barely coincide do not get a number.
    C = wide.corr(min_periods=int(0.6 * len(wide)))
    syms = list(C.columns)
    # pandas 3 hands back a read-only view, so copy before writing the diagonal.
    # PLAIN ENGLISH: a version-compatibility note. Newer pandas hands back data you are not
    # allowed to alter, so we take our own copy first. Without this the next line would fail.
    A = np.array(C.to_numpy(), dtype=float, copy=True)
    # Blank out the diagonal: every company correlates perfectly with itself, and being your
    # own neighbour would be both useless and, worse, the strongest edge in the graph.
    np.fill_diagonal(A, np.nan)
    rows = []
    for i, s in enumerate(syms):
        r = A[i]
        # The eight strongest relationships. `-np.abs(...)` sorts by strength largest-first,
        # ignoring direction: a company that reliably moves OPPOSITE to another is just as
        # informative a neighbour as one that moves with it.
        order = np.argsort(-np.abs(np.nan_to_num(r, nan=0.0)))[:cfg.top_k]
        for j in order:
            w = r[j]
            # Skip anything unknown or too weak to mean anything.
            if not np.isfinite(w) or abs(w) < cfg.min_abs_corr:
                continue
            rows.append({"source": syms[j], "target": s, "weight": float(abs(w)),
                         # The signed version is kept as well, so a later reader can see
                         # whether the pair moved together or in opposition -- information
                         # the absolute value throws away.
                         "signed_weight": float(w)})
    return pd.DataFrame(rows)


# Pass risk one step along the edges.
def propagate(edges: pd.DataFrame, risk: dict[str, float],
              cfg: GraphConfig = GraphConfig()) -> dict[str, float]:
    """One-step weighted-mean propagation of neighbour risk."""
    # No edges means no neighbours means no propagated risk -- zero for everybody.
    if edges.empty:
        return dict.fromkeys(risk, 0.0)
    out: dict[str, float] = {}
    # For each company, look at everyone pointing at it.
    for tgt, g in edges.groupby("target"):
        w = g["weight"].to_numpy()
        v = np.array([risk.get(s, np.nan) for s in g["source"]])
        ok = np.isfinite(v)
        # A weighted average of the neighbours' risk: closer neighbours count for more.
        # Then halved by the transfer setting, because trouble weakens as it travels.
        # `max(1e-9, ...)` prevents a divide-by-zero if all the weights somehow came out at
        # nothing.
        out[tgt] = float(cfg.transfer * np.sum(w[ok] * v[ok]) / max(1e-9, w[ok].sum())) \
            if ok.any() else 0.0
    # Make sure every company has an answer. `setdefault` fills in 0 for anyone with no
    # neighbours, so nobody is silently missing from the result.
    for k in risk:
        out.setdefault(k, 0.0)
    return out


# Show WHICH neighbours were responsible.
def propagation_paths(edges: pd.DataFrame, target: str, risk: dict[str, float],
                      k: int = 5) -> pd.DataFrame:
    """The neighbours that contributed most to a target's propagated risk."""
    # PLAIN ENGLISH: this is what makes propagation "shown rather than asserted". Instead of
    # "there is trouble in this company's neighbourhood", you can say "these five specific
    # companies, connected this strongly, are the ones in trouble" -- and a reader can go and
    # check each one.
    g = edges[edges["target"] == target].copy()
    if g.empty:
        return g
    # How much risk each neighbour is carrying...
    g["neighbour_risk"] = [risk.get(s, np.nan) for s in g["source"]]
    # ...times how closely connected it is. That product is its contribution.
    g["contribution"] = g["weight"] * g["neighbour_risk"]
    # The biggest contributors first.
    return g.sort_values("contribution", ascending=False).head(k)


# Add the propagated-risk column to a table of scored companies.
def build_propagation_feature(panel: pd.DataFrame, scored: pd.DataFrame,
                              cfg: GraphConfig = GraphConfig(),
                              score_col: str = "integrity_risk") -> pd.DataFrame:
    """Add ``propagated_risk`` to a scored frame, one graph per distinct date.

    Cost is one correlation matrix per date; on the research universe that is a few
    hundred columns, which is cheap. On a wider universe this should be moved to a
    rolling update.
    """
    # PLAIN ENGLISH: an honest note about how well this scales. With a few hundred companies,
    # rebuilding the whole correlation grid every day is perfectly affordable. With tens of
    # thousands it would not be, and the comment says what to do instead. Recording the limit
    # where it will be found is much better than leaving the next person to discover it.
    out = []
    for date, g in scored.groupby("date", sort=True):
        # A fresh graph for this date, built only from earlier data.
        edges = correlation_graph(panel, pd.Timestamp(date), cfg)
        risk = dict(zip(g["symbol"], g[score_col]))
        prop = propagate(edges, risk, cfg)
        gg = g.copy()
        gg["propagated_risk"] = [prop.get(s, 0.0) for s in gg["symbol"]]
        # How many neighbours each company had. Kept because "high neighbourhood risk from
        # one neighbour" and "from eight neighbours" are very different situations that the
        # single averaged number cannot distinguish.
        gg["n_neighbours"] = [int((edges["target"] == s).sum()) if len(edges) else 0
                              for s in gg["symbol"]]
        out.append(gg)
    return pd.concat(out).sort_index() if out else scored.assign(propagated_risk=0.0)


#: Feature columns contributed by this module.
PROPAGATION_FEATURES = ["prop_stress", "prop_stress_max", "prop_n_neighbours",
                        "prop_mean_abs_corr", "prop_disagreement"]


# The version that spreads OBSERVED stress rather than the model's own opinion.
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
    # PLAIN ENGLISH on that last paragraph, which is a genuinely careful distinction.
    # Two different things happen at two different times, and both are correct:
    #   WHO the neighbours are -- worked out from BEFORE today, because today's co-movement
    #     could be caused by the very event we are trying to detect.
    #   HOW STRESSED they are -- read from TODAY, which is fine, because by the time we make
    #     a decision today's trading is published and genuinely available to us.
    # Getting this the wrong way round in either direction would be a leak.

    # The columns we need.
    need = {"symbol", "date", "logret", "abnormal_ret_21", "turnover_z_21"}
    missing = need - set(panel_feat.columns)
    if missing:
        raise ValueError("panel_feat missing columns: %s" % sorted(missing))

    out_rows = []
    dates = sorted(pd.Timestamp(d) for d in set(wanted_dates))
    # dict(GroupBy) does not work: pandas exposes `GroupBy.keys` as the grouping key
    # name -- a string -- so dict() tries to call it and raises. The comprehension is
    # not redundant, whatever a linter thinks.
    # PLAIN ENGLISH: a note left for the next person. An automatic style checker will flag
    # the line below as a pointless copy and suggest the shorter form -- and the shorter form
    # CRASHES here, for a genuinely obscure reason. The comment (and the `noqa` that silences
    # the checker) is there so nobody "tidies" it up and breaks the build.
    by_date = {d: g for d, g in panel_feat.groupby("date")}  # noqa: C416
    for d in dates:
        g = by_date.get(d)
        if g is None or g.empty:
            continue
        # Who is next to whom, using only earlier data.
        edges = correlation_graph(panel_feat, d, cfg)
        # How stressed each company OBSERVABLY is today. A 60/40 mix of:
        #   how oddly its price moved compared with the market (`.abs()` -- either direction
        #     is interesting), and
        #   how unusual its trading was. `.clip(lower=0)` keeps only UNUSUALLY HIGH trading:
        #     a quiet day is not stress, and letting it count as negative stress would let
        #     calm neighbours cancel out alarming ones.
        stress = dict(zip(
            g["symbol"],
            0.6 * g["abnormal_ret_21"].abs().fillna(0.0)
            + 0.4 * g["turnover_z_21"].fillna(0.0).clip(lower=0)))
        if edges.empty:
            # No graph today: record explicit zeros for everybody, so the columns always
            # exist and the rows are never silently missing.
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
                # The neighbourhood's weighted average stress.
                mean = float(cfg.transfer * np.sum(w[ok] * v[ok])
                             / max(1e-9, w[ok].sum()))
                # The single most stressed neighbour. Kept separately because one neighbour
                # in serious trouble is a different story from eight mildly odd ones, and an
                # average cannot tell those apart.
                mx = float(np.max(v[ok]))
                own = stress.get(tgt, 0.0)
                # How far this company differs from its neighbourhood. Interesting in both
                # directions: a calm company in a panicking neighbourhood may be about to
                # catch it, and an agitated company among calm ones has a problem of its own.
                dis = float(abs(own - mean))
            out_rows.append({"symbol": tgt, "date": d, "prop_stress": mean,
                             "prop_stress_max": mx,
                             "prop_n_neighbours": float(len(e)),
                             # How strong the connections were on average -- context for how
                             # seriously to take the neighbourhood figure at all.
                             "prop_mean_abs_corr": float(w.mean()),
                             "prop_disagreement": dis})
    return pd.DataFrame(out_rows)


# Convert the edges into a proper graph object, for drawing and analysis.
def to_networkx(edges: pd.DataFrame, risk: dict[str, float] | None = None):
    # networkx is the standard toolbox for networks of dots and lines.
    import networkx as nx
    # A "DiGraph" is a DIRECTED graph -- the lines have arrows. That matters here because
    # neighbourliness is not symmetric: A may be one of B's eight closest companions without
    # B being one of A's.
    G = nx.DiGraph()
    for r in edges.itertuples(index=False):
        G.add_edge(r.source, r.target, weight=float(r.weight))
    # Optionally attach each company's own risk to its dot, so a drawing can colour them.
    if risk:
        for n in G.nodes:
            G.nodes[n]["risk"] = float(risk.get(n, 0.0))
    return G
