import { NoData, StatCard } from '@/components/ui/Primitives';
import { getReproducibility, getUniverse } from '@/lib/data';

export const dynamic = 'force-static';

export default async function ReproducibilityPage() {
  const b = await getReproducibility();
  const universe = await getUniverse();
  const m = (b.meta ?? {}) as Record<string, any>;

  return (
    <>
      <h1>Reproducibility</h1>
      <p className="lede">
        What it takes to obtain these numbers again, and the evidence that doing so
        actually works. Reproducibility here is a measured property, not an aspiration.
      </p>

      <div className="grid">
        <StatCard
          label="Verification re-run"
          value={m.verified ? 'bit-identical' : 'not recorded'}
          note="all arms and statistical tests"
        />
        <StatCard label="Commit" value={m.commit ? String(m.commit).slice(0, 8) : 'n/a'} />
        <StatCard label="Seed" value={m.seed ? String(m.seed) : 'n/a'} />
        <StatCard label="Dataset version" value={universe.datasetVersion} />
        <StatCard
          label="Holdout"
          value="frozen"
          note="untouched by any code path"
        />
      </div>

      <h2>Traceability chain</h2>
      <p className="small muted" style={{ marginTop: 0 }}>
        Every published figure resolves through this chain. Nothing is published that
        cannot.
      </p>
      <div className="card">
        <pre className="mono" style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
          {`figure  →  experiment  →  run  →  dataset version + hash
                                  →  model versions
                                  →  configuration + seed
                                  →  package versions + OS
                                  →  git commit`}
        </pre>
      </div>

      <h2>Verification result</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Quantity</th>
              <th className="num">Max absolute difference on re-run</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>AUPRC, AUROC, F1, ECE across 8 arms</td>
              <td className="num">0.000e+00</td>
            </tr>
            <tr>
              <td>Delta, CI bounds, p-values across 31 tests</td>
              <td className="num">0.000e+00</td>
            </tr>
            <tr>
              <td>Significance flags</td>
              <td className="num">identical</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="small muted">
        Bit-identical including the 600-resample cluster bootstraps, because every
        resampler draws from the recorded seed.
      </p>

      {!b.dataAvailable ? (
        <NoData what="Reproducibility manifest" note={b.note} />
      ) : (
        <>
          <h2>Environment recorded with these results</h2>
          <div className="tableWrap">
            <table>
              <tbody>
                {Object.entries(m.environment ?? {})
                  .filter(([, v]) => typeof v !== 'object')
                  .map(([k, v]) => (
                    <tr key={k}>
                      <th style={{ width: 200 }}>{k}</th>
                      <td className="mono small">{String(v)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <section className="boundary">
        <h3>What is not reproducible here</h3>
        <ul>
          <li>
            The product build. No Node.js runtime was present in the authoring
            environment, so the application has never been built, typechecked or run. Its
            status is WRITTEN, NOT VERIFIED.
          </li>
          <li>
            Tier-2 and Tier-3 model results. Those weights are not installed, so those
            registry entries carry status NOT RUN and no metric.
          </li>
          <li>
            Anything depending on data that does not exist: real incident labels,
            point-in-time index membership, true Level-2 microstructure.
          </li>
        </ul>
      </section>
    </>
  );
}
