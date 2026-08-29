/**
 * The risk-dimension strip and the evidence balance beneath it.
 *
 * Both are assembled from blocks the payload already carries — the scored risk state,
 * the Week 2 liquidity estimators, the Week 1 foundation. Nothing is computed here and no
 * dimension is invented: a dimension whose inputs are missing renders as INSUFFICIENT
 * EVIDENCE, which is a different statement from "low risk" and is kept visibly different.
 *
 * **Colour is a state, not an instruction.** Amber means an indicator is mixed or worth
 * monitoring; red means one is deteriorating; grey means there is not enough to say. None
 * of them means anything about what a reader should do, and every one is accompanied by
 * the word for the state so the page is readable without relying on colour at all.
 *
 * **The balance section is not a verdict.** It lists what the evidence supports on one
 * side, what it counts against on the other, and what remains unresolved — then stops.
 * There is deliberately no aggregate score: a single headline number invites being read
 * as a verdict whatever it is labelled, which is the reading this project refuses.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * FIVE DIMENSIONS OF RISK, LAID OUT SIDE BY SIDE -- AND DELIBERATELY NOT ADDED UP.
 *
 * IDEA 1: "INSUFFICIENT EVIDENCE" IS NOT "LOW RISK".
 * If we could not measure something, the strip says INSUFFICIENT EVIDENCE in grey. It does
 * not say "low" and it does not leave a gap. Because "we do not know" and "it is fine" are
 * completely different, and only one of them is reassuring -- yet a blank space or a green
 * tick would deliver the reassuring reading.
 *
 * IDEA 2: COLOUR SAYS WHAT THINGS ARE, NOT WHAT TO DO.
 * Red means an indicator is deteriorating. It does not mean sell. Nothing on this page means
 * sell. And every colour has its word written beside it, so a reader who cannot see colour
 * -- or who prints the page -- loses nothing at all.
 *
 * IDEA 3, AND IT IS THE BOLDEST DECISION IN THE PROJECT: THERE IS NO OVERALL SCORE.
 *
 * It would be trivial to average the five dimensions into one number. Every product
 * instinct says do it -- it is the number people want, it fits on a card, it is what gets
 * shared.
 * And the docstring gives the reason not to:
 *
 *     "a single headline number invites being read as a verdict whatever it is labelled."
 *
 * You can call it "informational". You can caveat it. It will still be read as the answer,
 * and it will be the only thing anybody remembers.
 * So the page lists what supports, what counts against, and what is unknown -- and then
 * STOPS. The final sentence says so plainly: "the reader weighs them."
 * That is a genuinely uncomfortable product decision, taken for the right reason.
 */
import type { InstrumentLiquidity, MarketBlock, RiskBlock } from '@/lib/product';

// Four states -- and note the fourth is an honest "we cannot say" rather than a middle
// value, which would be a claim.
type State = 'improving' | 'monitor' | 'deteriorating' | 'unknown';

// THE WORDS. Every colour has one, so the page never depends on colour alone.
const STATE_WORD: Record<State, string> = {
  improving: 'IMPROVING',
  monitor: 'MONITOR',
  deteriorating: 'DETERIORATING',
  // Not "LOW" and not "NONE" -- the honest phrase.
  unknown: 'INSUFFICIENT EVIDENCE',
};

interface Dimension {
  name: string;
  state: State;
  // A sentence saying what was observed.
  reading: string;
  // And the specific evidence behind it, so the reading can be checked.
  evidence: string[];
  asOf?: string | null;
}

