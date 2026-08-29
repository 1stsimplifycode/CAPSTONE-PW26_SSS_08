import { LimeStabilitySection } from '@/components/research/AngleSections';
import { NoData } from '@/components/ui/Primitives';
import { getFigures, getResearchAngles } from '@/lib/data';

export const dynamic = 'force-static';

const METHODS: [string, string, string][] = [
  ['Permutation importance', 'global', 'valid on the tree-based risk model'],
  ['Occlusion / feature ablation', 'local + block', 'valid on any model'],
  [
    'KernelSHAP',
    'local',
    'model-agnostic; the calibrated ensemble does not expose tree structure',
  ],
  ['LIME (local ridge surrogate)', 'local', 'perturbations drawn from background marginals'],
  [
    'Counterfactual search',
    'local',
    'smallest feature set whose change resolves the score',
  ],
  [
    'Integrated gradients',
    'combination layer only',
    'the combination rule is differentiable; the trees are not',
  ],
  ['PDP / ICE / ALE', 'global dependence', 'ALE preferred where features are correlated'],
];

const NOT_APPLICABLE: [string, string][] = [
  ['DeepSHAP', 'requires a differentiable deep network'],
  ['Grad-CAM / Guided Grad-CAM', 'requires convolutional feature maps'],
  ['DeepLIFT', 'requires a differentiable deep network'],
  ['TCAV', 'requires concept activation vectors in a differentiable network'],
  [
    'TreeSHAP',
    'the learners are wrapped in a probability calibrator, so tree structure is not exposed; KernelSHAP is used instead and the substitution is reported',
  ],
];

const FAITHFULNESS: [string, string, string, string, string][] = [
  ['Occlusion', '0.0298', '0.9286', '0.9942', '0.46'],
  ['KernelSHAP', '0.0290', '0.9279', '0.9909', '1.00'],
  ['LIME', '0.0371', '0.9256', '0.9891', '0.02'],
  ['Counterfactual', '0.0588', '0.9247', '0.9828', '0.43'],
];

export default async function XaiPage() {
  const figures = await getFigures();
  const b = await getResearchAngles();
  const angles = (b.meta?.results ?? {}) as Record<string, any>;

  const xaiFigures = figures.rows.filter((f) =>
    /local|importance|agreement|faithful|attribution|saliency|lime/i.test(f.figureId),
  );

  return (
    <>
      <h1>XAI lab</h1>
      <p className="lede">
        Which evidence drove an assessment, how faithful that explanation is, and whether
        it survives adversarial checks. An explanation that fails a sanity check is not
        presented as trustworthy, however plausible it looks.
      </p>

      <h2>Sanity checks</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Check</th>
              <th className="num">Statistic</th>
              <th className="num">Threshold</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Attribution sparsity (top-10 mass)</td>
              <td className="num">0.998</td>
              <td className="num">0.25</td>
              <td>
                <span className="chip chip--good">pass</span>
              </td>
            </tr>
            <tr>
              <td>Model randomisation (Spearman against a label-shuffled refit)</td>
              <td className="num">0.013</td>
              <td className="num">&lt; 0.50</td>
              <td>
                <span className="chip chip--good">pass</span>
              </td>
            </tr>
            <tr>
              <td>LIME sign consistency across seeds, 800 perturbations</td>
              <td className="num">0.780</td>
              <td className="num">0.80</td>
              <td>
                <span className="chip chip--bad">fail</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="small muted">
        The threshold was declared before the run and was not lowered to make the check
        pass. No claim in this project rests on a LIME attribution.
      </p>

      <LimeStabilitySection angles={angles} />

      <h2>Faithfulness</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th className="num">Deletion AUC</th>
              <th className="num">Insertion AUC</th>
              <th className="num">Comprehensiveness</th>
              <th className="num">Seconds</th>
            </tr>
          </thead>
          <tbody>
            {FAITHFULNESS.map(([m, d, i, c, s]) => (
              <tr key={m}>
                <td>{m}</td>
                <td className="num">{d}</td>
                <td className="num">{i}</td>
                <td className="num">{c}</td>
                <td className="num">{s}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        Lower deletion AUC and higher insertion AUC are better. Pairwise rank agreement:
        occlusion and KernelSHAP correlate at 0.472; LIME correlates with occlusion at
        -0.042. Agreement is descriptive — two methods can share a bias, so agreement is
        not corroboration and disagreement is not proof of error.
      </p>

      <h2>Methods in use</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Scope</th>
              <th>Applicability</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {METHODS.map(([m, s, a]) => (
              <tr key={m}>
                <td>{m}</td>
                <td>{s}</td>
                <td className="muted small">{a}</td>
                <td>
                  <span className="chip chip--good">RUN</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Declared but not applicable to this model class</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Why it is not run</th>
            </tr>
          </thead>
          <tbody>
            {NOT_APPLICABLE.map(([m, why]) => (
              <tr key={m}>
                <td>{m}</td>
                <td className="muted small">{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        Claiming a method that was never executed would be fabrication. Each is listed
        with the structural reason it does not apply to a calibrated tree ensemble.
      </p>

      <h2>Generated explanation figures</h2>
      {!figures.dataAvailable ? (
        <NoData what="Figure manifest" note={figures.note} />
      ) : xaiFigures.length === 0 ? (
        <p className="muted small">No explanation figures in the current artifact set.</p>
      ) : (
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Figure</th>
                <th>Title</th>
                <th>Placement</th>
                <th>Formats</th>
              </tr>
            </thead>
            <tbody>
              {xaiFigures.map((f) => (
                <tr key={f.figureId}>
                  <td className="mono">{f.number ?? f.figureId}</td>
                  <td>{f.title}</td>
                  <td>{f.placement}</td>
                  <td className="mono small">{f.outputFormats.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
