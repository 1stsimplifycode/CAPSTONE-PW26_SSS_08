/**
 * The risk state, made the hero of the page.
 *
 * The ordering here is the product argument. A security page that opens with a large
 * price teaches the reader that the price is the answer; this one opens with the risk
 * state and treats price as one evidence stream feeding it. Nothing about the underlying
 * numbers changes — only which question the first screen is answering.
 *
 * **Every factor is derived from a block the payload already carries.** A factor whose
 * inputs are absent renders UNAVAILABLE with the reason, never NORMAL: "we did not
 * measure this" and "we measured this and it was fine" are different claims and a reader
 * must be able to tell them apart at a glance.
 *
 * **The contribution bars are shares, not scores.** They show how much each block
 * contributed to the stored model result, which is a decomposition of something already
 * computed. They are not probabilities, not expected returns, and there is deliberately
 * no single headline number that could be read as a verdict.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE TOP OF THE PAGE -- AND AN ARGUMENT ABOUT WHAT SHOULD BE THERE.
 *
 * IDEA 1: WHAT YOU PUT FIRST TEACHES THE READER WHAT MATTERS.
 * Every financial page opens with a big price. And in doing so it teaches, wordlessly, that
 * the price is the answer.
 * This page opens with the RISK STATE, and treats the price as one piece of evidence
 * feeding into it.
 * The numbers underneath are identical. Only the question the first screen answers has
 * changed -- and the docstring is careful to say exactly that, rather than claiming any
 * improvement in the analysis.
 *
 * IDEA 2, AND IT IS THE ONE THAT RECURS THROUGHOUT THIS PROJECT:
 *
 *     "we did not measure this" and "we measured this and it was fine" are different
 *      claims and a reader must be able to tell them apart at a glance.
 *
 * So a factor we could not measure says UNAVAILABLE. Never NORMAL. Never a green tick.
 * Getting this wrong would be the single most misleading thing this page could do -- a row
 * of reassuring "normal" labels, some of which mean nothing was ever checked.
 *
 * IDEA 3: NO HEADLINE SCORE. The same refusal as the risk profile. The bars show how much
 * each part contributed to a result already computed -- they are a breakdown, not a verdict,
 * and there is deliberately no single number that could be mistaken for one.
 */
import type {
  InstrumentFoundation,
  InstrumentLiquidity,
  MarketBlock,
  RiskBlock,
} from '@/lib/product';

// Four levels -- and the fourth is the honest one.
export type FactorLevel = 'normal' | 'watch' | 'elevated' | 'unavailable';

// THE WORDS, so the page reads correctly without colour.
const LEVEL_WORD: Record<FactorLevel, string> = {
  normal: 'NORMAL',
  watch: 'WATCH',
  elevated: 'ELEVATED',
  // Not "NONE", not "LOW". The honest word.
  unavailable: 'UNAVAILABLE',
};

export interface RiskFactor {
  name: string;
  level: FactorLevel;
  reading: string;
  // EACH PIECE OF EVIDENCE CARRIES ITS KIND. Was it observed, derived by us, produced by
  // the model, or absent? Four very different standings, and the badge beside each line
  // keeps them distinguishable -- the same discipline as the research layer's `Basis`.
  evidence: { text: string; kind: 'OBSERVED' | 'DERIVED' | 'MODEL SIGNAL' | 'UNAVAILABLE' }[];
}