// One dimension, as a row.
function Row({ d }: { d: Dimension }) {
  return (
    <article className="riskDim" data-state={d.state}>
      <div className="riskDim__head">
        <span className="riskDim__name">{d.name}</span>
        {/* THE WORD, always present alongside the colour. */}
        <span className="riskDim__state">{STATE_WORD[d.state]}</span>
      </div>
      <p className="riskDim__reading">{d.reading}</p>
      {d.evidence.length ? (
        <ul className="riskDim__evidence">
          {d.evidence.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
      {/* WHEN this reading is from -- because a dimension measured last week and one
          measured today should not sit side by side unlabelled. */}
      {d.asOf ? <span className="riskDim__asOf">as of {d.asOf}</span> : null}
    </article>
  );
}

// Build the five dimensions from whatever the payload actually carries.
function buildDimensions(
  market: MarketBlock,
  risk: RiskBlock,
  liquidity: InstrumentLiquidity | undefined,
): Dimension[] {
  const out: Dimension[] = [];

  // Market/evidence state — the scored panel, when one exists for this symbol.
  if (risk.available && risk.state_label) {
    const tone = risk.state_tone;
    out.push({
      name: 'Evidence state',
      state: tone === 'calm' ? 'improving' : tone === 'high' ? 'deteriorating' : 'monitor',
      reading: risk.state_meaning ?? risk.state_label,
      evidence: [
        // The evidence lines are built conditionally and then filtered, so a missing figure
        // simply produces one fewer line rather than an empty bullet point.
        risk.sessions_scored ? `${risk.sessions_scored} sessions scored` : '',
        // THE UNCERTAINTY AND THE COVERAGE, listed as evidence. So the confidence in the
        // reading sits beside the reading itself.
        risk.uncertainty !== undefined
          ? `model uncertainty ${risk.uncertainty.toFixed(2)}`
          : '',
        risk.coverage !== undefined && risk.coverage !== null
          ? `evidence coverage ${(risk.coverage * 100).toFixed(0)}%`
          : '',
      ].filter(Boolean),
      asOf: risk.scored_to ?? null,
    });
  } else {
    // NOT SCORED. The row still appears, marked unknown, with the reason.
    out.push({
      name: 'Evidence state',
      state: 'unknown',
      reading: risk.why ?? 'This security has not been scored.',
      evidence: [],
    });
  }

  // Liquidity — Week 2 estimators, each rendered only when the artifact carries it.
  const state = liquidity?.liquidity_state;
  if (state?.available && typeof state.stress_score === 'number') {
    const s = state.stress_score;
    out.push({
      name: 'Liquidity',
      state: state.stress_gate_fired ? 'deteriorating' : s > 0 ? 'monitor' : 'improving',
      reading:
        state.stress_gate_fired === true
          ? 'The liquidity stress gate fired on the latest session.'
          // The units are NAMED -- "in robust-z units" -- rather than leaving a bare number
          // whose scale a reader would have to guess at.
          : `Composite liquidity stress is ${s.toFixed(2)} in robust-z units.`,
      evidence: [
        state.sessions ? `${state.sessions} sessions in the state vector` : '',
        state.sessions_stressed !== undefined
          ? `${state.sessions_stressed} stressed sessions`
          : '',
        // WHICH measurement caused it -- the honest attribution, surfaced here too.
        state.primary_driver ? `primary driver ${state.primary_driver}` : '',
      ].filter(Boolean),
      asOf: state.latest_session ?? null,
    });
  } else {
    out.push({
      name: 'Liquidity',
      state: 'unknown',
      reading: state?.why ?? 'No liquidity state vector was built for this security.',
      evidence: [],
    });
  }

  // Volatility — realised variance, when estimated.
  const rv = liquidity?.realised_variance;
  if (rv?.available && typeof rv.annualised_volatility === 'number') {
    out.push({
      name: 'Volatility',
      // Always 'monitor', never 'deteriorating'. High volatility is not in itself bad news
      // -- it is a fact worth watching. Colouring it red would be an opinion.
      state: 'monitor',
      reading: `Realised volatility is ${(rv.annualised_volatility * 100).toFixed(1)}% annualised.`,
      evidence: [
        rv.sampling_minutes ? `sampled at ${rv.sampling_minutes} minutes` : '',
        rv.n_returns ? `${rv.n_returns} returns` : '',
        // The precision, as evidence.
        rv.relative_standard_error !== undefined
          ? `relative standard error ${(rv.relative_standard_error * 100).toFixed(1)}%`
          : '',
      ].filter(Boolean),
    });
  } else {
    out.push({
      name: 'Volatility',
      state: 'unknown',
      reading: rv?.why ?? 'Realised variance was not estimated for this security.',
      evidence: [],
    });
  }

  // Price impact — Kyle's lambda, only when the fit is significant enough to quote.
  const pi = liquidity?.price_impact;
  if (pi?.available && typeof pi.lambda === 'number') {
    out.push({
      name: 'Price impact',
      // AND HERE IS A PARTICULARLY GOOD DECISION: if the estimate is not statistically
      // distinguishable from zero, the dimension is marked UNKNOWN rather than reported.
      // A number that could just as easily be zero is not a finding, and showing it would
      // invite a reader to compare two figures that neither support.
      state: pi.significant ? 'monitor' : 'unknown',
      reading: pi.significant
        ? `Price moves ${pi.lambda.toExponential(2)} per unit of signed flow.`
        // And when it is not significant, that is stated as the finding.
        : 'The price-impact fit is not statistically distinguishable from zero.',
      evidence: [
        pi.n_obs ? `${pi.n_obs} observations` : '',
        pi.t_stat !== undefined ? `t = ${pi.t_stat.toFixed(2)}` : '',
        pi.r_squared !== undefined ? `R² = ${pi.r_squared.toFixed(3)}` : '',
      ].filter(Boolean),
    });
  } else {
    out.push({
      name: 'Price impact',
      state: 'unknown',
      reading: pi?.why ?? 'Price impact was not estimated for this security.',
      evidence: [],
    });
  }

  // Momentum — derived indicator, labelled as derived.
  const ind = market.indicators;
  if (ind?.available && ind.rsi_latest !== null) {
    out.push({
      name: 'Technical momentum',
      state: 'monitor',
      reading: `${ind.rsi_observation} RSI(14) is ${ind.rsi_latest.toFixed(1)}.`,
      // AND THE LABEL SAYING WHERE IT CAME FROM, listed as evidence: "derived from closing
      // prices, not exchange-published". So a technical indicator is never mistaken for an
      // official figure -- the same distinction the reference layer enforces, carried here.
      evidence: [ind.macd_observation, 'derived from closing prices, not exchange-published'],
      asOf: market.latest_session ?? market.last_session,
    });
  } else {
    out.push({
      name: 'Technical momentum',
      state: 'unknown',
      reading: ind?.why_unavailable ?? 'Indicators are not available from this source.',
      evidence: [],
    });
  }

  return out;
}

export function RiskProfile({
  market,
  risk,
  liquidity,
}: {
  market: MarketBlock;
  risk: RiskBlock;
  liquidity?: InstrumentLiquidity;
}) {
  const dims = buildDimensions(market, risk, liquidity);
  const known = dims.filter((d) => d.state !== 'unknown');
  const deteriorating = dims.filter((d) => d.state === 'deteriorating');
  const improving = dims.filter((d) => d.state === 'improving');
  const unresolved = dims.filter((d) => d.state === 'unknown');

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>Risk profile</h2>
        <span className="home__asof">
          {/* THE HONESTY HEADLINE: how many of the five dimensions actually have evidence.
              "2 of 5" tells a reader immediately how much of this page rests on anything. */}
          {known.length} of {dims.length} dimensions have evidence
        </span>
      </div>

      <p className="riskProfile__legend">
        {/* The colour rule stated ON THE PAGE, not just in the code. A reader is told what
            the colours mean and, just as importantly, what they do not mean. */}
        Colour describes the state of the evidence, not an action. Every state is written
        out in words so the page reads the same without colour.
      </p>

      <div className="riskProfile__grid">
        {dims.map((d) => (
          <Row key={d.name} d={d} />
        ))}
      </div>

      <div className="evidenceBalance">
        <h3 className="evidenceBalance__title">Evidence balance</h3>
        <div className="evidenceBalance__cols">
          {/* THREE COLUMNS, GIVEN EQUAL WEIGHT: what supports, what counts against, and
              what is unknown. The third column is the unusual one -- most products would
              simply omit it, and omitting it would make the picture look more complete
              than it is. */}
          <div>
            <span className="evidenceBalance__head">Supporting evidence</span>
            {improving.length ? (
              <ul>
                {improving.map((d) => (
                  <li key={d.name}>
                    <strong>{d.name}</strong> — {d.reading}
                  </li>
                ))}
              </ul>
            ) : (
              // Even the empty case is stated plainly rather than left blank.
              <p className="small muted">No dimension is currently improving.</p>
            )}
          </div>
          <div>
            <span className="evidenceBalance__head">Risk evidence</span>
            {deteriorating.length ? (
              <ul>
                {deteriorating.map((d) => (
                  <li key={d.name}>
                    <strong>{d.name}</strong> — {d.reading}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted">No dimension is currently deteriorating.</p>
            )}
          </div>
          <div>
            <span className="evidenceBalance__head">Unresolved</span>
            {unresolved.length ? (
              <ul>
                {unresolved.map((d) => (
                  <li key={d.name}>
                    <strong>{d.name}</strong> — {d.reading}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted">Every dimension has evidence.</p>
            )}
          </div>
        </div>
        <p className="evidenceBalance__note">
          {/* TWO CLOSING ADMISSIONS.
              First, that company accounts are missing from EVERY dimension above -- a
              significant gap, stated at the foot of the page rather than left for a reader
              to notice.
              Second, and most important, the refusal itself: no aggregate score is produced.
              "The reader weighs them." Four words that hand the judgement back to the
              person, which is exactly where a system that does not give advice must leave it. */}
          Company fundamentals are absent from every dimension above; see the financial
          health section for why. No aggregate score is produced from these dimensions —
          the reader weighs them.
        </p>
      </div>
    </section>
  );
}
