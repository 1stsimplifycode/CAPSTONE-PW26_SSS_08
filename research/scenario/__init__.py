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

PLAIN ENGLISH -- what this whole file is about:

THE "WHAT IF" LAB, and the guard rails that stop it lying.

This part of the project answers questions like "what would the model have said if the
market had been more turbulent?" or "what if we had used a stricter threshold?".

Useful. Also dangerous, because a "what if" answer looks EXACTLY like a real answer once
it is written down as a number. So this file builds two guard rails, and -- importantly --
they are enforced by code that actually refuses things, not by a note asking people to be
careful.

GUARD RAIL 1: LABEL WHETHER IT HAPPENED.
There are three genuinely different kinds of scenario, and they are easy to confuse:

  OBSERVED_STRATUM -- "Look only at the days that were genuinely turbulent."
        These days REALLY HAPPENED. We simply filtered. Nothing invented.

  COUNTERFACTUAL -- "Pretend every day had been 30% more turbulent."
        These days DID NOT HAPPEN. We altered the data and re-ran. The answer is real
        only if the assumption is, and the assumption travels with the number.

  POLICY_COUNTERFACTUAL -- "Same real days, same model, different decision rule."
        The evidence is real; only the response to it is hypothetical.

Mixing these up is the classic failure. "Our system performed well in turbulent markets"
means something solid if it was the first kind and something much weaker if it was the
second -- and the sentence reads identically either way. So every result is stamped with
which kind it is.

GUARD RAIL 2: THIS THING NEVER DOES ANYTHING.
It analyses. It does not act. It places no trade, blocks no payment, approves nothing,
contacts nobody. And rather than promising this, the file keeps a list of phrases that
describe ACTING on the world, and REFUSES to run when it sees one.

Look at the trigger list further down and notice something clever. It does not just watch
for the word "block". It watches for "hold the payment", "freeze the account", "suspend
the account" -- all the natural ways somebody would describe blocking without using that
word. The comment says why: the first version watched only for the obvious word, and "hold
the payment" walked straight past it.

And note who these rails are really for. Not a villain -- a busy colleague in six months
who genuinely does not realise that wiring this into a system that holds payments is a
different kind of thing altogether.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building a fixed menu of allowed choices, where each is also a piece of text.
from enum import StrEnum

# A label for this version.
SCENARIO_VERSION = "scenario-v1"


class SimulationMethod(StrEnum):
    """How a scenario's evaluation rows were obtained. Load-bearing, not descriptive."""
    # PLAIN ENGLISH: "load-bearing" is a builder's word for a wall you cannot remove without
    # the house falling down. It means this label is not a helpful note attached to the
    # result -- it changes what the result MEANS. Two identical-looking numbers with
    # different labels here are different kinds of claim about the world.

    #: Real rows satisfying a stated condition. The condition filters; nothing is altered.
    # Days that genuinely occurred. The strongest kind of evidence available here.
    OBSERVED_STRATUM = "OBSERVED_STRATUM"
    #: Evaluation rows altered under a stated assumption, then re-scored. Nothing
    #: here was observed.
    # Invented data. Only as good as the assumption behind it, which must be stated
    # alongside the number every single time it is shown.
    COUNTERFACTUAL = "COUNTERFACTUAL"
    #: The rows and the model are unchanged; a declared decision policy differs. The
    #: comparison is between two policies on identical evidence.
    # A halfway case, and worth its own name: the world is real, only our response to it is
    # hypothetical. Stronger than a full counterfactual, weaker than a pure observation.
    POLICY_COUNTERFACTUAL = "POLICY_COUNTERFACTUAL"


#: Language a scenario result may use for its outcome, and what each word commits to.
# PLAIN ENGLISH: an approved vocabulary, with each word's exact meaning pinned down. In
# everyday speech "observed", "estimated" and "simulated" blur together. Here they are three
# different strengths of claim, and the definitions are written down so nobody has to guess.
OUTCOME_VOCABULARY = {
    # It happened, and we watched it.
    "observed": "measured on rows that occurred, with no modification",
    # A model produced it from real inputs.
    "estimated": "produced by a model from observed inputs",
    # A model produced it from INVENTED inputs. Weakest of the three.
    "simulated": "produced by a model from inputs altered under a stated assumption",
    # And an honest fourth: we genuinely cannot tell the two apart.
    "uncertain": "the interval around the estimate overlaps the comparison",
}

#: Words that turn a simulation into a claim about the world. Scanned for, not trusted to
#: discipline. "Recovered" is first because it is the one a summary reaches for.
# PLAIN ENGLISH: "scanned for, not trusted to discipline" means the code goes looking for
# these words rather than relying on everyone remembering not to use them.
# And the note about "recovered" shows real self-knowledge. When somebody summarises this
# work, "recovered Rs 2.4 crore" is the phrase that will come naturally to them -- and it
# asserts that money changed hands, which never happened. So it is listed first.
FORBIDDEN_OUTCOME_PHRASES = (
    "recovered", "money recovered", "profit generated", "guaranteed savings",
    "loss prevented", "prevented the loss", "ai diagnosed", "ai selected",
    "ai decided", "ai recovered", "cases recovered", "transactions recovered",
    "intervention caused", "caused recovery", "guaranteed return",
)