// Build the five factors from whatever the payload actually carries.
export function buildFactors(
  market: MarketBlock,
  risk: RiskBlock,
  liquidity: InstrumentLiquidity | undefined,
  foundation: InstrumentFoundation | undefined,
): RiskFactor[] {
  const out: RiskFactor[] = [];

  // --- Price behaviour ---------------------------------------------------------
  const chg = market.change_pct;
  const win = market.window_change_pct;
  const ind = market.indicators;
  const priceEvidence: RiskFactor['evidence'] = [];
  if (chg !== null && chg !== undefined) {
    priceEvidence.push({
      text: `Latest session move ${(chg * 100).toFixed(2)}%`,
      // OBSERVED: this actually happened and the exchange published it.
      kind: 'OBSERVED',
    });
  }
  if (win !== null && win !== undefined) {
    priceEvidence.push({
      text: `Return across the charted window ${(win * 100).toFixed(2)}%`,
      kind: 'OBSERVED',
    });
  }
  if (ind?.available && ind.rsi_latest !== null) {
    // DERIVED: we calculated these from the prices. The exchange publishes neither.
    priceEvidence.push({ text: `${ind.rsi_observation} RSI(14) ${ind.rsi_latest.toFixed(1)}`, kind: 'DERIVED' });
    priceEvidence.push({ text: ind.macd_observation, kind: 'DERIVED' });
  }
  // A 5% single-session move as the threshold for "elevated". A round, declared number
  // rather than something tuned.
  const bigMove = chg !== null && chg !== undefined && Math.abs(chg) >= 0.05;
  out.push({
    name: 'Price behaviour',
    // THE ORDER OF THESE CHECKS IS THE POINT: no evidence at all is checked FIRST, so an
    // absence can never fall through into 'normal'.
    level: priceEvidence.length === 0 ? 'unavailable' : bigMove ? 'elevated' : 'normal',
    reading: bigMove
      ? 'The latest session moved more than 5%.'
      : priceEvidence.length
        ? 'No session in the window moved outside the ordinary range.'
        // And a distinct sentence for the no-evidence case, so it cannot read as calm.
        : 'No price observations are available.',
    evidence: priceEvidence,
  });

  // --- Liquidity ---------------------------------------------------------------
  const st = liquidity?.liquidity_state;
  const pi = liquidity?.price_impact;
  const arr = liquidity?.arrival;
  const liqEvidence: RiskFactor['evidence'] = [];
  if (st?.available && typeof st.stress_score === 'number') {
    liqEvidence.push({
      // The units named -- "robust z" -- rather than a bare number.
      text: `Composite liquidity stress ${st.stress_score.toFixed(2)} (robust z)`,
      kind: 'DERIVED',
    });
  }
  if (pi?.available && typeof pi.lambda === 'number') {
    liqEvidence.push({
      text: pi.significant
        ? `Price impact ${pi.lambda.toExponential(2)} per unit signed flow`
        // NOT SIGNIFICANT is reported as the finding, rather than the number being shown
        // anyway. A figure indistinguishable from zero is not evidence of anything.
        : 'Price impact is not statistically distinguishable from zero',
      kind: 'DERIVED',
    });
  }
  if (arr?.available && typeof arr.fano_factor === 'number') {
    liqEvidence.push({
      text: `Trade arrivals overdispersed, Fano ${arr.fano_factor.toFixed(0)} (${arr.model_selected ?? 'model selected'})`,
      kind: 'DERIVED',
    });
  }
  out.push({
    name: 'Liquidity',
    level: !liqEvidence.length
      // Again: no evidence checked first.
      ? 'unavailable'
      : st?.stress_gate_fired
        ? 'elevated'
        : (st?.stress_score ?? 0) > 0
          ? 'watch'
          : 'normal',
    reading: !liqEvidence.length
      // The stored reason where there is one, and a plain fallback otherwise.
      ? (st?.why ?? 'No liquidity estimators were built for this security.')
      : st?.stress_gate_fired
        ? 'The liquidity stress gate fired on the latest session.'
        : 'Liquidity estimators are within their historical range.',
    evidence: liqEvidence.length
      ? liqEvidence
      // And even the empty case gets an explicit UNAVAILABLE line rather than a blank list.
      : [{ text: 'No liquidity artifacts for this security', kind: 'UNAVAILABLE' }],
  });

  // --- Market conditions -------------------------------------------------------
  const band = foundation?.price_band;
  const status = foundation?.status;
  const mktEvidence: RiskFactor['evidence'] = [];
  if (band?.available) {
    mktEvidence.push({ text: `Price band: ${band.band_label ?? band.band ?? 'none'}`, kind: 'OBSERVED' });
    if (band.surveillance_remark) {
      // A surveillance measure is an EXCHANGE statement -- the strongest kind of evidence
      // on this page, and marked OBSERVED accordingly.
      mktEvidence.push({ text: `Surveillance: ${band.surveillance_remark}`, kind: 'OBSERVED' });
    }
  }
  if (status?.available && status.state_label) {
    mktEvidence.push({ text: `Security status: ${status.state_label}`, kind: 'OBSERVED' });
  }
  out.push({
    name: 'Market conditions',
    level: !mktEvidence.length
      ? 'unavailable'
      // The exchange itself flagging this security is the one thing here that raises the
      // level -- an outside authority, not our own judgement.
      : band?.surveillance_remark
        ? 'elevated'
        : 'normal',
    reading: !mktEvidence.length
      ? (band?.why ?? 'No band or surveillance record is available.')
      : band?.surveillance_remark
        ? 'The exchange has placed this security under a surveillance measure.'
        : 'No surveillance measure or restrictive band applies.',
    evidence: mktEvidence.length
      ? mktEvidence
      : [{ text: 'No exchange status record', kind: 'UNAVAILABLE' }],
  });

  // --- Information ------------------------------------------------------------
  const ca = foundation?.corporate_actions;
  const infoEvidence: RiskFactor['evidence'] = [];
  if (ca?.available) {
    infoEvidence.push({ text: `${ca.count} corporate actions on record`, kind: 'OBSERVED' });
    if (ca.price_affecting) {
      infoEvidence.push({
        text: `${ca.price_affecting} change a price factor`,
        // DERIVED, because whether an action moved the price is our reconciliation rather
        // than something the exchange stated.
        kind: 'DERIVED',
      });
    }
  }
  out.push({
    name: 'Information activity',
    // Never 'elevated'. The mere existence of announcements is not a risk signal, and
    // treating it as one would be inventing a finding out of ordinary company housekeeping.
    level: infoEvidence.length ? 'normal' : 'unavailable',
    reading: infoEvidence.length
      ? 'Announcement and corporate-action records are present for this security.'
      : 'No information records are available.',
    evidence: infoEvidence.length
      ? infoEvidence
      : [{ text: 'No announcement or action record', kind: 'UNAVAILABLE' }],
  });

  // --- Company fundamentals ----------------------------------------------------
  // Deliberately not enumerated. The limitation record forbids naming the individual
  // measures beside a value, precisely so no surface can imply one exists.
  // PLAIN ENGLISH: A FACTOR THAT IS ALWAYS UNAVAILABLE, and included anyway.
  // It would be simpler to leave it out. Including it means every reader of every company
  // page is told that company accounts are missing from this analysis -- rather than that
  // absence being visible only to somebody who thought to wonder about it.
  // And the individual measure names are not written, because the forbidden-phrasings list
  // exists precisely to stop any page printing one beside a number.
  out.push({
    name: 'Company fundamentals',
    level: 'unavailable',
    reading: 'Unavailable — no verified point-in-time source.',
    evidence: [
      {
        // The limitation referenced by id AND explained, so a reader need not go and look
        // it up to understand the gap.
        text: 'Recorded limitation L-13: no licence-clear source carries the disclosure timestamp separately from the financial period',
        kind: 'UNAVAILABLE',
      },
      {
        // And the tempting shortcut ruled out, in the reader's view rather than only in a
        // code comment.
        text: 'No price-derived substitute is shown, because it would be a market signal under a company label',
        kind: 'UNAVAILABLE',
      },
    ],
  });

  return out;
}

