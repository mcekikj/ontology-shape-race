# ontology-agents-article

The third measurement piece: same facts, three ontology shapes, one traversal
agent on Microsoft Foundry - and what each design costs per question.

Working title: *Your Agent Is Not Confused, Your Ontology Is.*

## Status

- Code: complete and verified offline (losslessness proven, smoke test green)
- Data: generated, deterministic (seeded), fully synthetic and fictional
- Measured campaigns: DONE - the agent's tools querying Cosmos DB for Gremlin,
  480 episodes, 4.29M tokens, $8.09
  - `agent-small` (gpt-5.4-nano): 3 passes x 3 variants x 40 questions
  - `agent-large` (gpt-5.5): 1 pass x 3 variants x 40 questions (crossover)
- Cross-check campaigns: the same grid re-run with the tools reading the
  generator's files instead of the database, 480 episodes, $7.74. Kept as
  evidence that the store is not a variable; never mixed into the headline
  numbers - records carry a `store` field, and the per-campaign tables,
  the crossover and the figures all filter on it
- Article: published separately; every number in it comes from the Cosmos
  campaigns and is reproducible from `code/analyze.py` and the receipts here

## Headline results

All figures below are the Cosmos campaigns - the measured ones.

Small model, three passes, accuracy over all bands: **shaped 0.842, flat
0.783, normalized 0.592**, with run-to-run spreads of 0.075, 0.075 and 0.150
respectively. The
aggregate gap between shaped and flat does not clear that noise; the band-level
gap does, and by a distance - on single-fact lookups shaped scores 0.967
against flat's 0.533.

The two failing shapes fail in opposite directions. Flat dissolves entities
into properties, so the agent refused 18 of 90 answerable questions as
`NOT_MODELED` while the facts sat in the database. Normalized makes every
entity a vertex but every path long, so it ran out of turns 25 times and
scored 0.133 on the long-path band.

Crossover: the large model answered 30 of 30 answerable questions on BOTH flat
and shaped, at roughly 14x the cost per question of the small model on shaped.
You can buy your way out of a badly shaped ontology; a good shape is what lets
you run a cheap model.

## Layout

- `code/` - the whole experiment:
  - `generate_facts.py` - seeded synthetic fact base (the single source of truth)
  - `build_ontologies.py` - flat / normalized / shaped builders + reconstructors
  - `verify_lossless.py` - proves all three variants re-express EXACTLY the
    same 2,435 facts (run it; the experiment is invalid unless it passes)
  - `graph.py` - the four traversal tools, identical for every variant
  - `questions.py` - 40 questions in 4 bands (lookup / near / far /
    unanswerable), answers computed from the raw facts, never by a model
  - `agent.py` - the Foundry function-calling agent (the only SDK module)
  - `run_experiment.py` - campaign runner
  - `analyze.py` - computes every number the article quotes
  - `smoke_test.py` - offline spot-check that representative questions are
    answerable through the four tools on every ontology
  - `load_cosmos.py` - loads the three graphs into Azure Cosmos DB for
    Apache Gremlin, and verifies the counts against the JSON
  - `graph_cosmos.py` - the same four tools over Gremlin; what the campaigns
    actually query
  - `equivalence_check.py` - replays recorded tool calls against both stores
  - `infra.bicep`, `deploy.sh` - the entire Azure environment, reproducible
    with one command
  - `requirements.txt`, `.env.example` - dependencies and configuration
- `data/` - facts.json, the three ontology-*.json graphs, questions.json
- `results/` - the campaign receipts: one JSONL line per agent episode with
  the full tool-call trace, tokens, latency, answer and verdict. This is what
  every number in the article is computed from (plus the pilot run, kept for
  completeness but read by nothing)
- `figures/` - `tables.py` renders all seven of the article's tables,
  `json_triptych.py` the raw-data comparison and `cover.py` the featured
  image; every value and every drawn subgraph is computed from the receipts
  and the graph files, so a re-run re-renders correct figures
- `diagrams/` - mermaid sources, `render.py`, and the rendered PNGs
- `docs/azure-setup.md` - infrastructure, run and teardown guide
- `docs/gremlin-queries.md` - the same questions asked of all three graphs in
  Cosmos, with verified outputs

## Reproducibility notes

The fact base, the questions and all three graphs regenerate byte-identically
from their seeds (`generate_facts.SEED`, `questions.SEED`), and CI enforces it. Two honest caveats for anyone re-running the
Azure campaigns rather than re-analysing the committed receipts:

- The normalized builder originally iterated an unordered set, so the *order*
  of its edge list varied between rebuilds (contents never did). That is fixed,
  but it means the neighbour ordering `traverse` returned during the published
  campaign is not recoverable, and a fresh normalized run may differ slightly.
  Flat and shaped were always deterministic.
- `traverse` returns an empty list for an edge type a graph does not have,
  which the agent cannot distinguish from a genuine dead end. The published
  campaigns ran with that behaviour and it is documented in the article's
  limitations rather than patched after the fact.

## Continuous verification

`.github/workflows/verify.yml` runs on pushes to `main` and on pull requests,
entirely offline: it
regenerates the fact base from the seed, rebuilds the three ontologies, proves
all three are lossless, regenerates the questions and their computed answers,
spot-checks that answers are reachable through the four tools, and fails if the
committed data differs by a byte from what the seed produces.

## The graphs in Cosmos DB

The three ontologies live in Azure Cosmos DB for Apache Gremlin, one container
per shape (`code/load_cosmos.py`), and that is what the agent traverses: every
tool call in the measured campaigns is a Gremlin query. All three sit in the
same account under the same tool layer, so the store is held constant and the
shape stays the only variable.

`code/equivalence_check.py --all` replays every recorded tool call against both
Cosmos and the files the generator emits, and confirms the two return identical
answers - evidence that the engine underneath is not shaping what the agent
sees. The clearest single line:

```gremlin
g.V().hasLabel('policy').count()
```

returns **0** on flat (a policy is not a node), **0** on normalized (it is a
node, but labelled `Resource`), and **75** on shaped. Two zeros, two different
diseases.

## The rules that make it an experiment

1. One fact base; each ontology is a lossless re-expression (shortcut edges
   are derived, never new knowledge) - enforced by `verify_lossless.py`.
2. The tool surface, agent scaffolding, prompts, questions and models are
   identical across variants; only the graph shape varies.
3. Ground truth is computed from the raw facts by `questions.py`, so no graph
   design grades its own homework.
4. Every answer carries its tool-call trace - the path is the receipt.
5. Repeated runs; no single-run conclusions.

All data is synthetic: every person, company, place and the insurer itself are
fictional, generated from invented word lists with a fixed seed.
