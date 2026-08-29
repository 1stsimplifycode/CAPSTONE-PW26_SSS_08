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
"""
from __future__ import annotations

from dataclasses import dataclass

#: Declared notional research base, in rupees. Arbitrary and linear: every currency
#: figure in this project is a fraction of it, and quoting a figure without quoting the
#: base is the error :func:`label` exists to prevent.
NOTIONAL_RESEARCH_BASE_INR = 100_000_000.0

NOTIONAL_LABEL = "declared notional research base of Rs 100,000,000"

#: The wording every currency figure is shown with. One string so the caveat cannot drift
#: between the paper, the artifacts and the interface.
CURRENCY_CAVEAT = (
    "Estimated in simulation on a %s. Historical rows, a hypothetical exposure policy, "
    "and no capital at risk. This is not money that moved, not a return, and not an "
    "achievable outcome." % NOTIONAL_LABEL
)


@dataclass(frozen=True)
class CurrencyEstimate:
    """A rupee figure that carries its own provenance and refuses to be quoted bare."""

    #: What the underlying fraction measures, e.g. "daily 5% tail loss".
    quantity: str
    #: The modelled difference, as a fraction of the notional.
    fraction: float
    fraction_ci_low: float | None = None
    fraction_ci_high: float | None = None
    notional: float = NOTIONAL_RESEARCH_BASE_INR

    @property
    def amount(self) -> float:
        return self.fraction * self.notional

    @property
    def amount_ci_low(self) -> float | None:
        return None if self.fraction_ci_low is None \
            else self.fraction_ci_low * self.notional

    @property
    def amount_ci_high(self) -> float | None:
        return None if self.fraction_ci_high is None \
            else self.fraction_ci_high * self.notional

    def label(self) -> str:
        """The full sentence. There is no short form, deliberately."""
        body = "Estimated reduction in the %s: %s" % (self.quantity, inr(self.amount))
        if self.amount_ci_low is not None and self.amount_ci_high is not None:
            body += " (95%% CI %s to %s)" % (inr(self.amount_ci_low),
                                             inr(self.amount_ci_high))
        return "%s. %s" % (body, CURRENCY_CAVEAT)

    def to_dict(self) -> dict:
        return {
            "quantity": self.quantity,
            "fraction": self.fraction,
            "fraction_ci_low": self.fraction_ci_low,
            "fraction_ci_high": self.fraction_ci_high,
            "notional_inr": self.notional,
            "notional_label": NOTIONAL_LABEL,
            "amount_inr": self.amount,
            "amount_ci_low_inr": self.amount_ci_low,
            "amount_ci_high_inr": self.amount_ci_high,
            "label": self.label(),
            "caveat": CURRENCY_CAVEAT,
            "is_observed": False,
            "reading": ("A simulated difference between two hypothetical policies on "
                        "historical rows, expressed on a declared notional. No "
                        "intervention was performed and nothing was recovered."),
        }


def inr(amount: float) -> str:
    """Format rupees the way a reader in India reads them, with an explicit unit."""
    a = abs(amount)
    sign = "-" if amount < 0 else ""
    if a >= 1e7:
        return "%sRs %.2f crore" % (sign, a / 1e7)
    if a >= 1e5:
        return "%sRs %.2f lakh" % (sign, a / 1e5)
    return "%sRs %.0f" % (sign, a)
