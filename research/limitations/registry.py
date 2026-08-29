"""Limitations as structured research objects, not markdown prose.

`docs/LIMITATIONS.md` remains the authoritative factual record and nothing here weakens
any caveat in it. This module makes the same facts *machine-readable* so that the chain

    LIMITATION -> RESEARCH QUESTION -> EXPERIMENT -> RESULT -> FIGURE -> CLAIM

can be traversed by the UI, the paper generator and the claim guard.

The distinction this module exists to protect: a research *angle* is not a research
*result*. Every experiment specification carries a status, and a specification whose data
does not exist is `BLOCKED` -- never a number.

PLAIN ENGLISH -- what this whole file is about:

THIS IS THE PROJECT'S LIST OF EVERYTHING IT CANNOT DO.

Most projects hide their weaknesses in a short section near the end that nobody reads.
This one turns them into DATA: a structured, machine-readable list that the website, the
paper generator and the automatic fact-checker all read and act on.

Why does that matter? Because a weakness written in prose is a weakness somebody can
forget. A weakness written as data can be WIRED IN. If a limitation says "we cannot claim
this covers the Nifty 50", then the automatic checker reads that and REFUSES to publish
any sentence containing the phrase "on the Nifty 50" -- forever, whoever writes it, in
any document. The caveat stops depending on anybody remembering it.

EACH LIMITATION ENTRY RECORDS SIX THINGS, and the last two are the unusual ones:
  1. WHAT is missing.
  2. WHY it is missing.
  3. What we used INSTEAD, if anything.
  4. What research questions it opens up -- and the experiments that would settle them.
  5. INVALIDATED CLAIMS -- sentences this project is therefore NOT allowed to say.
  6. STILL VALID -- what we CAN honestly claim despite the gap.

Point 6 deserves attention. It would be easy to list only the failures, which sounds
humble and is actually just as unhelpful as hiding them: a reader cannot tell what
survives. Recording both sides is what makes the register usable rather than merely
apologetic.

AND THE RULE IN THE THIRD PARAGRAPH ABOVE, which is the sharpest idea here:
"a research angle is not a research result."
Having a good idea for an experiment is not the same as having run it. So every planned
experiment carries a status, and one whose data does not exist is marked BLOCKED. It can
never quietly turn into a number in a results table just because somebody wrote the plan
out in convincing detail.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For writing the register out as JSON.
import json
# Record-building tools.
from dataclasses import asdict, dataclass, field
# For fixed menus of allowed choices.
from enum import StrEnum
# A safe way to talk about places on the disk.
from pathlib import Path

# A label for this version of the register.
REGISTRY_VERSION = "limitations-v1"


class Category(StrEnum):
    """Section 2 of the research-angle brief. A limitation is not automatically a
    failure; the category says what kind of boundary it is."""
    # PLAIN ENGLISH: that second clause matters. "We could not afford this data" and "this
    # question is genuinely unsolved by science" are both limitations, and they mean
    # completely different things about the work. Sorting them into kinds stops a reader
    # treating an unavoidable boundary as a mistake, or a mistake as unavoidable.

    # Something we could build, and have not yet.
    ENGINEERING = "ENGINEERING"
    # The data does not exist, or we could not get it.
    DATA = "DATA"
    # The data exists but we are not legally allowed to use it.
    LICENSING = "LICENSING"
    # It would need more computing power than we have.
    COMPUTATIONAL = "COMPUTATIONAL"
    # A limit of the method itself.
    METHODOLOGICAL = "METHODOLOGICAL"
    # We could not properly test it.
    EVALUATION = "EVALUATION"
    # Nobody knows the answer. Not our failing.
    OPEN_QUESTION = "SCIENTIFIC_OPEN_QUESTION"
    # We tried it, it did not work, and we do not know why. The bravest thing to publish.
    NEGATIVE_RESULT = "UNRESOLVED_NEGATIVE_RESULT"


class Status(StrEnum):
    """Precise result vocabulary. `NOT MEASURED` and `NOT SUPPORTED` are different
    things, and neither is `FAILED`."""
    # PLAIN ENGLISH: read that sentence slowly, because the distinction is the whole point.
    #   NOT MEASURED  -- we never checked. We do not know.
    #   NOT SUPPORTED -- we checked, and the evidence did not back it up.
    #   FAILED        -- something went wrong.
    # In casual writing all three collapse into "it did not work", and they are three
    # completely different statements about the world. Giving each its own word means a
    # reader always knows which one is meant.

    # The evidence backs the claim.
    SUPPORTED = "SUPPORTED"
    # Partly.
    PARTIAL = "PARTIAL"
    # We checked, and it does not.
    NOT_SUPPORTED = "NOT_SUPPORTED"
    # Designed but never executed.
    NOT_RUN = "NOT_RUN"
    # Never checked at all.
    NOT_MEASURED = "NOT_MEASURED"
    # Cannot be run: something required does not exist.
    BLOCKED = "BLOCKED"
    # Nobody knows.
    OPEN_QUESTION = "OPEN_QUESTION"
    # Would need future work, or data that does not exist yet, to settle.
    FUTURE_VALIDATION = "FUTURE_VALIDATION"
    # It ran, and failed a check designed to catch nonsense -- so its output is not trusted.
    FAILED_SANITY_CHECK = "FAILED_SANITY_CHECK"
    # A number was produced, without a claim being attached to it.
    MEASURED = "MEASURED"


class Severity(StrEnum):
    # PLAIN ENGLISH: how far the damage spreads. Some limitations qualify every single thing
    # the project says; others only narrow one sentence. Recording which is which stops a
    # small caveat being read as fatal, and a fatal one being read as small.

    # Every claim in the project is bounded by this one.
    BOUNDS_ALL_CLAIMS = "BOUNDS_ALL_CLAIMS"
    # Several claims are.
    BOUNDS_SOME_CLAIMS = "BOUNDS_SOME_CLAIMS"
    # It narrows exactly one claim.
    SCOPES_A_CLAIM = "SCOPES_A_CLAIM"
    # It affects no scientific claim at all -- only how tidy the software is.
    ENGINEERING_ONLY = "ENGINEERING_ONLY"


@dataclass
class ExperimentSpec:
    """A designed experiment. Section 7 fields are mandatory so a specification cannot
    be vague enough to be unfalsifiable."""
    # PLAIN ENGLISH: "unfalsifiable" means phrased so vaguely that no result could ever
    # prove it wrong -- and a claim that nothing could disprove is not science, it is just
    # an opinion with equipment.
    # Every field below is COMPULSORY. That forces whoever writes an experiment to say, in
    # advance, exactly what would count as success and exactly what would count as failure.
    # You cannot fill this in and still be vague.

    # A unique name for it.
    id: str
    # Exactly what is being claimed, stated so it could turn out to be false.
    hypothesis: str
    # What we change.
    independent_variable: str
    # What we measure.
    dependent_variable: str
    # The comparison group, and the one being tested. Named separately, so the experiment
    # cannot quietly become a before-and-after with nothing to compare against.
    control: str
    treatment: str
    # Which data, and over which period.
    dataset: str
    evaluation_period: str
    # How success is measured, and which statistical test decides it. Both fixed in advance,
    # so nobody can pick the flattering metric after seeing the numbers.
    metrics: list[str]
    statistical_test: str
    # WHAT WE WILL CONCLUDE FROM EACH POSSIBLE OUTCOME -- written before running. This is the
    # single most important field on the form, because it makes it impossible to look at a
    # result afterwards and construct a story that happens to fit it.
    expected_interpretation: str
    # And the honest list of ways this experiment could mislead us even if it runs perfectly.
    threats_to_validity: list[str]
    # Where it has got to.
    status: Status
    #: What must exist before this can run. Empty means it is runnable now.
    # An empty list is meaningful: it means there is no excuse. See `runnable_now` below.
    required_data: list[str] = field(default_factory=list)
    #: Populated only when the experiment has actually been executed.
    # Empty until it has genuinely run, so a plan can never be mistaken for a result.
    result_artifact: str | None = None


@dataclass
class ResearchQuestion:
    """One open question that a limitation gives rise to."""
    # A unique name.
    id: str
    # The question itself.
    question: str
    # Which limitation it came from -- so the chain back to the gap is never broken.
    limitation_id: str
    status: Status
    # The experiments that would settle it.
    experiments: list[ExperimentSpec] = field(default_factory=list)
    # What we can say today.
    current_evidence: str | None = None
    # And, crucially, what is still genuinely unknown. Stated separately so partial progress
    # is never allowed to read as a finished answer.
    what_remains_unresolved: str | None = None


@dataclass
class Limitation:
    """One thing this project cannot do, and everything that follows from it."""
    # A unique name, like "L-01".
    id: str
    # A short readable title.
    title: str
    # What kind of boundary it is.
    category: Category
    # How far it reaches.
    severity: Severity
    #: The fact, stated exactly as `docs/LIMITATIONS.md` states it.
    # Copied word for word from the human-written document, so the two can never drift apart
    # and quietly start saying different things.
    description: str
    # Why it exists -- so a reader can judge whether it was avoidable.
    why_it_exists: str
    current_status: Status
    # What we used instead, if anything. None means we used nothing rather than inventing.
    current_substitute: str | None
    # THE SENTENCES THIS PROJECT MAY NOT SAY because of this gap.
    invalidated_claims: list[str]
    # And what it CAN still honestly say. Both sides, always.
    still_valid: list[str]
    # The questions this opens up, with their experiments.
    research_questions: list[ResearchQuestion] = field(default_factory=list)
    # What would need to exist to fix it.
    required_data: list[str] = field(default_factory=list)
    # And how it could be settled in future.
    future_validation: str = ""
    #: Forbidden phrasings the claim guard enforces (section 54).
    # THE ENFORCEMENT. Actual phrases the automatic checker hunts for and blocks. This is
    # what turns a caveat from something people must remember into something the machine
    # will not let them forget.
    forbidden_phrasings: list[str] = field(default_factory=list)
    #: Scope note automatically attached to any result depending on this limitation.
    # A short warning label stapled to every result touched by this gap -- so the caveat
    # travels with the number instead of living in a document nobody opens.
    scope_note: str = ""


# A small helper for building a research question with less typing.
# The bare `*` means everything after it must be passed BY NAME, so a caller cannot get the
# order of several similar-looking text arguments wrong.
def _rq(rid: str, lid: str, q: str, status: Status, *,
        current_evidence: str | None = None,
        unresolved: str | None = None,
        experiments: list[ExperimentSpec] | None = None) -> ResearchQuestion:
    # `experiments or []` turns "nothing given" into a fresh empty list, so every question
    # gets its own rather than all of them sharing one.
    return ResearchQuestion(rid, q, lid, status, experiments or [], current_evidence,
                            unresolved)



# ---------------------------------------------------------------------------------------
# The register. Facts are taken verbatim in substance from docs/LIMITATIONS.md; the
# research angles are added on top and never soften the underlying caveat.
# ---------------------------------------------------------------------------------------

LIMITATIONS: list[Limitation] = [

    # We could not get a proper historical list of which companies were in the
    # famous Nifty-50 index, so we built our own stand-in from what was busiest at the
    # time -- and we never call it the Nifty 50.
    Limitation(
        id="L-01",
        title="Point-in-time index membership unavailable",
        category=Category.LICENSING,
        severity=Severity.BOUNDS_ALL_CLAIMS,
        description=(
            "No licence-clear, point-in-time Nifty-50 constituent history was located. "
            "The research universe is a point-in-time liquidity proxy: the top 50 "
            "symbols by trailing median traded value at each monthly rebalance, "
            "estimated only from sessions strictly preceding the rebalance."),
        why_it_exists=(
            "No free source with redistribution rights was found. Reconstructing one "
            "from secondary web sources would be unverifiable, and inventing one is "
            "prohibited."),
        current_status=Status.NOT_MEASURED,
        current_substitute="Point-in-time liquidity-proxy universe (survivorship-safe)",
        invalidated_claims=[
            "Any statement of the form 'results on the Nifty 50'.",
            "Like-for-like comparison against index-level literature.",
        ],
        still_valid=[
            "The universe is survivorship-safe by construction: 257 rebalances, 270 "
            "distinct members ever selected for a 50-name universe, 2.59 entries and "
            "2.59 exits per rebalance.",
            "Every instrument-day used was genuinely liquid at that time.",
        ],
        required_data=[
            "Licence-clear point-in-time NSE index constituent history with effective "
            "dates and change reasons (additions, removals, symbol changes).",
        ],
        future_validation=(
            "Re-run the full ablation suite on true point-in-time membership and report "
            "the delta against the liquidity proxy."),
        forbidden_phrasings=["on the Nifty 50", "Nifty-50 results", "index constituents"],
        scope_note="Universe: point-in-time liquidity proxy, not the Nifty 50.",
        research_questions=[
            _rq("RQ-L01-A", "L-01",
                "How sensitive are integrity-event results to the choice of "
                "universe construction?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Only one universe has been evaluated, so sensitivity is unmeasured."),
                unresolved="Whether universe choice changes block importance ordering.",
                experiments=[ExperimentSpec(
                    id="EXP-L01-1",
                    hypothesis=(
                        "Event prevalence and block contribution differ materially "
                        "between a liquidity-proxy universe and true point-in-time index "
                        "membership."),
                    independent_variable="universe construction rule",
                    dependent_variable="AUPRC, lead time, block contribution, "
                                       "event prevalence",
                    control="point-in-time liquidity proxy (current)",
                    treatment="licence-clear point-in-time index membership",
                    dataset="NSE cash panel 2005-2026 + injected episodes",
                    evaluation_period="validation split, identical for both arms",
                    metrics=["auprc", "auroc", "lead_time", "false_alarm_rate",
                             "block_contribution", "ece"],
                    statistical_test="paired cluster bootstrap on episodes",
                    expected_interpretation=(
                        "A small delta would support the proxy as an adequate stand-in; "
                        "a large delta would mean universe construction is a confound "
                        "that the literature should control for."),
                    threats_to_validity=[
                        "Membership history itself may contain vendor errors.",
                        "Injected episodes are placed by the generator, so prevalence "
                        "differences partly reflect universe size, not market reality."],
                    status=Status.BLOCKED,
                    required_data=["point-in-time index membership"])]),
            _rq("RQ-L01-B", "L-01",
                "Does a liquidity-proxy universe systematically over- or under-represent "
                "the instruments where integrity events actually concentrate?",
                Status.BLOCKED,
                current_evidence="Requires real incident labels; see L-04.",
                unresolved="Everything.",
                experiments=[]),
        ],
    ),

    # The really fine-grained trading data (every order, including cancelled ones)
    # is not published, so the 'microstructure' measures here are honest stand-ins.
    Limitation(
        id="L-02",
        title="True market microstructure not measured",
        category=Category.DATA,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "NSE does not publish historical Level-2 depth openly. Order-book imbalance, "
            "signed order-flow imbalance, VPIN, cancellation behaviour and execution "
            "aggression are emitted as NaN with a stated reason and appear as "
            "NOT MEASURED in the coverage table."),
        why_it_exists="The data is not published openly at any price the project can pay.",
        current_status=Status.NOT_MEASURED,
        current_substitute=(
            "Four daily-aggregate proxies: average trade size, its z-score, trade-count "
            "z-score, turnover-per-trade z-score."),
        invalidated_claims=[
            "Any claim about order-book dynamics, liquidity provision or predatory "
            "order behaviour.",
            "Any claim that the 'microstructure' ablation arm tests true microstructure.",
        ],
        still_valid=[
            "The proxies are computed from real trade counts and real turnover.",
            "Their contribution was measured: removing them changes AUPRC by 0.0002 "
            "(95% CI -0.000006 to 0.0004), not significant at 5% FDR.",
        ],
        required_data=[
            "A licence-clear Level-2 sample: order-book snapshots or message-level data "
            "for a subset of instruments and dates, aligned to the panel.",
        ],
        future_validation=(
            "Calibrate the daily proxies against a small true Level-2 sample and report "
            "the information retained."),
        forbidden_phrasings=["order book", "order-flow imbalance", "VPIN", "depth"],
        scope_note="Microstructure: daily-aggregate proxies only; true depth NOT MEASURED.",
        research_questions=[
            _rq("RQ-L02-A", "L-02",
                "How much of the integrity-event information carried by true order-book "
                "features is retained by daily-aggregate proxies?",
                Status.BLOCKED,
                current_evidence=(
                    "The proxies contribute negligibly on their own (delta 0.0002, "
                    "not significant), which is consistent either with the proxies being "
                    "weak *or* with microstructure being uninformative here. The current "
                    "evidence cannot separate those two explanations."),
                unresolved="Which of the two explanations holds.",
                experiments=[ExperimentSpec(
                    id="EXP-L02-1",
                    hypothesis=(
                        "Daily-aggregate proxies retain a measurable but minority share "
                        "of the detection information available from Level-2 features."),
                    independent_variable="microstructure feature source",
                    dependent_variable="AUPRC on a matched instrument-date subset",
                    control="market features + daily proxies",
                    treatment="market features + true Level-2 features",
                    dataset="matched subset with Level-2 coverage",
                    evaluation_period="whatever window the Level-2 sample covers",
                    metrics=["auprc", "auroc", "lead_time", "permutation_importance"],
                    statistical_test="paired cluster bootstrap on the matched subset",
                    expected_interpretation=(
                        "If the proxy arm approaches the Level-2 arm, the proxy is an "
                        "adequate substitute at daily resolution; if not, the negligible "
                        "proxy contribution measured here is an artefact of resolution "
                        "rather than evidence about microstructure."),
                    threats_to_validity=[
                        "A short Level-2 window may not span enough episodes.",
                        "Matched subsets are small, so power is limited (see L-12)."],
                    status=Status.BLOCKED,
                    required_data=["licence-clear Level-2 sample"])]),
        ],
    ),

    # The website was built and checked, but never actually put live on the
    # internet for real users.
    Limitation(
        id="L-03",
        title="Product build verified; deployment not performed",
        category=Category.ENGINEERING,
        severity=Severity.ENGINEERING_ONLY,
        description=(
            "RESOLVED in iteration 3. Node.js 24.19.0 was installed and the application "
            "now typechecks, lints and builds: 35 files checked by tsc with zero errors, "
            "ESLint clean, 204 pages prerendered including all 162 instrument routes and "
            "17 limitation routes, and every route verified to return HTTP 200 with "
            "server-rendered content. What remains unverified is deployment to Vercel "
            "itself, which is a hosting step rather than a build property."),
        why_it_exists=(
            "Originally: no Node.js runtime existed in the authoring environment. That is "
            "no longer the case, so the build half of this limitation is discharged."),
        current_status=Status.MEASURED,
        current_substitute=None,
        invalidated_claims=[
            "'The product is deployed' remains unsupported: it builds and serves locally, "
            "but no Vercel deployment has been performed.",
        ],
        still_valid=[
            "tsc --noEmit passes over all 35 project files.",
            "next build prerenders 204 pages with no error.",
            "Every route returns HTTP 200 with server-rendered content, checked route by "
            "route against the running production server.",
            "Artifact-to-page value parity holds: numbers reported by the pipeline appear "
            "unchanged in the served HTML.",
        ],
        required_data=[],
        future_validation=(
            "Deploy to Vercel and re-measure latency against the local baseline recorded "
            "in EXP-L03-1."),
        forbidden_phrasings=["deploys on Vercel", "is deployed", "deployment verified"],
        scope_note="Product: builds and serves locally; not deployed to Vercel.",
        research_questions=[
            _rq("RQ-L03-A", "L-03",
                "Can a static-artifact architecture preserve exact research results while "
                "serving them from a serverless frontend?",
                Status.PARTIAL,
                current_evidence=(
                    "Both halves are now measured. Research side: a full re-run "
                    "reproduced all 8 arms and 7 statistical tests to 0.000e+00 maximum "
                    "absolute difference. Delivery side: every checked value renders in "
                    "the served HTML identical to its source artifact (AUPRC 0.941166 -> "
                    "0.941, minimum detectable effect 0.000185 -> 0.000185), and p95 "
                    "latency over 20 samples per route is 17-33 ms locally with no "
                    "computation in the request path. The export step was found to emit "
                    "bare NaN, which is invalid JSON and silently blanked a page; that is "
                    "fixed and now tested."),
                unresolved=("Behaviour on Vercel specifically: cold starts, edge caching "
                            "and artifact freshness under a real deployment."),
                experiments=[ExperimentSpec(
                    id="EXP-L03-1",
                    hypothesis=(
                        "Exported JSON bundles render identical values to the source "
                        "artifacts, with page latency dominated by transfer rather than "
                        "computation."),
                    independent_variable="delivery path (direct artifact vs exported bundle)",
                    dependent_variable="value parity, p95 page latency",
                    control="values read directly from research_artifacts/",
                    treatment="values read from public/data/ in the deployed app",
                    dataset="current export",
                    evaluation_period="n/a",
                    metrics=["value_parity", "p95_latency_ms", "bundle_bytes"],
                    statistical_test="exact equality check; latency percentiles",
                    expected_interpretation=(
                        "Any parity failure is a bug in the export, not a research "
                        "finding."),
                    threats_to_validity=[
                        "Network variance dominates latency measurement.",
                        "Local measurement excludes cold starts and edge caching, which "
                        "are precisely what a hosted deployment would stress."],
                    status=Status.MEASURED,
                    required_data=[],
                    result_artifact=(
                        "iteration 3: parity verified across 6 values; p50 5.9-10.0 ms, "
                        "p95 17.1-32.9 ms over 20 samples per route"))]),
        ],
    ),

    # Nobody publishes a trustworthy list of real market-integrity incidents, so we
    # painted our own fake ones onto real data. Every score is about OUR fakes.
    Limitation(
        id="L-04",
        title="Episode labels are synthetic",
        category=Category.DATA,
        severity=Severity.BOUNDS_ALL_CLAIMS,
        description=(
            "No open, labelled corpus of NSE market-integrity incidents exists. Synthetic "
            "episodes are injected into the real price panel: phase-structured intensity "
            "profiles perturb returns, volume, turnover and trade counts, with a matched "
            "text corpus."),
        why_it_exists=(
            "None exists publicly, and labelling real companies as subjects of "
            "manipulation by inference would be both fabrication and defamation."),
        current_status=Status.MEASURED,
        current_substitute="Injected episodes with generator/detector isolation",
        invalidated_claims=[
            "Every detection metric describes behaviour on injected episodes.",
            "No number in this repository is evidence that the system detects real-world "
            "market manipulation.",
        ],
        still_valid=[
            "Generator parameters are structurally isolated from every detector, "
            "asserted by an AST-level test.",
            "Background days are drawn from the same symbols and the same calendar as "
            "episode days, so neither symbol identity nor date is the label.",
            "Features are recomputed from the modified bars, so a detector sees only data.",
        ],
        required_data=[
            "Expert-adjudicated or regulator-published incident labels for NSE "
            "instruments, with dates and instrument identifiers.",
        ],
        future_validation=(
            "Train on injected episodes, evaluate on adjudicated real incidents, and "
            "report the transfer gap."),
        forbidden_phrasings=["detects manipulation", "real manipulation", "detected fraud",
                             "real-world detection"],
        scope_note="Labels: synthetic episodes injected into real prices.",
        research_questions=[
            _rq("RQ-L04-A", "L-04",
                "How well does a detector trained on injected episodes transfer to "
                "expert-adjudicated real incidents?",
                Status.BLOCKED,
                current_evidence="No real labels exist, so transfer is entirely unmeasured.",
                unresolved="The central question of the whole project.",
                experiments=[ExperimentSpec(
                    id="EXP-L04-1",
                    hypothesis=(
                        "A detector fitted on injected episodes retains above-chance "
                        "AUPRC on adjudicated real incidents without refitting."),
                    independent_variable="evaluation corpus (synthetic vs real)",
                    dependent_variable="AUPRC, lead time, false-alarm rate",
                    control="evaluation on held-out injected episodes",
                    treatment="evaluation on adjudicated real incidents",
                    dataset="NSE panel + adjudicated incident labels",
                    evaluation_period="whatever the label corpus covers",
                    metrics=["auprc", "auprc_lift", "lead_time", "false_alarm_rate", "ece"],
                    statistical_test="cluster bootstrap on incidents; DeLong on AUROC",
                    expected_interpretation=(
                        "Transfer above the real-corpus base rate would be the first "
                        "genuine evidence for the method. Transfer at chance would show "
                        "the injected episodes are the wrong generative model, which is "
                        "itself a publishable methodological finding."),
                    threats_to_validity=[
                        "Adjudicated incidents are themselves a biased sample: only "
                        "detected incidents get adjudicated.",
                        "Real incident base rates are far lower than the injected 22%, "
                        "so AUPRC is not comparable across corpora without the base rate."],
                    status=Status.BLOCKED,
                    required_data=["adjudicated incident labels"])]),
            _rq("RQ-L04-B", "L-04",
                "Which synthetic episode properties most strongly determine detector "
                "performance, and is that dependence itself informative?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Runnable now: the generator exposes duration, peak intensity, "
                    "return kappa, volume kappa, censoring and text noise fraction, and "
                    "each episode's realised parameters are recorded."),
                unresolved="Whether the dependence generalises to real incidents.",
                experiments=[ExperimentSpec(
                    id="EXP-L04-2",
                    hypothesis=(
                        "Detection performance is monotone in peak intensity and episode "
                        "duration, and degrades sharply below a discoverable intensity "
                        "floor."),
                    independent_variable="episode peak intensity and duration",
                    dependent_variable="per-episode detection and lead time",
                    control="episodes in the lowest intensity quartile",
                    treatment="episodes in the highest intensity quartile",
                    dataset="current injected episodes",
                    evaluation_period="validation split",
                    metrics=["detection_rate", "lead_time", "peak_score"],
                    statistical_test="cluster bootstrap across episodes; rank correlation",
                    expected_interpretation=(
                        "An intensity floor tells a future study what magnitude of real "
                        "event this architecture could plausibly see at all."),
                    threats_to_validity=[
                        "Intensity is a generator parameter, so the relationship is "
                        "partly definitional; only the *shape* and the floor are "
                        "informative."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # The 'who is connected to whom' graph is built purely from prices moving
    # together. It never means one company supplies or owns another.
    Limitation(
        id="L-07",
        title="Propagation graph is statistical, not economic",
        category=Category.METHODOLOGICAL,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "Edges are trailing 126-session return correlations above 0.25, estimated "
            "strictly before each decision date. No sector, ownership or supply-chain "
            "structure is used."),
        why_it_exists="No licence-clear NSE sector or ownership mapping was located.",
        current_status=Status.MEASURED,
        current_substitute="Correlation graph with neighbour-stress features",
        invalidated_claims=[
            "Any claim that an edge is an economic, sectoral or causal relationship.",
        ],
        still_valid=[
            "Edges are point-in-time correct: the graph for date t uses only sessions "
            "before t.",
            "The contribution was measured: 0.0005 AUPRC (95% CI 0.0002-0.0009).",
        ],
        required_data=["licence-clear sector, index-weight or ownership mapping"],
        future_validation="Compare correlation, sector, ownership and news-entity graphs "
                          "on identical folds.",
        forbidden_phrasings=["causal", "supply chain", "sector propagation",
                             "contagion pathway"],
        scope_note="Propagation: statistical co-movement only.",
        research_questions=[
            _rq("RQ-L07-A", "L-07",
                "Does statistical co-movement provide sufficient relational information "
                "for integrity-event propagation, or is richer graph semantics required?",
                Status.PARTIAL,
                current_evidence=(
                    "The correlation graph contributes 0.0005 AUPRC: statistically "
                    "significant, substantively negligible. This bounds how much a richer "
                    "graph would have to add to matter."),
                unresolved="Whether the negligible contribution is the graph's fault or "
                           "the task's.",
                experiments=[ExperimentSpec(
                    id="EXP-L07-1",
                    hypothesis=(
                        "A semantically grounded graph increases propagation-feature "
                        "contribution above the correlation graph's 0.0005."),
                    independent_variable="graph construction",
                    dependent_variable="incremental AUPRC of the propagation block",
                    control="trailing return correlation (current)",
                    treatment="sector / ownership / news-entity graph",
                    dataset="NSE panel + relational mapping",
                    evaluation_period="validation split",
                    metrics=["incremental_auprc", "lead_time", "neighbour_precision"],
                    statistical_test="paired cluster bootstrap",
                    expected_interpretation=(
                        "Because the injected episodes are generated per instrument with "
                        "no cross-instrument mechanism, a *null* result here is expected "
                        "and would say more about the generator than about propagation."),
                    threats_to_validity=[
                        "Decisive: the episode generator injects no genuine contagion, so "
                        "this experiment is close to uninformative until real incidents "
                        "or a contagion-aware generator exist."],
                    status=Status.OPEN_QUESTION,
                    required_data=["sector or ownership mapping",
                                   "contagion-aware episode generator or real incidents"])]),
        ],
    ),

    # Some larger, more advanced models were designed but never run, because there
    # was not enough computing power.
    Limitation(
        id="L-08",
        title="Tier-2 and Tier-3 models not run",
        category=Category.COMPUTATIONAL,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "torch and the deep-learning stack are deliberately not installed. Every "
            "neural-network entry in the model registry carries status NOT RUN and no "
            "metric is reported for any of them."),
        why_it_exists="Compute and environment constraints; the adapter interface exists.",
        current_status=Status.NOT_RUN,
        current_substitute="Tier-1 CPU-only, deterministic, fully inspectable stack",
        invalidated_claims=[
            "Any claim about what a learned-embedding stack would achieve.",
            "Any claim of comprehensive model coverage.",
        ],
        still_valid=[
            "The Tier-1 stack's numbers are real and reproduce bit-identically.",
            "Tier-1 explanations are exact rather than approximate for every block.",
        ],
        required_data=["model weights and a GPU or patience"],
        future_validation="Run the registry's Tier-2 entries and report performance, "
                          "calibration, latency, memory and XAI compatibility together.",
        forbidden_phrasings=["state of the art", "best available model",
                             "all model tiers evaluated"],
        scope_note="Models: Tier-1 only; Tier-2/3 NOT RUN.",
        research_questions=[
            _rq("RQ-L08-A", "L-08",
                "How much additional research value does a higher-capacity full-stack "
                "model provide over an interpretable Tier-1 baseline, once calibration, "
                "latency, memory and explanation stability are counted alongside AUPRC?",
                Status.NOT_RUN,
                current_evidence=(
                    "The Tier-1 baseline reaches AUPRC 0.9412 on injected episodes, which "
                    "sets the bar a larger model must clear to justify its cost."),
                unresolved="The entire capacity-versus-cost trade-off.",
                experiments=[ExperimentSpec(
                    id="EXP-L08-1",
                    hypothesis=(
                        "Higher-capacity models improve AUPRC but degrade calibration and "
                        "explanation stability, so the net research value is smaller than "
                        "the headline metric suggests."),
                    independent_variable="model tier",
                    dependent_variable="AUPRC, ECE, latency, memory, XAI sign consistency",
                    control="Tier-1 gradient-boosted per-block stack",
                    treatment="Tier-2 transformer / CLIP-class stack",
                    dataset="current market panel",
                    evaluation_period="validation split",
                    metrics=["auprc", "ece", "latency_ms", "peak_memory_mb",
                             "sign_consistency"],
                    statistical_test="paired cluster bootstrap on AUPRC; paired t on latency",
                    expected_interpretation=(
                        "A capacity gain that costs calibration is a real trade-off, not "
                        "an improvement, for a system whose output is a risk probability."),
                    threats_to_validity=[
                        "Tier-2 text models may have been pretrained on data overlapping "
                        "the evaluation window, which the Tier-1 lexicon cannot be."],
                    status=Status.NOT_RUN,
                    required_data=["installed model weights"])]),
        ],
    ),

    # The model's probabilities are not perfectly honest yet -- when it says 70%
    # the real rate is not exactly 70%.
    Limitation(
        id="L-10",
        title="Calibration is imperfect",
        category=Category.EVALUATION,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "Expected calibration error for the full stack is 0.1227, materially above "
            "zero. The combination layer averages calibrated per-block scores, which does "
            "not itself guarantee a calibrated output."),
        why_it_exists="Averaging calibrated components does not preserve calibration.",
        current_status=Status.MEASURED,
        current_substitute="Reliability diagrams and ECE are published, not smoothed away",
        invalidated_claims=[
            "Any use of the score as a literal probability without recalibration.",
        ],
        still_valid=[
            "Calibration is measured with equal-mass bins and reported per arm.",
            "The uncertainty-weighted combination arm reaches ECE 0.0631, less than half the "
            "full stack's, at a cost of 0.0043 AUPRC. That trade-off is measured.",
        ],
        required_data=[],
        future_validation="Post-hoc recalibration on the training split only, then "
                          "re-measure on validation.",
        forbidden_phrasings=["well calibrated", "calibrated probability"],
        scope_note="Calibration: ECE 0.1227, imperfect.",
        research_questions=[
            _rq("RQ-L10-A", "L-10",
                "Does calibration degrade under block missingness and cross-block "
                "disagreement, and does coverage-aware recalibration recover it?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Runnable now. The dataset carries per-row coverage and the combination "
                    "layer already emits a disagreement-based uncertainty, so ECE can be "
                    "measured conditional on both."),
                unresolved="Whether recalibration helps or merely shifts the error.",
                experiments=[ExperimentSpec(
                    id="EXP-L10-1",
                    hypothesis=(
                        "ECE rises monotonically as coverage falls and as cross-block "
                        "disagreement rises."),
                    independent_variable="coverage bucket and disagreement bucket",
                    dependent_variable="ECE and Brier within bucket",
                    control="full-coverage, low-disagreement rows",
                    treatment="reduced-coverage or high-disagreement rows",
                    dataset="current market panel",
                    evaluation_period="validation split",
                    metrics=["ece", "brier", "auprc", "n_per_bucket"],
                    statistical_test="cluster bootstrap CI on per-bucket ECE",
                    expected_interpretation=(
                        "If ECE is flat across coverage, the uncertainty estimate is "
                        "already absorbing missingness; if it rises, coverage-aware "
                        "calibration is warranted."),
                    threats_to_validity=[
                        "Bucketing on a model output (disagreement) risks selection "
                        "effects; coverage is exogenous and is the safer axis."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # The final, never-touched test data has deliberately NOT been used yet. Using
    # it more than once would burn it, so it is being saved.
    Limitation(
        id="L-11",
        title="Final holdout not evaluated",
        category=Category.EVALUATION,
        severity=Severity.BOUNDS_ALL_CLAIMS,
        description=(
            "The holdout split (2024-01-01 onward, 3,352 rows) is frozen and untouched. "
            "Every reported number is on validation (2022-01-01 to 2023-12-31)."),
        why_it_exists=(
            "Deliberate methodological safeguard, not an omission: models, features, "
            "thresholds, the combination rule, XAI methods and figure definitions must "
            "be frozen first."),
        current_status=Status.FUTURE_VALIDATION,
        current_substitute="Validation-split reporting, labelled as such everywhere",
        invalidated_claims=[
            "No result in this release is an out-of-sample result in the strict sense.",
        ],
        still_valid=[
            "The freeze itself is evidence of experimental discipline and is verifiable: "
            "no code path reads the holdout split.",
        ],
        required_data=[],
        future_validation="Freeze every choice, then evaluate the holdout exactly once, "
                          "then lock it.",
        forbidden_phrasings=["out-of-sample", "holdout result", "generalises"],
        scope_note="Split: validation. Holdout FROZEN and unevaluated.",
        research_questions=[
            _rq("RQ-L11-A", "L-11",
                "Does the full stack retain its validation-split advantage under a "
                "strict freeze-and-evaluate-once protocol on a later market era?",
                Status.FUTURE_VALIDATION,
                current_evidence="None by construction. That is the point.",
                unresolved="Temporal generalisation.",
                experiments=[ExperimentSpec(
                    id="EXP-L11-1",
                    hypothesis=(
                        "Holdout AUPRC falls relative to validation but stays above the "
                        "market-only baseline."),
                    independent_variable="evaluation era",
                    dependent_variable="AUPRC, ECE, block contribution ordering",
                    control="validation split (2022-2023)",
                    treatment="holdout split (2024 onward)",
                    dataset="current market panel",
                    evaluation_period="one execution, after freeze",
                    metrics=["auprc", "ece", "lead_time", "block_contribution"],
                    statistical_test="cluster bootstrap; pre-registered direction",
                    expected_interpretation=(
                        "A large drop would indicate the validation split leaked into "
                        "model selection despite the protocol."),
                    threats_to_validity=[
                        "Single execution means no variance estimate across protocol runs.",
                        "The holdout era has different market conditions, so era and "
                        "generalisation are confounded."],
                    status=Status.FUTURE_VALIDATION,
                    required_data=["a completed freeze"])]),
        ],
    ),

    # There is not enough data to detect small differences. Some 'no difference'
    # results mean 'we could not have seen one either way'.
    Limitation(
        id="L-12",
        title="Limited statistical power",
        category=Category.EVALUATION,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "Episode counts are in the low hundreds (140 generated, 36 true windows in "
            "the validation split) and cluster-bootstrap intervals are correspondingly "
            "wide. Several ablation differences are not distinguishable from zero at 5% "
            "FDR."),
        why_it_exists="Rare events are rare, and clustering costs effective sample size.",
        current_status=Status.MEASURED,
        current_substitute="Cluster bootstrap with BH-FDR correction across the family",
        invalidated_claims=[
            "Any narrative built on a difference whose interval spans zero.",
        ],
        still_valid=[
            "26 of 31 comparisons are significant at 5% FDR, and the five that are not "
            "are reported as not significant rather than dropped.",
        ],
        required_data=["more episodes, or real incidents"],
        future_validation="Report a power curve alongside every non-significant result.",
        forbidden_phrasings=["no effect", "proves", "confirms"],
        scope_note="Power: low-hundreds episode counts; wide intervals.",
        research_questions=[
            _rq("RQ-L12-A", "L-12",
                "What effect size is detectable at the current episode count, and how "
                "many episodes would a null result need to be informative?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Runnable now: bootstrap interval width can be measured as a function "
                    "of subsampled episode count, which yields an empirical power curve "
                    "without any distributional assumption."),
                unresolved="Nothing, once the curve is computed.",
                experiments=[ExperimentSpec(
                    id="EXP-L12-1",
                    hypothesis=(
                        "Bootstrap interval half-width scales approximately as the "
                        "inverse square root of episode count, so the minimum detectable "
                        "AUPRC difference at the current count is materially larger than "
                        "the non-significant deltas observed."),
                    independent_variable="number of episodes resampled",
                    dependent_variable="bootstrap interval half-width; minimum detectable "
                                       "effect",
                    control="full episode set",
                    treatment="subsampled episode sets",
                    dataset="current per-arm per-row scores",
                    evaluation_period="validation split",
                    metrics=["ci_half_width", "minimum_detectable_effect"],
                    statistical_test="nested cluster bootstrap over subsample sizes",
                    expected_interpretation=(
                        "If the minimum detectable effect exceeds the observed "
                        "microstructure delta, that non-significant result is "
                        "uninformative rather than evidence of no effect."),
                    threats_to_validity=[
                        "Subsampling episodes changes the positive rate, which itself "
                        "moves AUPRC; the curve must be read as relative, not absolute."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # Company accounts data (sales, profits, debts) could not be obtained.
    Limitation(
        id="L-13",
        title="Company fundamentals are unavailable",
        category=Category.DATA,
        severity=Severity.BOUNDS_ALL_CLAIMS,
        description=(
            "Revenue growth, net debt, interest coverage, earnings, cash flow and "
            "profitability are absent from this repository. The NSE cash bhavcopy carries "
            "price, volume and trade counts only, and no fundamentals source was "
            "obtained. The domain framework this module implements is built around "
            "exactly these three quantities, so the lifecycle analysis runs without the "
            "signals a practitioner would actually monitor."),
        why_it_exists=(
            "Point-in-time fundamentals with disclosure timestamps are needed to avoid "
            "look-ahead, and no licence-clear source with that property was located. "
            "Reported financials without a disclosure timestamp are unusable: applying a "
            "quarter's figures from the quarter end rather than the filing date leaks "
            "weeks of future information into every historical decision."),
        current_status=Status.NOT_MEASURED,
        current_substitute=(
            "The lifecycle framework runs over market, microstructure, regime, "
            "propagation and derived blocks. No fundamental proxy is substituted, "
            "because a price-derived stand-in for revenue growth would be a market "
            "signal wearing a fundamental label."),
        invalidated_claims=[
            "Any statement that fundamental deterioration precedes, accompanies or "
            "follows a risk-state change.",
            "Any claim about revenue growth, net debt or interest coverage whatsoever.",
            "Any claim that the lifecycle analysis reflects the domain expert framework "
            "in full: it implements the temporal structure, not the fundamental inputs.",
        ],
        still_valid=[
            "The lifecycle state model, change-point detection, transition extraction "
            "and stage-differential comparison are implemented and run on real market "
            "and panel evidence.",
            "The framework accepts a fundamentals block without modification: adding one "
            "is a data task, not an architecture task.",
        ],
        required_data=[
            "Point-in-time company fundamentals for the universe: revenue, net debt, "
            "interest coverage, earnings and cash flow, each carrying the disclosure "
            "timestamp separately from the financial period, so knowledge time can be "
            "set correctly.",
        ],
        future_validation=(
            "Add the fundamentals block, re-run the stage-differential experiment, and "
            "report whether fundamental signals rank differently from market signals at "
            "entry versus at transitions."),
        forbidden_phrasings=["revenue growth", "net debt", "interest coverage",
                             "fundamental deterioration", "fundamentals show"],
        scope_note="Fundamentals: NOT AVAILABLE. Lifecycle analysis excludes them.",
        research_questions=[
            _rq("RQ-L13-A", "L-13",
                "Do fundamental indicators provide statistically detectable changes in "
                "risk before market-level signals change?",
                Status.BLOCKED,
                current_evidence=(
                    "The ordering machinery exists and has been run on the blocks that "
                    "are available: only the microstructure proxies shift before the risk "
                    "estimate, and they do so weakly. Whether fundamentals would lead is "
                    "entirely unmeasured."),
                unresolved="The expert framework's central premise.",
                experiments=[ExperimentSpec(
                    id="EXP-L13-1",
                    hypothesis=(
                        "Fundamental change points precede market change points for the "
                        "same instrument, so a fundamentals block would shift the median "
                        "signal-ordering offset negative relative to the market block."),
                    independent_variable="signal block (fundamental vs market vs full-stack)",
                    dependent_variable="offset of each block change point from the risk "
                                       "change point, in sessions",
                    control="market block ordering, already measured",
                    treatment="fundamental block ordering",
                    dataset="NSE panel + point-in-time fundamentals",
                    evaluation_period="validation split",
                    metrics=["median_offset", "share_leading", "n_instruments"],
                    statistical_test="paired comparison of per-instrument offsets; "
                                     "sign test against zero",
                    expected_interpretation=(
                        "A negative median offset for fundamentals would support the "
                        "expert premise. A zero or positive offset would indicate that "
                        "by the time a filing lands, the market has already moved -- "
                        "which is itself a publishable result about disclosure lag."),
                    threats_to_validity=[
                        "Fundamentals arrive quarterly and risk moves daily, so the "
                        "sampling rates differ by roughly sixty to one; any offset is "
                        "quantised by the reporting calendar.",
                        "Disclosure timestamps are frequently wrong in vendor data, and "
                        "an error there manufactures exactly the lead this experiment "
                        "looks for."],
                    status=Status.BLOCKED,
                    required_data=["point-in-time fundamentals with disclosure timestamps"])]),
            _rq("RQ-L13-B", "L-13",
                "Does combining fundamental deterioration with market and full-stack "
                "evidence improve detection of material risk-state transitions over "
                "market evidence alone?",
                Status.BLOCKED,
                current_evidence=(
                    "The transition-detection target and the stage-differential design "
                    "are implemented and running; the fundamental arm cannot be built."),
                unresolved="Whether fundamentals add incremental information here.",
                experiments=[ExperimentSpec(
                    id="EXP-L13-2",
                    hypothesis=(
                        "A fundamentals block adds incremental AUPRC for material "
                        "transition detection beyond market and panel evidence."),
                    independent_variable="presence of the fundamentals block",
                    dependent_variable="AUPRC for material transition within 10 sessions",
                    control="market + full-stack + regime + propagation",
                    treatment="the same plus fundamentals",
                    dataset="NSE panel + point-in-time fundamentals",
                    evaluation_period="validation split",
                    metrics=["auprc", "incremental_auprc", "lead_time", "ece"],
                    statistical_test="paired cluster bootstrap over instruments",
                    expected_interpretation=(
                        "Read against the minimum detectable effect for this sample: "
                        "an increment below roughly 0.0002 would be unresolvable here "
                        "regardless of its p-value."),
                    threats_to_validity=[
                        "Fundamentals are near-constant between filings, so a model can "
                        "exploit them as an instrument identifier rather than as a "
                        "signal; the ablation must hold instrument identity fixed."],
                    status=Status.BLOCKED,
                    required_data=["point-in-time fundamentals with disclosure timestamps"])]),
        ],
    ),

    # Valuation measures could not be obtained either, for the same reason.
    Limitation(
        id="L-14",
        title="Valuation measures are unavailable",
        category=Category.DATA,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "P/E, P/B, EV/EBITDA and free-cash-flow yield cannot be computed: each needs "
            "an accounting quantity the dataset does not contain. Price alone is not a "
            "valuation."),
        why_it_exists="Follows directly from L-13; every ratio needs the denominator.",
        current_status=Status.NOT_MEASURED,
        current_substitute=(
            "None. No price-only quantity is presented as a valuation measure, because "
            "labelling a price ratio as valuation would misdescribe what it is."),
        invalidated_claims=[
            "Any claim about valuation change, cheapness, richness or re-rating.",
        ],
        still_valid=[
            "Price behaviour, volatility, liquidity and turnover are measured directly "
            "and are labelled as market signals rather than as valuation.",
        ],
        required_data=["shares outstanding, earnings, book value, enterprise value and "
                       "free cash flow, point-in-time"],
        future_validation=(
            "Add the valuation block and test whether it carries information beyond the "
            "market block, which shares its price numerator."),
        forbidden_phrasings=["valuation", "P/E", "overvalued", "undervalued",
                             "re-rating"],
        scope_note="Valuation: NOT AVAILABLE.",
        research_questions=[
            _rq("RQ-L14-A", "L-14",
                "Does valuation carry information about risk-state transitions beyond "
                "the price behaviour it is partly built from?",
                Status.BLOCKED,
                current_evidence="None; the block cannot be constructed.",
                unresolved="Everything.",
                experiments=[]),
        ],
    ),

    # The buying and selling in the results never happened. It is a simulation on
    # historical data, with no real money anywhere.
    Limitation(
        id="L-15",
        title="Position lifecycle is hypothetical, not observed",
        category=Category.METHODOLOGICAL,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "No real position, holding period or investor decision is observed. The "
            "lifecycle framework segments each instrument's risk trajectory into ENTRY, "
            "HOLDING and RESOLUTION phases by position within an analysis window. Those "
            "are analytical phases over a risk estimate, not the phases of anyone's "
            "actual holding."),
        why_it_exists=(
            "Observed holding periods would require position-level data from real "
            "investors, which does not exist here and would carry its own privacy "
            "constraints."),
        current_status=Status.MEASURED,
        current_substitute="Window-position phases over the risk trajectory",
        invalidated_claims=[
            "Any claim about what investors did, would have done, or should do.",
            "Any claim that the phase boundaries correspond to real decision points.",
        ],
        still_valid=[
            "The phases are defined mechanically and identically for every instrument, "
            "so a stage comparison is a comparison of like with like.",
            "Nothing in the framework emits a reference price, target or position size "
            "to any surface.",
        ],
        required_data=["observed position-level holding data, if such a study were ever "
                       "run with consent"],
        future_validation=(
            "Compare window-position phases against phases anchored on real entry dates "
            "if a consented dataset ever exists."),
        forbidden_phrasings=["investors should", "when to enter", "when to exit",
                             "holding period returns"],
        scope_note="Lifecycle phases are analytical, not observed positions.",
        research_questions=[
            _rq("RQ-L15-A", "L-15",
                "Does phase defined by window position behave differently from phase "
                "anchored on a risk-state change point?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Both segmentations are implemented: window-position phases and "
                    "change-point-relative offsets. Comparing them directly is runnable "
                    "and has not yet been run."),
                unresolved="Whether the stage-differential result is an artifact of how "
                           "phase is defined.",
                experiments=[ExperimentSpec(
                    id="EXP-L15-1",
                    hypothesis=(
                        "The ranking of block importance by stage is stable whether "
                        "stages are defined by window position or by distance from a "
                        "detected change point."),
                    independent_variable="phase definition",
                    dependent_variable="per-block permutation importance ranking",
                    control="window-position phases",
                    treatment="change-point-relative phases",
                    dataset="current market panel",
                    evaluation_period="validation split",
                    metrics=["spearman_between_rankings", "top3_overlap", "auprc"],
                    statistical_test="Spearman correlation between importance vectors",
                    expected_interpretation=(
                        "A low correlation would mean the stage-differential finding "
                        "depends on an arbitrary definitional choice and should not be "
                        "reported as a property of lifecycle stages."),
                    threats_to_validity=[
                        "Change-point-relative phases are defined using the risk series "
                        "the model produces, so they are not independent of the model."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),
    # -- Stream B: the transaction-risk track and the scenario laboratory ------------

    # No free, properly labelled transaction dataset exists that we are allowed to
    # use, so one whole planned line of work is blocked.
    Limitation(
        id="L-23",
        title="No licence-clear, labelled, feature-interpretable transaction corpus",
        category=Category.LICENSING,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "The transaction-risk track executes on a declared synthetic development "
            "fixture. Five candidate corpora were assessed against six requirements and "
            "none satisfied all of them: IEEE-CIS and ULB Credit Card Fraud carry human "
            "labels but obfuscated features, so no scenario can name the feature it "
            "changes; PaySim is a simulator, so its labels are a property of that "
            "simulator; institutional records are neither public nor licensed; and NPCI "
            "publishes aggregates rather than records."),
        why_it_exists=(
            "Labelled payment records identify people and businesses, so the corpora that "
            "exist publicly are either anonymised past the point where a feature can be "
            "named, or synthetic, or aggregate. The requirement that a scenario name the "
            "feature it changes is what most of them fail, and it is not negotiable: an "
            "assumption about an unnamed principal component cannot be stated."),
        current_status=Status.BLOCKED,
        current_substitute=(
            "A declared synthetic fixture whose label rule is written out in the "
            "artifact, so a reader can see exactly why any model scores well on it. Every "
            "transaction number in the project carries the fixture caveat."),
        invalidated_claims=[
            "Any statement that this system detects, scores or ranks real transactions.",
            "Any accuracy, coverage or currency figure on the transaction track read as "
            "a measurement of a payments system.",
        ],
        still_valid=[
            "The interface is complete and runs unchanged on a frame plus a column "
            "mapping the day a qualifying corpus exists.",
            "The scenario machinery, the intervals and the exposure accounting are the "
            "same code the market track uses, so the transaction track demonstrates the "
            "framework rather than a second implementation.",
        ],
        required_data=[
            "Transaction-level records with investigation-derived labels, published "
            "feature semantics, an amount, an entity identifier, and a licence "
            "verifiable at download.",
        ],
        future_validation=(
            "Re-run the transaction catalogue on a qualifying corpus and report the "
            "difference against the fixture, which is itself the interesting comparison."),
        forbidden_phrasings=[
            "detects fraudulent transactions", "transaction fraud detection",
            "real transactions analysed", "payments system evaluation",
        ],
        scope_note="Transaction track: declared synthetic fixture, not observed "
                   "transactions.",
        research_questions=[
            _rq("RQ-L23-A", "L-23",
                "Does the scenario framework behave the same way on observed transaction "
                "data as on the declared fixture?",
                Status.BLOCKED,
                current_evidence=(
                    "None. The fixture's separability is manufactured by its own label "
                    "rule, so nothing measured on it transfers."),
                unresolved="Everything about behaviour on real transaction data.",
                experiments=[ExperimentSpec(
                    id="EXP-L23-1",
                    hypothesis=(
                        "Scenario effects measured on a qualifying transaction corpus "
                        "keep the sign and rough magnitude they have on the declared "
                        "fixture."),
                    independent_variable="corpus (declared fixture vs qualifying corpus)",
                    dependent_variable="scenario effect on the mean risk score and on "
                                       "elevated-value coverage",
                    control="the declared synthetic fixture",
                    treatment="a corpus meeting all six requirements",
                    dataset="fixture; qualifying transaction corpus",
                    evaluation_period="entity-disjoint split in both",
                    metrics=["risk_mean", "elevated_value_coverage", "review_load",
                             "auprc"],
                    statistical_test="paired cluster bootstrap over accounts",
                    expected_interpretation=(
                        "Matching signs would support the fixture as a development "
                        "instrument. Diverging signs would establish that nothing "
                        "measured on it transfers, which is the assumption currently "
                        "made."),
                    threats_to_validity=[
                        "The fixture's label rule is linear in its features, so any "
                        "scorer that is also linear will look better on it than on data "
                        "with real structure.",
                        "A real corpus has a base rate this fixture only declares."],
                    status=Status.BLOCKED,
                    required_data=["qualifying transaction corpus"])]),
        ],
    ),

    # A 'what if' simulation is not proof of cause and effect. It shows what the
    # model WOULD have said, not what would have happened.
    Limitation(
        id="L-24",
        title="Counterfactual simulation is not causal inference",
        category=Category.METHODOLOGICAL,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "The Scenario Lab reports what a fitted model would have estimated had its "
            "inputs or its declared decision rule been different. That is a statement "
            "about the model under an assumption, not about what would have happened in "
            "the world. No scenario here carries an identification strategy, and none is "
            "reported as an effect of an intervention."),
        why_it_exists=(
            "Re-scoring altered rows measures the model's sensitivity to those rows. "
            "Establishing that a real intervention would have produced the outcome "
            "additionally requires that the alteration correspond to the intervention, "
            "that nothing else move with it, and that the model remain valid under the "
            "altered distribution. None of the three is established here, and the third "
            "is unlikely: a two-sigma shift in every text feature at once is not a "
            "distribution the model was fitted on."),
        current_status=Status.MEASURED,
        current_substitute=(
            "Three simulation methods, named on every result. An observed stratum "
            "selects rows that occurred; a counterfactual alters rows under a stated "
            "assumption; a policy comparison changes a declared rule on identical "
            "evidence and is the only one of the three that isolates a decision."),
        invalidated_claims=[
            "Any statement that a scenario shows what an intervention would achieve.",
            "Any statement that a counterfactual outcome was observed, recovered or "
            "prevented.",
            "Any causal reading of a difference between two scenarios.",
        ],
        still_valid=[
            "The sensitivity of the model to each stated condition is measured, with an "
            "interval, on identical rows and one fitted model.",
            "The policy comparison holds rows, model and scores fixed and changes only "
            "the declared rule, so its difference is attributable to that rule under the "
            "declared policy.",
        ],
        required_data=[
            "An identification strategy: a natural experiment, an assignment mechanism, "
            "or an actual intervention with recorded outcomes.",
        ],
        future_validation=(
            "Where a real policy change exists with a date and an unaffected comparison "
            "group, evaluate it as a difference in differences and report the gap against "
            "the simulated estimate."),
        forbidden_phrasings=[
            "the intervention caused", "would have prevented", "recovered",
            "the scenario proves", "causal effect of the policy",
        ],
        scope_note="Scenario results are model behaviour under a stated assumption, not "
                   "causal effects.",
        research_questions=[
            _rq("RQ-L24-A", "L-24",
                "How far does a simulated counterfactual estimate sit from an effect "
                "estimated under an identification strategy?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "None: no scenario in this project has an identification strategy, "
                    "so the gap is unmeasured."),
                unresolved="The size and direction of the gap.",
                experiments=[ExperimentSpec(
                    id="EXP-L24-1",
                    hypothesis=(
                        "A simulated counterfactual estimate and a difference-in-"
                        "differences estimate of the same change agree in sign and to "
                        "within their intervals."),
                    independent_variable="estimation strategy (simulation vs "
                                         "difference in differences)",
                    dependent_variable="estimated change in the outcome",
                    control="the simulated counterfactual estimate",
                    treatment="the identified estimate from a real policy change",
                    dataset="the panel, plus a dated policy change with an unaffected "
                            "comparison group",
                    evaluation_period="windows either side of the change date",
                    metrics=["estimated_change", "interval_overlap", "sign_agreement"],
                    statistical_test="cluster bootstrap over instruments on both arms",
                    expected_interpretation=(
                        "Agreement would support simulation as a cheap proxy for a "
                        "question that usually needs an identification strategy. "
                        "Disagreement would bound every counterfactual in this project "
                        "to a statement about the model."),
                    threats_to_validity=[
                        "A dated market-structure change affects the comparison group "
                        "too, so the parallel-trends assumption has to be argued rather "
                        "than assumed.",
                        "The simulated arm alters features the real change would move "
                        "only indirectly."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # The index data we have and the period the model was tested on do not cover
    # the same dates, so they cannot be compared directly.
    Limitation(
        id="L-25",
        title="The NIFTY 50 series and the model evaluation window do not overlap",
        category=Category.DATA,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "The verified NIFTY 50 index series covers 2024-07-08 to 2026-08-14, because "
            "that is where NSE's derivatives report begins carrying an underlying price. "
            "The model evaluation this project has already run covers 2022-01-03 to "
            "2023-12-29. The two share zero sessions. The benchmark therefore cannot "
            "currently be used as a temporally aligned market variable alongside the "
            "existing model results, and no figure, statistic or scenario in this "
            "project combines them."),
        why_it_exists=(
            "Two independent facts about coverage, neither of them a defect. NSE changed "
            "its bhavcopy format in July 2024; before that the report carries no index "
            "level at all, and reconstructing one from constituents or from futures "
            "would produce a number that is not the NIFTY 50. Separately, the evaluation "
            "split was fixed long before the index was ingested and is not moved to "
            "manufacture an overlap. The gap is the honest consequence of taking both "
            "sources as they are."),
        current_status=Status.MEASURED,
        current_substitute=(
            "The two are presented side by side and never merged. `research/data/"
            "alignment.py` computes the overlap on every request rather than storing a "
            "verdict, so the status is derived from the data and will change on its own "
            "when an overlapping source arrives. `require_alignment` raises where a "
            "caller attempts a combined result, and the Scenario Lab consults the same "
            "gate before offering one."),
        invalidated_claims=[
            "Any statement associating a NIFTY 50 movement with a model assessment.",
            "Any claim that the model's risk signal describes the benchmark.",
            "Any figure plotting model output against the index on a shared axis.",
            "Any scenario whose result depends on both the index and the stored "
            "evaluation at once.",
        ],
        still_valid=[
            "The NIFTY 50 series itself, over the sessions it covers.",
            "Every model result, over the sessions it was evaluated on.",
            "Market-context statements about evidence volume inside the index window: "
            "the text corpus and the assembled panel do overlap the index, at 521 and "
            "507 shared sessions respectively.",
            "Side-by-side presentation of the index and the model evidence, each labelled "
            "with the window it covers.",
        ],
        research_questions=[
            _rq("RQ-L25-A", "L-25",
                "Does the model's behaviour on the 2022-2023 evaluation window hold on "
                "sessions the verified index series covers?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "None. The question cannot be asked of the current artifacts: they "
                    "were evaluated on a period the index series does not reach."),
                unresolved=(
                    "Whether detection quality, calibration and block contribution "
                    "are stable across the two periods."),
                experiments=[
                    ExperimentSpec(
                        id="EXP-L25-1",
                        hypothesis=(
                            "Re-evaluating the fitted model on sessions inside the "
                            "verified NIFTY 50 window yields detection metrics within "
                            "the seed noise floor of the existing evaluation."),
                        independent_variable="evaluation period",
                        dependent_variable="AUPRC, calibration error, block shares",
                        control="the existing 2022-01-03 to 2023-12-29 evaluation",
                        treatment=(
                            "an evaluation restricted to sessions inside 2024-07-08 to "
                            "2026-08-14"),
                        dataset=(
                            "data/panel/market_dataset.parquet restricted to the "
                            "index window; 2,728 instrument-sessions are available"),
                        evaluation_period="2024-07-08 to 2026-08-14",
                        metrics=["auprc", "auroc", "ece", "block contribution share"],
                        statistical_test=(
                            "paired comparison against the multi-seed noise floor from "
                            "STATS-16"),
                        expected_interpretation=(
                            "A difference inside the noise floor would mean the existing "
                            "results carry over to the index window. A difference beyond "
                            "it would mean the two periods are not interchangeable, "
                            "which is itself the finding."),
                        threats_to_validity=[
                            "The episode labels are injected, so a period difference may "
                            "reflect the injection rather than the market.",
                            "The frozen holdout must remain untouched by any re-run.",
                            "Refitting rather than re-evaluating would confound period "
                            "with training data.",
                        ],
                        status=Status.NOT_RUN,
                        required_data=[],
                    ),
                ]),
            _rq("RQ-L25-B", "L-25",
                "Is a licence-compatible NIFTY 50 series covering 2022-2023 obtainable?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "NSE Indices publishes historical index levels, but the archive this "
                    "project ingests carries none before July 2024 and redistribution of "
                    "the source is restricted."),
                unresolved=(
                    "Whether a series covering the evaluation window can be obtained "
                    "under terms compatible with this project's open-data requirement.")),
        ],
        required_data=[
            "Either a licence-compatible NIFTY 50 level series covering 2022-01-03 to "
            "2023-12-29, or a model evaluation executed on sessions inside 2024-07-08 to "
            "2026-08-14.",
        ],
        future_validation=(
            "Nothing needs to be rewritten when either arrives. The alignment status is "
            "computed from the sessions each source holds, so ingesting an overlapping "
            "series moves this limitation from NOT_ALIGNED to PARTIAL or ALIGNED without "
            "a code change, and the combined-analysis gate opens on the same arithmetic."),
        forbidden_phrasings=[
            "nifty 50 risk score",
            "the model's assessment of the nifty",
            "index-level risk signal",
            "nifty 50 was flagged",
            "the benchmark's integrity score",
        ],
        scope_note=(
            "The NIFTY 50 series and the model evaluation cover different periods and "
            "share no sessions (L-25). Results about one say nothing about the other."),
    ),
]


# ---------------------------------------------------------------------------------------
# Negative findings promoted to first-class research objects (sections 23-26, 55-59).
# These are measured results, not limitations, and they must not be quietly buried.
# ---------------------------------------------------------------------------------------

NEGATIVE_FINDINGS: list[Limitation] = [

    # NEGATIVE FINDING: one of the explanation methods (LIME) gives different
    # answers when re-run, so its explanations are not stable enough to trust.
    Limitation(
        id="N-01",
        title="LIME explanations fail the declared stability threshold",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "LIME re-run under three seeds agrees on attribution sign for 0.780 of "
            "features, below the 0.80 threshold declared before the run. Its rank "
            "agreement with occlusion is -0.042."),
        why_it_exists="Local surrogate fitting is sensitive to the perturbation sample.",
        current_status=Status.FAILED_SANITY_CHECK,
        current_substitute="Occlusion and KernelSHAP, which pass",
        invalidated_claims=["Any claim resting on a LIME attribution."],
        still_valid=[
            "Occlusion and KernelSHAP pass sparsity and model-randomisation checks and "
            "agree with each other at rho 0.472.",
            "The threshold was declared before the run and was not lowered.",
        ],
        required_data=[],
        future_validation="Increase perturbation count and re-measure; report the "
                          "stability-versus-cost curve.",
        forbidden_phrasings=["LIME shows", "LIME confirms"],
        scope_note="LIME: failed stability check; not used for any claim.",
        research_questions=[
            _rq("RQ-N01-A", "N-01",
                "How stable are local surrogate explanations under financial "
                "models, and does stability trade against runtime?",
                Status.PARTIAL,
                current_evidence=(
                    "Measured: LIME 0.02 s and unstable; occlusion 0.46 s and stable; "
                    "KernelSHAP 1.00 s and stable. The cheapest method is the unreliable "
                    "one."),
                unresolved="Whether more perturbations recover LIME's stability, and at "
                           "what cost.",
                experiments=[ExperimentSpec(
                    id="EXP-N01-1",
                    hypothesis=(
                        "LIME sign consistency rises with perturbation count and crosses "
                        "0.80 before its runtime exceeds occlusion's."),
                    independent_variable="LIME perturbation sample size",
                    dependent_variable="sign consistency, runtime",
                    control="800 perturbations (current)",
                    treatment="1600 / 3200 / 6400 perturbations",
                    dataset="current market panel",
                    evaluation_period="validation split, highest-risk rows",
                    metrics=["sign_consistency", "spearman_vs_occlusion", "seconds"],
                    statistical_test="repeated runs across seeds; report mean and spread",
                    expected_interpretation=(
                        "If stability requires more runtime than occlusion, LIME has no "
                        "remaining advantage for this model class."),
                    threats_to_validity=["Stability measured on one row may not "
                                         "generalise across the score distribution."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # NEGATIVE FINDING: adjusting for market mood made detection WORSE, not better.
    # Reported anyway, because that is the result.
    Limitation(
        id="N-02",
        title="Regime conditioning reduces detection performance",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "The corrected regime-conditioned combination reaches AUPRC 0.9412 against static "
            "attention's 0.9480. Removing regime conditioning improves AUPRC by 0.0060 "
            "(95% CI 0.0022-0.0110, BH-adjusted p 0.0021)."),
        why_it_exists="Measured, not yet explained.",
        current_status=Status.NOT_SUPPORTED,
        current_substitute="Static attention performs better and is reported as the "
                           "stronger arm",
        invalidated_claims=["RQ9: that corrected regime-conditioned combination outperforms "
                            "static combination."],
        still_valid=[
            "The degeneracy result stands independently: the inherited formulation is "
            "algebraically identical to static attention, verified below 1e-12 and "
            "confirmed empirically to six decimals.",
            "The correction does what it claims mechanically: its weights vary by regime.",
        ],
        required_data=[],
        future_validation="Test the candidate explanations below before concluding "
                          "anything about regime-aware combination in general.",
        forbidden_phrasings=["regime conditioning does not work",
                             "regimes are uninformative"],
        scope_note="Regime conditioning: NOT SUPPORTED on this evaluation.",
        research_questions=[
            _rq("RQ-N02-A", "N-02",
                "Under what conditions does regime conditioning help or hurt full-stack "
                "integrity-event detection?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Measured inputs: k=4 regimes admitted under a pre-declared rule, "
                    "bootstrap stability ARI 0.624, shuffle-null p 0.0164. The regimes "
                    "are real but the conditioning costs performance."),
                unresolved=(
                    "Which of four candidate explanations holds: noisy regime labels, "
                    "insufficient per-regime sample, variance inflation from extra "
                    "parameters, or redundancy between regime and market features."),
                experiments=[ExperimentSpec(
                    id="EXP-N02-1",
                    hypothesis=(
                        "The loss comes from variance inflation: per-regime parameters "
                        "are fitted on too few episodes, so the corrected arm should "
                        "recover as episodes per regime increase."),
                    independent_variable="episodes available per regime",
                    dependent_variable="AUPRC gap between corrected and static combination",
                    control="static attention",
                    treatment="corrected regime-conditioned combination",
                    dataset="current dataset, subsampled by episode count",
                    evaluation_period="validation split",
                    metrics=["auprc_gap", "regime_weight_variance", "episodes_per_regime"],
                    statistical_test="paired cluster bootstrap at each subsample size",
                    expected_interpretation=(
                        "A gap that shrinks with more episodes supports variance "
                        "inflation; a flat gap points to redundancy between regime and "
                        "market features instead."),
                    threats_to_validity=[
                        "Regime membership is itself estimated, so its error enters the "
                        "treatment arm but not the control."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # NEGATIVE FINDING: the system spots trouble LATE, not early. The honest name
    # for what it does is detection, not early warning.
    Limitation(
        id="N-03",
        title="Detection is late, not early",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "Median lead time is -10.0 sessions and mean -8.5: the system identifies "
            "injected episodes roughly two weeks after onset. Detection rate is 0.917 "
            "with 23 false-alarm windows against 36 true windows."),
        why_it_exists=(
            "The state machine requires persistence above a threshold before opening a "
            "window, which trades latency for precision by construction."),
        current_status=Status.NOT_SUPPORTED,
        current_substitute="None; the result stands",
        invalidated_claims=["RQ5: that risk emergence is detected early."],
        still_valid=[
            "Detection itself is high: 33 of 36 windows matched.",
            "The state machine's hysteresis parameters are the direct cause and are "
            "explicit, so the trade-off is tunable rather than mysterious.",
        ],
        required_data=[],
        future_validation="Map the full precision-versus-lead-time frontier rather than "
                          "reporting a single operating point.",
        forbidden_phrasings=["early warning", "early detection", "detects before"],
        scope_note="Timing: detection lags onset by a median 10 sessions.",
        research_questions=[
            _rq("RQ-N03-A", "N-03",
                "What is the achievable frontier between detection lead time and "
                "precision, and do different blocks carry evidence at different "
                "lags?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Runnable now. Both halves are computable from artifacts already on "
                    "disk: sweeping the entry threshold traces the frontier, and "
                    "cross-correlating each block score against the episode indicator "
                    "gives block-specific lead/lag."),
                unresolved="Whether any operating point achieves positive lead time at "
                           "useful precision.",
                experiments=[ExperimentSpec(
                    id="EXP-N03-1",
                    hypothesis=(
                        "Lowering the entry threshold buys lead time at a steep precision "
                        "cost, and text evidence leads market evidence."),
                    independent_variable="state-machine entry threshold; block",
                    dependent_variable="lead time; precision; cross-correlation lag",
                    control="entry threshold 0.55 (current operating point)",
                    treatment="entry thresholds swept from 0.20 to 0.90",
                    dataset="current per-arm per-row scores",
                    evaluation_period="validation split",
                    metrics=["median_lead_time", "precision", "false_alarm_rate",
                             "peak_cross_correlation_lag"],
                    statistical_test="cluster bootstrap CI at each threshold",
                    expected_interpretation=(
                        "A frontier that never reaches positive lead time at acceptable "
                        "precision would mean the evidence itself is lagging, not the "
                        "detector."),
                    threats_to_validity=[
                        "The injected episodes ramp gradually, so 'onset' is a generator "
                        "convention rather than a sharp event; lead time is measured "
                        "against that convention."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # NEGATIVE FINDING: the clever uncertainty-aware combining does not beat the
    # simple fixed-weight version.
    Limitation(
        id="N-04",
        title="Uncertainty-aware combination does not beat static combination",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "The uncertainty-weighted combination arm reaches AUPRC 0.9455 against static "
            "attention's 0.9480, a difference of -0.0043 whose interval spans zero "
            "(p 0.303, not significant)."),
        why_it_exists="Measured, not yet explained.",
        current_status=Status.NOT_SUPPORTED,
        current_substitute="Static attention",
        invalidated_claims=["RQ8: that uncertainty-aware combination reduces false positives."],
        still_valid=[
            "The same arm reaches ECE 0.0631 against the full stack's 0.1227: the best "
            "calibration of any arm. Judged on AUPRC alone it looks like a failure; "
            "judged on calibration it is the best arm in the family.",
        ],
        required_data=[],
        future_validation="Evaluate on selective risk and coverage, where the arm's "
                          "calibration advantage should show up if it is real.",
        forbidden_phrasings=["uncertainty combination improves", "reduces false positives"],
        scope_note="Uncertainty combination: no AUPRC advantage; best calibration.",
        research_questions=[
            _rq("RQ-N04-A", "N-04",
                "When does uncertainty-aware combination improve reliability rather than "
                "discrimination, and is AUPRC the wrong metric for judging it?",
                Status.PARTIAL,
                current_evidence=(
                    "Measured: AUPRC -0.0043 (not significant), ECE 0.0631 versus 0.1227. "
                    "The two metrics disagree about which arm is better, which is itself "
                    "the finding."),
                unresolved="Whether the calibration advantage survives on selective-risk "
                           "and coverage metrics.",
                experiments=[ExperimentSpec(
                    id="EXP-N04-1",
                    hypothesis=(
                        "The uncertainty-weighted arm dominates on selective risk at low "
                        "coverage even though it does not dominate on AUPRC."),
                    independent_variable="combination rule",
                    dependent_variable="selective risk at coverage levels; ECE; AUPRC",
                    control="static attention",
                    treatment="uncertainty-weighted combination",
                    dataset="current per-arm per-row scores",
                    evaluation_period="validation split",
                    metrics=["selective_risk", "coverage", "ece", "auprc"],
                    statistical_test="paired cluster bootstrap at each coverage level",
                    expected_interpretation=(
                        "Dominance on selective risk would mean the arm should be "
                        "preferred wherever abstention is allowed, and that reporting "
                        "AUPRC alone hid a real advantage."),
                    threats_to_validity=[
                        "Selective risk and the uncertainty used for abstention come from "
                        "the same model, so the comparison flatters any arm whose "
                        "uncertainty is merely self-consistent."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # NEGATIVE FINDING: the contagion/neighbour evidence contributes almost nothing.
    Limitation(
        id="N-05",
        title="Propagation contribution is negligible",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "Removing the propagation block changes AUPRC by 0.0005 (95% CI 0.0002-0.0009, "
            "BH-adjusted p 0.0021): statistically significant, substantively negligible."),
        why_it_exists=(
            "The episode generator injects episodes independently per instrument, so "
            "there is no cross-instrument contagion mechanism for propagation features to "
            "recover."),
        current_status=Status.NOT_SUPPORTED,
        current_substitute="None",
        invalidated_claims=["RQ7: that propagation improves early detection."],
        still_valid=[
            "The propagation features are correctly computed and point-in-time: 98.5% "
            "coverage, mean 7.6 neighbours per instrument-day.",
            "The near-null result is the *expected* outcome given the generator, which "
            "makes it a working negative control rather than a disappointment.",
        ],
        required_data=["a contagion-aware episode generator, or real incidents"],
        future_validation="Re-evaluate after adding correlated multi-instrument episodes "
                          "to the generator.",
        forbidden_phrasings=["propagation improves detection", "contagion detected"],
        scope_note="Propagation: negligible contribution under an independent-episode "
                   "generator.",
        research_questions=[
            _rq("RQ-N05-A", "N-05",
                "Is the negligible propagation contribution a property of the method or an "
                "artefact of an episode generator with no contagion?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "The generator is documented to place episodes independently per "
                    "instrument, so the null is predicted a priori."),
                unresolved="The method's behaviour under genuine contagion.",
                experiments=[ExperimentSpec(
                    id="EXP-N05-1",
                    hypothesis=(
                        "With correlated multi-instrument episodes injected along graph "
                        "edges, the propagation block's contribution rises materially "
                        "above 0.0005."),
                    independent_variable="episode generator contagion structure",
                    dependent_variable="incremental AUPRC of the propagation block",
                    control="independent per-instrument episodes (current)",
                    treatment="episodes propagated along the correlation graph with a lag",
                    dataset="NSE panel + contagion-aware generator",
                    evaluation_period="validation split",
                    metrics=["incremental_auprc", "lead_time", "neighbour_precision"],
                    statistical_test="paired cluster bootstrap",
                    expected_interpretation=(
                        "A rise would confirm the features work and the current null is a "
                        "generator artefact. No rise would indict the features."),
                    threats_to_validity=[
                        "Injecting contagion along the same graph the detector uses makes "
                        "the test partly circular; the generator must use a different "
                        "edge set from the detector."],
                    status=Status.OPEN_QUESTION,
                    required_data=["contagion-aware generator (implementable now)"])]),
        ],
    ),

    # NEGATIVE FINDING: when the signals disagree it tells you nothing extra beyond
    # the risk level you already had.
    Limitation(
        id="N-07",
        title="Signal conflict predicts forward change only through the risk level",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.SCOPES_A_CLAIM,
        description=(
            "Rows where the blocks disagree with the fused estimate show a forward "
            "material-change rate of 0.976 against 0.480 where they agree: an "
            "unconditional difference of +0.496 that looks like a strong result and is "
            "not one. Conflict is defined against the same 0.5 threshold that separates "
            "the MODERATE and ELEVATED risk bands, so a row can only register conflict "
            "when the fused estimate is already near or above that line. The coupling is "
            "so tight that only one risk decile out of ten contains enough rows both "
            "with and without conflict to compare at all, and within that decile the "
            "difference is -0.005."),
        why_it_exists=(
            "The conflict definition and the risk-band definition share a threshold. "
            "Mean risk is 0.610 on conflicting rows against 0.124 on agreeing ones, so "
            "the two groups are not comparable populations and the unconditional "
            "contrast is a restatement of the risk level."),
        current_status=Status.NOT_SUPPORTED,
        current_substitute=(
            "The risk-stratified figure, which is the only interpretable one: -0.005, "
            "resting on the single risk decile that has adequate cells on both sides."),
        invalidated_claims=[
            "That disagreement between blocks anticipates a change in the risk "
            "profile.",
            "That signal conflict is a usable early indicator of anything.",
            "Any unconditional comparison of conflicting against agreeing rows.",
        ],
        still_valid=[
            "The agreement, conflict and dominance measures are computed correctly and "
            "describe what the blocks are doing at a point in time.",
            "The stratified analysis is implemented and reports which strata had enough "
            "rows in both cells rather than pooling silently over the ones that did "
            "not: only one of ten deciles qualifies, and that is itself the result.",
        ],
        required_data=[
            "A conflict definition whose threshold is not the risk-band edge: for "
            "instance disagreement measured against each block own operating "
            "point, or a rank-based definition with no threshold at all.",
        ],
        future_validation=(
            "Redefine conflict against a threshold independent of the band edges and "
            "re-run the stratified comparison. If the within-stratum difference stays "
            "near zero under a definition that cannot be confounded this way, the "
            "negative result is a property of the measure rather than of its "
            "construction."),
        forbidden_phrasings=[
            "conflict predicts", "disagreement anticipates",
            "conflict is an early warning", "block disagreement signals"],
        scope_note=(
            "Signal conflict: no association with forward change once the risk level "
            "is held fixed."),
        research_questions=[
            _rq("RQ-N07-A", "N-07",
                "Does block disagreement carry information about forward risk change "
                "under a definition that does not share a threshold with the risk bands?",
                Status.OPEN_QUESTION,
                current_evidence=(
                    "Under the current threshold-shared definition, -0.005 within the "
                    "one usable risk stratum against +0.496 unconditionally. The "
                    "confound accounts for the whole unconditional effect."),
                unresolved="Whether any disagreement measure survives stratification.",
                experiments=[ExperimentSpec(
                    id="EXP-N07-1",
                    hypothesis=(
                        "A rank-based disagreement measure, which has no threshold to "
                        "share with the band edges, retains a non-zero within-stratum "
                        "association with forward material change."),
                    independent_variable="disagreement definition (threshold vs rank)",
                    dependent_variable="pooled within-risk-stratum difference in forward "
                                       "material-change rate",
                    control="the current threshold-based conflict measure",
                    treatment="rank disagreement across block scores",
                    dataset="current lifecycle cohort",
                    evaluation_period="validation + holdout",
                    metrics=["pooled_within_stratum_difference", "n_strata_usable"],
                    statistical_test="stratified difference with cluster bootstrap over "
                                     "instruments",
                    expected_interpretation=(
                        "A non-zero within-stratum difference would mean disagreement "
                        "carries information the current measure hides. A second null "
                        "would establish the negative result properly, since it would no "
                        "longer be attributable to the definition."),
                    threats_to_validity=[
                        "Every disagreement measure is a function of the same block "
                        "scores that produce the risk estimate, so some coupling to the "
                        "risk level is unavoidable and stratification can only remove "
                        "the part that is monotone in risk."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

    # NEGATIVE FINDING: adding synthetic training data made real-world performance
    # worse, even though the synthetic data looked realistic.
    Limitation(
        id="N-09",
        title="Synthetic augmentation degrades real-data performance despite low "
              "distributional distance",
        category=Category.NEGATIVE_RESULT,
        severity=Severity.BOUNDS_SOME_CLAIMS,
        description=(
            "Training on real rows alone reaches AUPRC 0.9390 on real validation rows. "
            "Adding 40000 copula-generated rows to 9351 real ones drops it to 0.3870, a "
            "difference of -0.5521 against a seed noise floor of 0.0088. A share sweep "
            "places the collapse between 50% and 75% synthetic: 0.9412 at 0%, 0.9439 at "
            "10%, 0.9429 at 25%, 0.9076 at 50%, 0.3856 at 75%."),
        why_it_exists=(
            "Six candidate mechanisms were measured and five are not supported: mean KS "
            "distance 0.0028, positive-rate ratio 1.01, mean pairwise correlation error "
            "0.0216, effective-rank ratio 1.11, zero out-of-range values and no "
            "memorisation. The supported mechanism is interaction loss: a tree ensemble "
            "separates real from generated rows at AUC 0.9639 while a linear model "
            "reaches 0.4952, and that 0.4687 gap is dependence structure beyond second "
            "order that a Gaussian copula cannot carry."),
        current_status=Status.NOT_SUPPORTED,
        current_substitute=(
            "Synthetic rows are confined to the training split and are 6.1% of the "
            "corpus. The test split is real-only and the builder refuses to place a "
            "generated row in any evaluation split."),
        invalidated_claims=[
            "Any statement that synthetic augmentation improves performance here.",
            "Any use of distributional distance alone as evidence that generated data "
            "is safe to train on.",
        ],
        still_valid=[
            "The generator reproduces marginals, rank correlation, class balance and "
            "feature range closely, and does not memorise the training rows.",
            "Shares at or below 25% are harmless on this task within the seed noise "
            "floor.",
        ],
        required_data=[],
        future_validation=(
            "Repeat with a generator that carries higher-order dependence and test "
            "whether the discriminator gap and the performance drop move together."),
        forbidden_phrasings=[
            "synthetic data works", "augmentation improves the model",
            "the generator is high fidelity",
        ],
        scope_note="Synthetic augmentation: measured to degrade real-data AUPRC above a "
                   "25% share on this task.",
        research_questions=[
            _rq("RQ-N09-A", "N-09",
                "Under what conditions does synthetic augmentation improve rather than "
                "degrade predictive performance?",
                Status.PARTIAL,
                current_evidence=(
                    "One condition is measured: a share at or below 25% is harmless, and "
                    "the harm above it tracks a generator that reproduces marginals but "
                    "not interactions."),
                unresolved=(
                    "Whether a generator that closes the discriminator gap also closes "
                    "the performance gap, which would establish interaction fidelity as "
                    "the operative variable rather than a correlate."),
                experiments=[ExperimentSpec(
                    id="EXP-N09-1",
                    hypothesis=(
                        "Real-data AUPRC under augmentation rises monotonically as the "
                        "tree-versus-linear discriminator gap of the generator falls, at "
                        "a fixed synthetic share."),
                    independent_variable="generator class, ordered by discriminator gap",
                    dependent_variable="AUPRC on real validation rows",
                    control="the Gaussian copula generator, discriminator gap 0.4687",
                    treatment="generators carrying higher-order dependence",
                    dataset="the panel-features shard, real validation rows for scoring",
                    evaluation_period="validation split, unchanged between arms",
                    metrics=["auprc", "discriminator_auc_trees",
                             "discriminator_auc_linear", "interaction_gap"],
                    statistical_test="paired comparison across seeds against the 0.0088 "
                                     "seed noise floor",
                    expected_interpretation=(
                        "A monotone relation would establish interaction fidelity as the "
                        "variable that decides whether augmentation helps. A flat "
                        "relation would mean the discriminator gap is a symptom rather "
                        "than the mechanism."),
                    threats_to_validity=[
                        "A richer generator may also memorise more, so the memorisation "
                        "check has to be re-run for each arm.",
                        "Discriminator AUC depends on the discriminator's own capacity, "
                        "so the same family must be used across arms."],
                    status=Status.OPEN_QUESTION,
                    required_data=[])]),
        ],
    ),

]


ALL_ENTRIES: list[Limitation] = LIMITATIONS + NEGATIVE_FINDINGS


# Find one entry by its name.
def by_id(entry_id: str) -> Limitation | None:
    for entry in ALL_ENTRIES:
        if entry.id == entry_id:
            return entry
    # Not found. Say so honestly rather than crashing, so a caller can decide what to do.
    return None


# Every research question, from every entry, in one flat list.
def research_questions() -> list[ResearchQuestion]:
    # A nested loop written as one line: for each entry, for each of its questions, collect
    # the question. It reads left to right in the same order you would say it aloud.
    return [rq for entry in ALL_ENTRIES for rq in entry.research_questions]


# Every experiment, from every question, in one flat list.
def experiments() -> list[ExperimentSpec]:
    return [ex for rq in research_questions() for ex in rq.experiments]


# The experiments that could be run today.
def runnable_now() -> list[ExperimentSpec]:
    """Specifications that need no external data. These are obligations, not ideas."""
    # PLAIN ENGLISH: "obligations, not ideas" is a sharp and uncomfortable distinction.
    # An experiment blocked by missing data is a fair excuse -- nobody could run it.
    # An experiment that needs NOTHING and has still not been run has no excuse at all. It is
    # simply outstanding work. This function makes that list impossible to look away from,
    # because it separates itself out automatically and gets counted in the summary.
    # An empty `required_data` means nothing is missing.
    return [ex for ex in experiments() if not ex.required_data]


# And the ones genuinely blocked by data that does not exist.
def blocked() -> list[ExperimentSpec]:
    return [ex for ex in experiments() if ex.required_data]


# Collect the warning labels for a set of limitations.
def scope_notes(limitation_ids: list[str]) -> list[str]:
    # PLAIN ENGLISH: this is what attaches the caveats to a result. A result declares which
    # gaps it depends on, and this hands back the warning label for each one, ready to be
    # printed alongside the number.
    out = []
    for lid in limitation_ids:
        entry = by_id(lid)
        # Skip anything unknown or with no note, rather than crashing -- a missing label
        # must not be able to bring down a report.
        if entry and entry.scope_note:
            out.append(entry.scope_note)
    return out


# Count everything up.
def summary() -> dict:
    # `Counter` tallies how many times each value appears.
    from collections import Counter
    cat = Counter(e.category.value for e in ALL_ENTRIES)
    sta = Counter(e.current_status.value for e in ALL_ENTRIES)
    return {
        "version": REGISTRY_VERSION,
        # How many known gaps.
        "n_limitations": len(LIMITATIONS),
        # How many things were tried that did not work. Published, not buried.
        "n_negative_findings": len(NEGATIVE_FINDINGS),
        # How many open questions, and how many experiments designed to settle them.
        "n_research_questions": len(research_questions()),
        "n_experiment_specs": len(experiments()),
        # THE TWO NUMBERS THAT MATTER MOST. The first is outstanding work with no excuse;
        # the second is work genuinely prevented by missing data. Publishing both, side by
        # side, is a project telling on itself in public.
        "n_runnable_now": len(runnable_now()),
        "n_blocked_by_data": len(blocked()),
        # And the breakdown by kind and by status.
        "by_category": dict(cat),
        "by_status": dict(sta),
    }


# The whole register as labelled boxes, ready to be saved or served to the website.
def to_dict() -> dict:
    # A tiny helper that turns one record into boxes. It handles the nesting automatically,
    # so questions inside limitations and experiments inside questions all come along too.
    def _enc(o):
        d = asdict(o)
        return d
    return {
        "version": REGISTRY_VERSION,
        "summary": summary(),
        "limitations": [_enc(x) for x in LIMITATIONS],
        # Note the negative findings are a separate, equally prominent section -- not an
        # appendix, and not folded in among the limitations where they would be easy to miss.
        "negative_findings": [_enc(x) for x in NEGATIVE_FINDINGS],
    }


# Save the whole register to disk.
def write(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # `indent=2` so a human can read it; `default=str` so anything json cannot handle is
    # written as text instead of stopping the save.
    path.write_text(json.dumps(to_dict(), indent=2, default=str), encoding="utf-8")
    return path