#: Purposes this module refuses. Each names an action on the world rather than an
#: analysis of it; the Scenario Lab has no mechanism for any of them and must not acquire
#: one by being described as if it did.
# PLAIN ENGLISH: the last clause is the subtle and clever bit. The worry is not only that
# somebody wires up a trading connection. It is that somebody DESCRIBES this module as the
# thing that blocks payments -- and then, over time, somebody else builds the mechanism to
# match the description. Refusing the description blocks that path at the start.
FORBIDDEN_ACTIONS = {
    "execution": "No order, trade or transfer is placed. The Scenario Lab simulates; it "
                 "has no execution path and must not be given one.",
    # Note the reasoning offered, not just the prohibition: a risk estimate is evidence for
    # a person to weigh, not an action a system takes on its own.
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
# PLAIN ENGLISH: an honest record of a bug that was found and fixed. Version one watched for
# the word "block". Somebody wrote "automatically hold the payment" -- which is blocking, in
# plain English, using none of the watched words -- and it sailed through. So the list was
# rewritten around what people ACTUALLY SAY rather than around the official term.
FORBIDDEN_ACTION_TRIGGERS: dict[str, str] = {
    # All the ways of saying "make a trade happen".
    "execute trade": "execution", "place order": "execution",
    "place an order": "execution", "execute the transaction": "execution",
    "submit order": "execution", "route to broker": "execution",
    "settle the trade": "execution",
    # All the ways of saying "stop somebody's money moving".
    "block the payment": "blocking", "block the transaction": "blocking",
    "freeze the account": "blocking", "hold the payment": "blocking",
    "suspend the account": "blocking",
    # All the ways of saying "decide yes or no automatically".
    "approve the transaction": "approval", "reject the transaction": "approval",
    "auto-approve": "approval", "auto-reject": "approval",
    "adjudicate": "approval",
    # All the ways of saying "reach out to a person".
    "contact the customer": "contact", "notify the customer": "contact",
    "email the customer": "contact", "call the account holder": "contact",
    "report to the regulator": "contact",
    # And all the ways of saying "tell somebody what to do with their money".
    "buy signal": "advice", "sell signal": "advice", "target price": "advice",
    "portfolio allocation": "advice", "investment recommendation": "advice",
    "what to buy": "advice", "when to exit": "advice",
}


# A new kind of error, for when somebody tries to make this act on the world.
class ForbiddenAction(RuntimeError):
    """Raised when a purpose would route the Scenario Lab into acting on the world."""


# The gate, called at the start of every scenario run.
def assert_no_execution(purpose: str) -> None:
    """Refuse a purpose that names an action rather than an analysis.

    Called at the entry point of every scenario run. It cannot stop someone writing new
    code that executes something; what it stops is this module being *routed* toward such
    a use through its own interface, which is the realistic path.
    """
    # PLAIN ENGLISH: an unusually honest statement of what a safety measure can and cannot
    # do. A determined person could write entirely new code that trades. This check does not
    # pretend to prevent that -- nothing could.
    # What it DOES prevent is the realistic version: somebody gradually pointing this
    # existing module at a live system, one small reasonable-seeming step at a time. That is
    # how these things actually happen, and that is the path this closes.
    # `(purpose or "")` handles being given nothing at all without crashing, and `.lower()`
    # makes the check work whatever capitals were used.
    low = (purpose or "").lower()
    for trigger, action in FORBIDDEN_ACTION_TRIGGERS.items():
        if trigger in low:
            # Refuse, quoting the purpose, naming the category, and giving the full reason.
            # A bare "not allowed" would invite somebody to reword their way round it; the
            # explanation makes clear it is the intent, not the phrasing, that is refused.
            raise ForbiddenAction(
                "%r routes to the forbidden action %r: %s"
                % (purpose, action, FORBIDDEN_ACTIONS[action]))


# The other gate: check the words used to describe a result.
def assert_outcome_language(text: str, where: str = "scenario outcome") -> None:
    """Refuse outcome text that reports a simulation as something that happened."""
    low = (text or "").lower()
    # Collect every forbidden phrase found, rather than stopping at the first, so somebody
    # fixing the wording sees all the problems at once instead of one per attempt.
    hits = [p for p in FORBIDDEN_OUTCOME_PHRASES if p in low]
    if hits:
        raise ForbiddenAction(
            # And the message names the actual fault -- claiming an observed outcome that a
            # simulation cannot support -- rather than just listing banned words. `sorted`
            # keeps the message identical between runs.
            "%s asserts an observed outcome a simulation cannot support: %s"
            % (where, ", ".join(sorted(hits))))