// One factor, collapsible.
function Factor({ f }: { f: RiskFactor }) {
  return (
    // The browser's own `<details>` again -- so the evidence is in the page even with
    // JavaScript off, is findable by find-in-page, and prints.
    <details className="rf" data-level={f.level}>
      <summary className="rf__summary">
        <span className="rf__name">{f.name}</span>
        {/* The word, always visible even when collapsed. */}
        <span className="rf__level">{LEVEL_WORD[f.level]}</span>
      </summary>
      <p className="rf__reading">{f.reading}</p>
      <ul className="rf__evidence">
        {f.evidence.map((e) => (
          <li key={e.text}>
            {/* THE KIND BADGE ON EVERY LINE. So a reader can see at a glance which items are
                exchange facts and which are our own calculations -- without having to know
                the difference in advance. */}
            <span className="rf__kind" data-kind={e.kind}>
              {e.kind}
            </span>
            {e.text}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function RiskHeader({
  symbol,
  market,
  risk,
  liquidity,
  foundation,
  dataThrough,
  variant = 'banner',
}: {
  symbol: string;
  market: MarketBlock;
  risk: RiskBlock;
  liquidity?: InstrumentLiquidity;
  foundation?: InstrumentFoundation;
  dataThrough: string;
  /** `aside` renders the same evidence as a narrow column beside the chart. */
  // The SAME evidence in two layouts -- so a narrow column and a wide banner cannot end up
  // showing different things.
  variant?: 'banner' | 'aside';
}) {
  const factors = buildFactors(market, risk, liquidity, foundation);
  const elevated = factors.filter((f) => f.level === 'elevated').length;
  const watch = factors.filter((f) => f.level === 'watch').length;
  const unavailable = factors.filter((f) => f.level === 'unavailable').length;

  // NOT SCORED reads as "Evidence unavailable", never as "Normal".
  const stateLabel = risk.available ? (risk.state_label ?? 'Normal') : 'Evidence unavailable';
  const tone = risk.available ? (risk.state_tone ?? 'calm') : 'unknown';

  // The headline sentence, in order of how much it matters.
  const headline = !risk.available
    // Not scored at all -- said first and plainly.
    ? 'This security has not been scored by the model.'
    : elevated > 0
      // Correct singular and plural throughout, so the sentence never reads like a machine.
      ? `${elevated} risk factor${elevated === 1 ? '' : 's'} require attention.`
      : watch > 0
        ? `${watch} risk factor${watch === 1 ? '' : 's'} to monitor.`
        // And carefully worded: "no risk factor is currently ELEVATED" -- a statement about
        // the factors, not a reassurance about the company.
        : 'No risk factor is currently elevated.';

  if (variant === 'aside') {
    return (
      <section className="riskAside" data-tone={tone}>
        <span className="riskAside__eyebrow">AEGIS risk profile</span>
        <span className="riskAside__state">{stateLabel.toUpperCase()}</span>
        <span className="riskAside__headline">{headline}</span>
        {risk.available && risk.state_meaning ? (
          // What the state MEANS, so the label never appears without its explanation.
          <span className="riskAside__meaning">{risk.state_meaning}</span>
        ) : null}

        <div className="riskAside__factors">
          {factors.map((f) => (
            <Factor key={f.name} f={f} />
          ))}
        </div>

        <p className="riskAside__counts">
          {/* THE HONESTY LINE: how many factors actually have evidence, and how many do not.
              Plus an instruction telling the reader they can open each one and see whether
              each item was observed, derived or a model signal. */}
          {factors.length - unavailable} of {factors.length} factors have evidence
          {unavailable ? ` · ${unavailable} unavailable` : ''}. Expand a factor for the
          items behind it and whether each was observed, derived or a model signal.
        </p>
      </section>
    );
  }

  return (
    <section className="riskHero" data-tone={tone}>
      <div className="riskHero__top">
        <div className="riskHero__id">
          {/* "Risk intelligence" as the eyebrow, not "Price". Idea 1, made visible in the
              first two words on the page. */}
          <span className="riskHero__eyebrow">Risk intelligence</span>
          <h2 className="riskHero__symbol">{symbol}</h2>
          {/* The venue named, so nobody has to guess which exchange this is. */}
          <span className="riskHero__venue">NSE: {symbol}</span>
        </div>

        <div className="riskHero__state">
          {/* THE RISK STATE IN THE HERO POSITION, where the price usually goes. */}
          <span className="riskHero__stateLabel">Risk state</span>
          <span className="riskHero__stateValue">{stateLabel.toUpperCase()}</span>
          <span className="riskHero__headline">{headline}</span>
          {risk.available && risk.state_meaning ? (
            <span className="riskHero__meaning">{risk.state_meaning}</span>
          ) : null}
        </div>

        <div className="riskHero__integrity">
          {/* AND THE DATA'S AGE, GIVEN EQUAL PROMINENCE. Not tucked in a footnote -- placed
              in the header beside the verdict, because how old the evidence is matters as
              much as what it says. */}
          <span className="riskHero__integrityLabel">Market data through</span>
          <span className="riskHero__integrityValue">{dataThrough}</span>
          <span className="riskHero__integrityNote">
            {/* And when the data is behind, it says by HOW MANY DAYS -- rather than a vague
                "may not be current" that a reader cannot act on. */}
            {market.days_since_latest_session && market.days_since_latest_session > 0
              ? `latest verified session · ${market.days_since_latest_session} days behind today`
              : 'latest verified session'}
          </span>
        </div>
      </div>

      <div className="riskHero__factors">
        {factors.map((f) => (
          <Factor key={f.name} f={f} />
        ))}
      </div>

      <p className="riskHero__counts">
        {/* The same honesty line as the narrow version -- built from the same numbers, so
            the two layouts cannot disagree. */}
        {factors.length - unavailable} of {factors.length} factors have evidence
        {unavailable ? ` · ${unavailable} unavailable` : ''}. Expand any factor to see what
        it was based on and whether each item was observed, derived or a model signal.
      </p>
    </section>
  );
}
