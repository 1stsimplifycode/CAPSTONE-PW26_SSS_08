import type { InstrumentLiquidity } from '@/lib/product';

/**
 * The Week 2 liquidity estimators, as the instrument page shows them.
 *
 * Two rules, both because the alternative misleads:
 *
 * 1. Every estimate is shown with its uncertainty. A price-impact coefficient without its
 *    standard error invites a comparison between two securities that the data may not
 *    support, and the interval is what stops that.
 * 2. An estimator that could not be computed is rendered as "not available" with the
 *    reason. Silently omitting it reads as "nothing unusual here", which is a claim.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * HOW EASY IS THIS SHARE TO TRADE? Four measurements, on screen.
 *
 * RULE 1: EVERY NUMBER WEARS ITS UNCERTAINTY.
 * The docstring gives a precise example of the harm. Company A has a price-impact figure of
 * 0.0012 and company B has 0.0015. Is B harder to trade? Without the margins of error you
 * cannot possibly say -- and a reader looking at two bare numbers will conclude that it is.
 * If both figures are ± 0.0008, the difference means nothing whatever.
 * So every estimate is shown with its uncertainty, and the comparison the reader would
 * otherwise make wrongly becomes one they can make properly.
 *
 * RULE 2: AN UNCOMPUTED MEASUREMENT IS SHOWN AS ABSENT.
 * Same as everywhere else in this project, and the docstring's phrasing is precise:
 * omitting it "reads as 'nothing unusual here', which is a claim."
 * Leaving something out is not neutral. The reader fills the silence, and they fill it
 * with reassurance.
 */

// Format a number that might be extremely large or extremely small.
function Sci({ value, digits = 2 }: { value: number; digits?: number }) {
  if (!Number.isFinite(value)) return <>—</>;
  // How many digits before or after the decimal point this number needs.
  const exp = Math.floor(Math.log10(Math.abs(value)));
  // Very small or very large: use scientific notation, so 0.0000034 becomes 3.4×10⁻⁶
  // rather than a row of zeros nobody can count.
  if (exp <= -4 || exp >= 5) {
    const mant = value / 10 ** exp;
    return (
      <>
        {/* `<sup>` makes the exponent a proper raised power, so it reads as mathematics
            rather than as "10-6". */}
        {mant.toFixed(digits)}×10<sup>{exp}</sup>
      </>
    );
  }
  // Otherwise ordinary notation -- but with the number of decimal places ADJUSTED to the
  // size of the number, so a small value keeps its meaningful digits instead of rounding
  // away to 0.00.
  return <>{value.toFixed(Math.max(0, digits - exp))}</>;
}

// The tile for something that could not be computed.
function Unavailable({ what, why }: { what: string; why?: string }) {
  return (
    <article className="tile tile--muted">
      <span className="tile__label">{what}</span>
      <span className="tile__value">Not available</span>
      <span className="tile__note">{why}</span>
    </article>
  );
}

