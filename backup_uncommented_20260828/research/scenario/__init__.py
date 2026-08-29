"""Counterfactual scenario analysis over the existing risk models.

The Scenario Lab answers one question: *what would the model have reported under a
different, stated set of conditions?* It adds no model, no dataset and no metric. Every
scenario is executed by the same fitting harness, the same perturbation primitives, the
same exposure policy and the same bootstrap machinery the headline results use, so a
scenario number and a headline number are the same kind of object.

Two rules are enforced mechanically rather than promised, because both are the failure
this module invites:

**A simulated outcome is never an observed one.** Every scenario result carries a
:class:`SimulationMethod`, and the two methods mean genuinely different things:

``OBSERVED_STRATUM``   the model is evaluated on a subset of rows that actually occurred
                       and satisfy a stated condition. Nothing is simulated; the
                       condition is a filter. What is reported is model behaviour on
                       real rows.
``COUNTERFACTUAL``     the evaluation rows are modified under a stated assumption and the
                       model is re-scored. Nothing here happened. The outcome is what the
                       model would have reported *if* the assumption held, and the
                       assumption is carried beside the number everywhere it is shown.

Reporting a counterfactual as an event, or a stratum as an intervention, is the mistake
this distinction exists to prevent.

**Nothing is executed.** :func:`assert_no_execution` refuses any purpose that routes this
module toward acting on a market, a customer or an account. The Scenario Lab analyses,
simulates and compares. It places no order, blocks no payment, approves nothing, contacts
nobody, and produces no instruction that a person or a system could act on.

Currency figures obey a third rule, in :mod:`research.scenario.money`: a rupee value may
only ever be an *estimated* quantity on a *declared notional base*, in simulation. There
is no recovered money anywhere in this project, because no intervention was ever
performed.
"""
from __future__ import annotations

from enum import StrEnum

SCENARIO_VERSION = "scenario-v1"


class SimulationMethod(StrEnum):
    """How a scenario's evaluation rows were obtained. Load-bearing, not descriptive."""

    #: Real rows satisfying a stated condition. The condition filters; nothing is altered.
    OBSERVED_STRATUM = "OBSERVED_STRATUM"
    #: Evaluation rows altered under a stated assumption, then re-scored. Nothing
    #: here was observed.
    COUNTERFACTUAL = "COUNTERFACTUAL"
    #: The rows and the model are unchanged; a declared decision policy differs. The
    #: comparison is between two policies on identical evidence.
    POLICY_COUNTERFACTUAL = "POLICY_COUNTERFACTUAL"


#: Language a scenario result may use for its outcome, and what each word commits to.
OUTCOME_VOCABULARY = {
    "observed": "measured on rows that occurred, with no modification",
    "estimated": "produced by a model from observed inputs",
    "simulated": "produced by a model from inputs altered under a stated assumption",
    "uncertain": "the interval around the estimate overlaps the comparison",
}

#: Words that turn a simulation into a claim about the world. Scanned for, not trusted to
#: discipline. "Recovered" is first because it is the one a summary reaches for.
FORBIDDEN_OUTCOME_PHRASES = (
    "recovered", "money recovered", "profit generated", "guaranteed savings",
    "loss prevented", "prevented the loss", "ai diagnosed", "ai selected",
    "ai decided", "ai recovered", "cases recovered", "transactions recovered",
    "intervention caused", "caused recovery", "guaranteed return",
)

#: Purposes this module refuses. Each names an action on the world rather than an
#: analysis of it; the Scenario Lab has no mechanism for any of them and must not acquire
#: one by being described as if it did.
FORBIDDEN_ACTIONS = {
    "execution": "No order, trade or transfer is placed. The Scenario Lab simulates; it "
                 "has no execution path and must not be given one.",
    "blocking": "No financial activity is blocked, held or frozen. A risk estimate is "
                "evidence for a person to weigh, not an action the system takes.",
    "approval": "No financial activity is approved or rejected. Automated adjudication "
                "is outside scope and outside what the evidence supports.",
    "contact": "No customer, counterparty or authority is contacted. The system produces "
               "analysis, and who reads it is a human decision.",
    "advice": "No buy, sell, hold, target or exposure instruction is produced for any "
              "person. See docs/NON_ADVISORY.md.",
}

#: Phrases that route to a forbidden action without naming it. Written for the same
#: reason the affective guard has one: the first version keyed on the canonical word and
#: let "automatically hold the payment" through.
FORBIDDEN_ACTION_TRIGGERS: dict[str, str] = {
    "execute trade": "execution", "place order": "execution",
    "place an order": "execution", "execute the transaction": "execution",
    "submit order": "execution", "route to broker": "execution",
    "settle the trade": "execution",
    "block the payment": "blocking", "block the transaction": "blocking",
    "freeze the account": "blocking", "hold the payment": "blocking",
    "suspend the account": "blocking",
    "approve the transaction": "approval", "reject the transaction": "approval",
    "auto-approve": "approval", "auto-reject": "approval",
    "adjudicate": "approval",
    "contact the customer": "contact", "notify the customer": "contact",
    "email the customer": "contact", "call the account holder": "contact",
    "report to the regulator": "contact",
    "buy signal": "advice", "sell signal": "advice", "target price": "advice",
    "portfolio allocation": "advice", "investment recommendation": "advice",
    "what to buy": "advice", "when to exit": "advice",
}


class ForbiddenAction(RuntimeError):
    """Raised when a purpose would route the Scenario Lab into acting on the world."""


def assert_no_execution(purpose: str) -> None:
    """Refuse a purpose that names an action rather than an analysis.

    Called at the entry point of every scenario run. It cannot stop someone writing new
    code that executes something; what it stops is this module being *routed* toward such
    a use through its own interface, which is the realistic path.
    """
    low = (purpose or "").lower()
    for trigger, action in FORBIDDEN_ACTION_TRIGGERS.items():
        if trigger in low:
            raise ForbiddenAction(
                "%r routes to the forbidden action %r: %s"
                % (purpose, action, FORBIDDEN_ACTIONS[action]))


def assert_outcome_language(text: str, where: str = "scenario outcome") -> None:
    """Refuse outcome text that reports a simulation as something that happened."""
    low = (text or "").lower()
    hits = [p for p in FORBIDDEN_OUTCOME_PHRASES if p in low]
    if hits:
        raise ForbiddenAction(
            "%s asserts an observed outcome a simulation cannot support: %s"
            % (where, ", ".join(sorted(hits))))
