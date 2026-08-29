"""Currency values, and the only form in which this project may state one.

A rupee figure is the single most quotable thing a risk system can produce and the single
easiest to misread. Every currency value here is the product of

    a *difference in a modelled tail statistic*  x  a *declared notional base*

evaluated in simulation, on historical rows, under a hypothetical exposure policy that
was never applied to anyone's capital. None of it is money that moved.

The notional is declared rather than inferred because there is no real book behind this
system. Its size is arbitrary and stated as such: it scales every figure linearly, so a
reader who prefers a different base can multiply. What it must never become is an implied
claim about assets under management.

PLAIN ENGLISH -- what this whole file is about:

THE MOST DANGEROUS NUMBER IN THE WHOLE PROJECT IS A NUMBER WITH A CURRENCY SIGN ON IT.

Here is why. Suppose a report contains the sentence:

    "The system reduced tail losses by Rs 2.4 crore."

That sentence will be repeated. It will go on a slide. It will end up in a headline. And
by the time it gets there, every one of the following will have quietly fallen off:
  * that it was a SIMULATION, not something that happened;
  * that no actual money was involved, anywhere, at any point;
  * that it is a percentage multiplied by a made-up starting amount;
  * that the made-up starting amount was chosen arbitrarily.

Nobody has to lie for this to happen. A rupee figure is simply the most quotable thing a
system like this can produce, and quoting strips context by its nature.

SO THIS FILE MAKES THAT STRIPPING IMPOSSIBLE, BY DESIGN.

Every currency figure here is one calculation:
    (a modelled percentage difference)  x  (a starting amount we openly made up)

The starting amount -- the "notional" -- is Rs 100,000,000 (ten crore). It is arbitrary,
and it says so. It is a stick to measure with, not a claim that anybody has that money.
Because everything scales linearly, a reader who thinks a different base is more relevant
can simply multiply.

AND THE ENFORCEMENT: the `label` method builds the full sentence, complete with its
caveat, and there is deliberately NO SHORT VERSION. You cannot ask this object for just
the number. The warning is welded to the figure, so the only way to strip it is to
deliberately take it apart -- which is a decision somebody would have to make on purpose,
rather than an accident of copying.
"""
# Treat type hints as plain text rather than working them out immediately.
from __future__ import annotations

# For building tidy record types.
from dataclasses import dataclass

#: Declared notional research base, in rupees. Arbitrary and linear: every currency
#: figure in this project is a fraction of it, and quoting a figure without quoting the
#: base is the error :func:`label` exists to prevent.
# PLAIN ENGLISH: ten crore rupees. Chosen because it is a round, obviously illustrative
# number. The underscores are just Python letting us write big numbers readably -- they
# have no effect on the value.
NOTIONAL_RESEARCH_BASE_INR = 100_000_000.0

# The wording used to describe that base, written once so it is identical everywhere.
NOTIONAL_LABEL = "declared notional research base of Rs 100,000,000"

#: The wording every currency figure is shown with. One string so the caveat cannot drift
#: between the paper, the artifacts and the interface.
# PLAIN ENGLISH: the reason for one single copy is important. If the warning were written
# out separately in the paper, the website and the data files, then over time somebody
# would shorten one of them "for space", and the three would gradually stop agreeing. One
# copy means the caveat is identical everywhere, forever, by construction.
CURRENCY_CAVEAT = (
    # Note how much work this sentence does: simulation, historical, hypothetical, no
    # capital at risk, not money that moved, not a return, not achievable. Seven separate
    # ways of saying the same thing, because each blocks a different misreading.
    "Estimated in simulation on a %s. Historical rows, a hypothetical exposure policy, "
    "and no capital at risk. This is not money that moved, not a return, and not an "
    "achievable outcome." % NOTIONAL_LABEL
)


