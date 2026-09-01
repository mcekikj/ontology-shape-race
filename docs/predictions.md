# Registered predictions - the ablation campaign

Committed BEFORE the first episode of the ablation campaign runs. The
follow-up article scores these one by one, including the wrong ones. The
commit timestamp is the registration; nothing here is edited after the
campaigns start.

## The experiment

The shaped ontology won the measured race. But "shaped" bundles two design
decisions: a domain vocabulary (typed vertices, named edges, and node ids
that carry their type) and a geometry (ninety derived held_by shortcuts).
This campaign separates them with a 2x2 ablation:

|                    | shortcuts kept | shortcuts removed |
|--------------------|----------------|-------------------|
| domain vocabulary  | shaped         | shaped-minus      |
| anonymous          | shaped-anon    | shaped-bare       |

All four variants are mechanical, invertible transforms of the committed
shaped graph (build_ablations.py), proven lossless and proven to differ
only as described (verify_ablations.py). The instrument - tools, agent,
prompts, questions, caps, oracle - is byte-identical to the published
campaign; run_experiment.py is untouched and the new variants are selected
with --variants. Same Cosmos account, one container per variant, same two
Foundry deployments.

## Predictions

**P1. Vocabulary carries more than geometry.** Averaged over all bands on
the small model, the accuracy drop from anonymising the vocabulary
(shaped vs shaped-anon) will be larger than the drop from removing the
shortcuts (shaped vs shaped-minus).

Reasoning: the published campaign's biggest between-shape gaps sat on
bands where recognition plausibly mattered (band L: shaped 0.967 vs flat
0.533) rather than on path length alone, and the shortcut serves exactly
one question template.

**P2. The shortcut effect concentrates on its home turf.** shaped-minus
loses measurably on the claim-holder-city template (the only path held_by
compresses) and is within noise of shaped on the remaining answerable
templates.

**P3. Structure without language lands near normalized.** shaped-bare's
overall small-model accuracy falls within the published normalized
per-run range (0.500 to 0.650 across three runs, 0.592 overall) despite
having 5.8x fewer vertices - the claim being that normalized's cost was
never the vertex count, it was the silence.

**P4. The large model buys its way out of language too.** On gpt-5.5 the
four variants converge: every variant scores within noise of the published
large-model shaped result on answerable bands, at the same roughly 14x
cost per question.

**P5 (refusal risk, the one I am least sure of).** Anonymised variants
false-refuse more: NOT_MODELED on answerable questions rises on
shaped-anon and shaped-bare relative to shaped, because an agent that
cannot recognise the schema concludes the fact is not modelled - the flat
graph's disease, arrived at by a different road.

## What would falsify the article's framing

If shaped-anon matches shaped everywhere (vocabulary never mattered) AND
shaped-minus matches shaped everywhere (geometry never mattered), the
2x2 has found that the halves are individually redundant on this
workload, and the article must say the winner's margin came from their
interaction or from neither - not quietly pick whichever cell looks best.

## Campaign plan

- Small model (agent-small): 3 runs x 4 variants x 40 questions = 480
  episodes.
- Large model (agent-large): 1 run x 4 variants x 40 questions = 160
  episodes, crossover check.
- shaped re-runs fresh in this campaign; article-3 numbers are quoted as
  history only and never compared against directly.
- Store: cosmos. Same receipts format; every record carries its variant.
