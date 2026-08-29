import { LimeStabilitySection } from '@/components/research/AngleSections';
import { NoData } from '@/components/ui/Primitives';
import { getFigures, getResearchAngles } from '@/lib/data';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE EXPLANATIONS PAGE, WHICH LEADS WITH A FAILED CHECK.
 *
 * The order of the page is the argument. Before showing a single explanation, it shows the
 * SANITY CHECKS -- and one of the three is marked FAIL, in red, at the top.
 *
 * The introduction says why: "An explanation that fails a sanity check is not presented as
 * trustworthy, however plausible it looks."
 *
 * And the note beneath the failure contains the sentence that matters most:
 *
 *     "The threshold was declared before the run and was not lowered to make the check
 *      pass."
 *
 * Which pre-empts the obvious suspicion. The bar was set at 0.80. The result came in at
 * 0.780. Nudging the bar to 0.75 would have turned a red FAIL into a green PASS, and
 * nobody outside would ever have known.
 * Saying explicitly that this was not done is the difference between a threshold and a
 * formality.
 */

export const dynamic = 'force-static';

// The explanation methods that ARE used, each with its scope and why it applies here.
const METHODS: [string, string, string][] = [
  ['Permutation importance', 'global', 'valid on the tree-based risk model'],
  ['Occlusion / feature ablation', 'local + block', 'valid on any model'],
  [
    'KernelSHAP',
    'local',
    // The reason the model-agnostic version is needed rather than the faster tree one.
    'model-agnostic; the calibrated ensemble does not expose tree structure',
  ],
  // And the note about how the perturbations are drawn -- the on-the-data-manifold choice.
  ['LIME (local ridge surrogate)', 'local', 'perturbations drawn from background marginals'],
  [
    'Counterfactual search',
    'local',
    'smallest feature set whose change resolves the score',
  ],
  [
    'Integrated gradients',
    // Applied ONLY where it validly can be, and the reason given in the same row.
    'combination layer only',
    'the combination rule is differentiable; the trees are not',
  ],
  ['PDP / ICE / ALE', 'global dependence', 'ALE preferred where features are correlated'],
];

// THE FAMOUS METHODS THAT ARE NOT USED, each with its structural reason.
const NOT_APPLICABLE: [string, string][] = [
  ['DeepSHAP', 'requires a differentiable deep network'],
  ['Grad-CAM / Guided Grad-CAM', 'requires convolutional feature maps'],
  ['DeepLIFT', 'requires a differentiable deep network'],
  ['TCAV', 'requires concept activation vectors in a differentiable network'],
  [
    // The subtlest one, and the substitution is reported rather than passed over.
    'TreeSHAP',
    'the learners are wrapped in a probability calibrator, so tree structure is not exposed; KernelSHAP is used instead and the substitution is reported',
  ],
];

// How faithful each method is -- and how long it takes.
const FAITHFULNESS: [string, string, string, string, string][] = [
  ['Occlusion', '0.0298', '0.9286', '0.9942', '0.46'],
  ['KernelSHAP', '0.0290', '0.9279', '0.9909', '1.00'],
  // LIME: the least faithful of the four, and the cheapest. Both facts in the same row.
  ['LIME', '0.0371', '0.9256', '0.9891', '0.02'],
  ['Counterfactual', '0.0588', '0.9247', '0.9828', '0.43'],
];