export function Liquidity({ liquidity }: { liquidity?: InstrumentLiquidity }) {
  if (!liquidity) return null;
  const { realised_variance: rv, price_impact: pi, arrival, liquidity_state: state } =
    liquidity;

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        {/* A plain-English heading, and a subtitle that promises the uncertainty. */}
        <h2>How liquid this security is</h2>
        <span className="home__asof">Week 2 estimators, each with its uncertainty</span>
      </div>

      <div className="cardRow">
        {rv.available ? (
          <article className="tile">
            <span className="tile__label">Realised volatility</span>
            <span className="tile__value">
              {/* The `!` tells the type checker this is definitely present -- which it is,
                  because `available` is true. */}
              {(rv.annualised_volatility! * 100).toFixed(1)}%
            </span>
            <span className="tile__note">
              {/* THE NOTE CARRIES THE METHOD AND THE PRECISION: how many observations, how
                  often sampled, and the relative error. Enough for a reader to judge how
                  much weight the headline figure deserves. */}
              Annualised, from {rv.n_returns} intraday returns sampled every{' '}
              {rv.sampling_minutes} min · ±
              {(rv.relative_standard_error! * 100).toFixed(0)}% relative
            </span>
          </article>
        ) : (
          <Unavailable what="Realised volatility" why={rv.why} />
        )}

        {pi.available ? (
          <article className="tile">
            {/* The Greek letter is used because that is what the research calls it, and a
                reader following the method across the two will recognise it. */}
            <span className="tile__label">Price impact (λ)</span>
            <span className="tile__value">
              <Sci value={pi.lambda!} />
            </span>
            <span className="tile__note">
              {/* THE FULL STATISTICAL PICTURE: the margin of error, the test statistic, an
                  explicit "significant" or "not significant" IN WORDS, and the sample size.
                  Saying it in words matters -- not every reader knows what a t of 1.2
                  implies, and none of them should have to. */}
              ±<Sci value={pi.standard_error!} /> (t={pi.t_stat!.toFixed(1)},{' '}
              {pi.significant ? 'significant' : 'not significant'}) · n={pi.n_obs}
            </span>
          </article>
        ) : (
          <Unavailable what="Price impact" why={pi.why} />
        )}

        {arrival.available ? (
          <article className="tile">
            <span className="tile__label">Trade arrivals</span>
            <span className="tile__value">
              {Math.round(arrival.mean_daily_trades!).toLocaleString()}/day
            </span>
            <span className="tile__note">
              {/* The burstiness expressed as a MULTIPLE of the textbook assumption --
                  "340× Poisson" makes the scale of the departure immediately vivid. */}
              Dispersion {arrival.fano_factor!.toFixed(0)}× Poisson ·{' '}
              {/* And the verdict in plain words rather than the model's name. */}
              {arrival.model_selected === 'negative_binomial'
                ? 'arrivals cluster'
                : 'Poisson is adequate'}
            </span>
          </article>
        ) : (
          <Unavailable what="Trade arrivals" why={arrival.why} />
        )}

        {state.available ? (
          // The tile is styled differently when the alarm has fired, so a stressed security
          // is visible at a glance.
          <article className={`tile ${state.stress_gate_fired ? 'tile--alert' : ''}`}>
            <span className="tile__label">Liquidity state</span>
            <span className="tile__value">
              {/* "Stressed" or "Ordinary" -- plain words, not a score the reader must
                  interpret. */}
              {state.stress_gate_fired ? 'Stressed' : 'Ordinary'}
            </span>
            <span className="tile__note">
              {/* The score, AND how many sessions out of how many were stressed -- context
                  that tells you whether this is a one-off or a persistent condition. */}
              Stress score {state.stress_score!.toFixed(2)} · {state.sessions_stressed} of{' '}
              {state.sessions} sessions stressed
            </span>
          </article>
        ) : (
          <Unavailable what="Liquidity state" why={state.why} />
        )}
      </div>

      {state.available && state.stress_gate_fired && state.attribution ? (
        <div className="tableWrap">
          <table className="dataTable">
            {/* THE CAPTION IS THE IMPORTANT PART. It says the share was "computed from the
                state vector rather than chosen as an explanation."
                That is the honest-attribution promise from the research layer, restated for
                a reader: nobody selected this explanation because it sounded plausible. It
                is arithmetic on the same numbers that produced the alarm. */}
            <caption>
              What drove the stress on {state.latest_session}. Each share is the
              component&rsquo;s own robust z-score as a fraction of the total, computed from
              the state vector rather than chosen as an explanation.
            </caption>
            <thead>
              <tr>
                <th scope="col">Estimator</th>
                <th scope="col">Value</th>
                <th scope="col">Robust z</th>
                <th scope="col">Share of stress</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(state.attribution)
                // Biggest contributor first -- the one a reader most wants to see.
                .sort((a, b) => b[1] - a[1])
                .map(([key, share]) => {
                  const c = state.components?.[key];
                  return (
                    <tr key={key}>
                      {/* The friendly name, falling back to the internal one rather than a
                          blank if no label was supplied. */}
                      <td>{c?.label ?? key}</td>
                      {/* THE RAW VALUE and THE STANDARDISED SCORE, side by side. The raw
                          number is the real measurement; the z-score is how unusual it was.
                          A reader needs both -- one to check, one to judge. */}
                      <td>{c?.value != null ? <Sci value={c.value} /> : '—'}</td>
                      <td>{c?.robust_z != null ? c.robust_z.toFixed(2) : '—'}</td>
                      <td>{(share * 100).toFixed(0)}%</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      ) : null}

      {pi.available ? (
        <p className="instrument__note">
          {/* AN OUTSTANDING PIECE OF HONESTY, printed right beside the number it qualifies.
              It admits three things in two sentences:
                1. The exchange does not publish whether each trade was a buy or a sell.
                2. So we GUESS it, with a known method that is known to get some wrong.
                3. Those mistakes push the figure TOWARDS ZERO -- so our estimate is
                   conservative, understating rather than overstating the impact.
              And the final clause draws the line that the whole reference layer is built
              around: this is our inference, and it is "not an exchange statement". */}
          Trade direction is not published by NSE. The signs behind λ are inferred by the
          tick test, which misclassifies some bars and pulls the coefficient toward zero
          &mdash; so this is a conservative estimate, and it is not an exchange statement
          about order flow.
        </p>
      ) : null}
    </section>
  );
}