# Frozen: a published figure must not be editable after the fact.
@dataclass(frozen=True)
class CurrencyEstimate:
    """A rupee figure that carries its own provenance and refuses to be quoted bare."""
    # PLAIN ENGLISH: "refuses to be quoted bare" is the design in four words.

    #: What the underlying fraction measures, e.g. "daily 5% tail loss".
    quantity: str
    #: The modelled difference, as a fraction of the notional.
    # NOTE what is stored: the FRACTION, not the rupee amount. The rupee figure is worked
    # out on demand. So the object's actual content is a percentage, and the money is only
    # ever a presentation of it.
    fraction: float
    # The plausible range for that fraction, so the figure never appears without its
    # uncertainty.
    fraction_ci_low: float | None = None
    fraction_ci_high: float | None = None
    # The base it is measured against, carried on every single estimate rather than assumed.
    notional: float = NOTIONAL_RESEARCH_BASE_INR

    @property
    # The rupee amount: the fraction times the base. One multiplication, no hidden steps.
    def amount(self) -> float:
        return self.fraction * self.notional

    @property
    # The bottom of the range in rupees, or nothing if no range was supplied.
    def amount_ci_low(self) -> float | None:
        return None if self.fraction_ci_low is None \
            else self.fraction_ci_low * self.notional

    @property
    # The top of the range in rupees.
    def amount_ci_high(self) -> float | None:
        return None if self.fraction_ci_high is None \
            else self.fraction_ci_high * self.notional

    # THE ENFORCEMENT.
    def label(self) -> str:
        """The full sentence. There is no short form, deliberately."""
        # PLAIN ENGLISH: "deliberately" is the operative word. It would have been trivial to
        # add a `short_label()` that returns just "Rs 2.4 crore". It is not there, and its
        # absence is the whole safeguard. Ask this object to describe itself and you get the
        # figure, the range, and the warning -- all or nothing.
        body = "Estimated reduction in the %s: %s" % (self.quantity, inr(self.amount))
        # Add the range if we have one.
        if self.amount_ci_low is not None and self.amount_ci_high is not None:
            # The `%%` is how you write a literal percent sign when the string is also being
            # used for filling in gaps.
            body += " (95%% CI %s to %s)" % (inr(self.amount_ci_low),
                                             inr(self.amount_ci_high))
        # And the caveat, welded on the end. There is no path through this method that omits
        # it.
        return "%s. %s" % (body, CURRENCY_CAVEAT)

    # The full record, for saving.
    def to_dict(self) -> dict:
        return {
            "quantity": self.quantity,
            # The underlying fraction and its range are given first, so a reader can see the
            # money is derived from a percentage rather than being a primary measurement.
            "fraction": self.fraction,
            "fraction_ci_low": self.fraction_ci_low,
            "fraction_ci_high": self.fraction_ci_high,
            # The base, and its wording, so the figure can never be read without it.
            "notional_inr": self.notional,
            "notional_label": NOTIONAL_LABEL,
            "amount_inr": self.amount,
            "amount_ci_low_inr": self.amount_ci_low,
            "amount_ci_high_inr": self.amount_ci_high,
            # The full sentence.
            "label": self.label(),
            # And the caveat again on its own, so a program consuming this file can find and
            # display it without having to parse the sentence apart.
            "caveat": CURRENCY_CAVEAT,
            # An explicit machine-readable flag: this was NOT observed. A program can check
            # this without understanding any English at all.
            "is_observed": False,
            # And one more plain-English restatement, phrased as instructions for how to read
            # the number. The final clause is the bluntest: nothing was recovered.
            "reading": ("A simulated difference between two hypothetical policies on "
                        "historical rows, expressed on a declared notional. No "
                        "intervention was performed and nothing was recovered."),
        }


# Write a rupee amount the way people in India actually write them.
def inr(amount: float) -> str:
    """Format rupees the way a reader in India reads them, with an explicit unit."""
    # PLAIN ENGLISH: India groups large numbers differently from Britain or America.
    #   1 lakh  = 100,000        (a hundred thousand)
    #   1 crore = 10,000,000     (ten million, or a hundred lakh)
    # Writing "Rs 2.4 crore" is natural and instantly graspable to the intended reader;
    # writing "Rs 24,000,000" is technically the same and reads as a wall of digits.
    a = abs(amount)
    # Handle the sign separately, so we can format the size cleanly and put the minus back.
    sign = "-" if amount < 0 else ""
    # Ten million or more: express in crore.
    if a >= 1e7:
        return "%sRs %.2f crore" % (sign, a / 1e7)
    # A hundred thousand or more: express in lakh.
    if a >= 1e5:
        return "%sRs %.2f lakh" % (sign, a / 1e5)
    # Smaller than that: plain rupees, with no decimal places, since fractions of a rupee
    # are not meaningful at this scale.
    return "%sRs %.0f" % (sign, a)