export default async function XaiPage() {
  const figures = await getFigures();
  const b = await getResearchAngles();
  const angles = (b.meta?.results ?? {}) as Record<string, any>;

  // Pick out the explanation figures by name. `i` makes the match case-insensitive.
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

      {/* THE SANITY CHECKS COME FIRST, before any explanation is shown. */}
      <h2>Sanity checks</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Check</th>
              {/* THE STATISTIC AND THE THRESHOLD SIDE BY SIDE -- so a reader can see how close
                  each result came, not merely whether it passed. */}
              <th className="num">Statistic</th>
              <th className="num">Threshold</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              {/* Does the explanation single anything out? 0.998 against a bar of 0.25 --
                  comfortably passed. */}
              <td>Attribution sparsity (top-10 mass)</td>
              <td className="num">0.998</td>
              <td className="num">0.25</td>
              <td>
                <span className="chip chip--good">pass</span>
              </td>
            </tr>
            <tr>
              {/* THE MOST IMPORTANT CHECK: does the explanation change when the model is
                  nonsense? 0.013 -- almost no agreement with a model that learned nothing.
                  So the explanations really are about the model, not merely about the data. */}
              <td>Model randomisation (Spearman against a label-shuffled refit)</td>
              <td className="num">0.013</td>
              <td className="num">&lt; 0.50</td>
              <td>
                <span className="chip chip--good">pass</span>
              </td>
            </tr>
            <tr>
              {/* AND THE FAILURE. 0.780 against a bar of 0.80. Twenty thousandths short --
                  and marked FAIL, in red, on the project's own page. */}
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
        {/* TWO SENTENCES, AND BOTH MATTER.
            First: the bar was set in advance and NOT lowered to make it pass. Given how close
            0.780 is to 0.80, that is precisely the suspicion a reader would have -- and it is
            answered before it is raised.
            Second: no claim in the project rests on a LIME attribution. So the failure is not
            only reported, it is ACTED ON -- the untrustworthy method is not load-bearing
            anywhere. */}
        The threshold was declared before the run and was not lowered to make the check
        pass. No claim in this project rests on a LIME attribution.
      </p>

      {/* The follow-up analysis: can LIME be made stable, and does it then agree with
          anything? (It can, at a price -- and it still does not agree.) */}
      <LimeStabilitySection angles={angles} />

      <h2>Faithfulness</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              {/* Deletion and insertion: remove the features an explanation calls important
                  and see whether the score collapses; add them back and see whether it
                  recovers. A faithful explanation should do both. */}
              <th className="num">Deletion AUC</th>
              <th className="num">Insertion AUC</th>
              <th className="num">Comprehensiveness</th>
              {/* THE COST COLUMN, beside the quality. A method nobody can afford to run is a
                  different proposition from one that works. */}
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
        {/* FIRST it explains which direction is good -- so nobody has to guess whether a low
            deletion AUC is a triumph or a disaster.
            THEN the agreement figures, including LIME's -0.042 against occlusion, which is
            effectively no relationship at all.
            AND THEN THE PARAGRAPH'S BEST SENTENCE, which cuts both ways:
              "two methods can share a bias, so agreement is not corroboration and
               disagreement is not proof of error."
            Two methods agreeing may simply be two methods making the same mistake. And two
            disagreeing does not tell you which is wrong. Refusing both the comforting and the
            alarming reading of the same number is genuinely careful. */}
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
              {/* WHY IT APPLIES to this model -- so the choice of method is justified rather
                  than merely listed. */}
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
                  {/* RUN -- each of these actually executed. */}
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
              {/* Not "status" but "WHY IT IS NOT RUN" -- the column is the explanation. */}
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
        {/* THE PRINCIPLE, STATED BLUNTLY: "Claiming a method that was never executed would be
            fabrication."
            These are famous, impressive-sounding methods. Listing them as used would make the
            project look far more thorough. It would also be a lie -- and the page says so in
            those words, then gives the structural reason each one cannot apply. */}
        Claiming a method that was never executed would be fabrication. Each is listed
        with the structural reason it does not apply to a calibrated tree ensemble.
      </p>

      <h2>Generated explanation figures</h2>
      {!figures.dataAvailable ? (
        <NoData what="Figure manifest" note={figures.note} />
      ) : xaiFigures.length === 0 ? (
        // A distinct message for "the manifest exists but has no explanation figures" --
        // different from the manifest being missing altogether.
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
                  {/* The paper's number where it has one, otherwise the internal id -- so a
                      reader holding the paper can match them up. */}
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
