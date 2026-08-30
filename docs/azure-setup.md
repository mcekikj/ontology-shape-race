# Azure environment for the ontology experiment

Two services, and the agent uses both: Microsoft Foundry for the reasoning and
a serverless Cosmos DB for Apache Gremlin account for the knowledge. Every
tool call the agent makes is a Gremlin query against one of three graph
containers, one per ontology. The ontology design is the experiment; the model
and the store are the constants.

Serverless Cosmos has no minimum throughput charge, so three graphs of this
size plus a campaign's traffic costs a couple of dollars at most.

## What gets created

One dedicated resource group, one Foundry (Cognitive Services) account, two
model deployments, and one serverless Cosmos DB for Apache Gremlin account
holding the three ontologies as real graphs:

- a small model (the working deployment for the main campaign)
- a frontier model (for the crossover measurement: does a small model on the
  well-shaped ontology beat a frontier model on the badly shaped one?)

Model names and SKUs are chosen at deploy time from what the subscription's
region actually offers - check current availability first, do not assume.

## Deploy

The scripted path is one command - it creates the resource group, the account,
both model deployments (`agent-small` = gpt-5.4-nano, `agent-large` = gpt-5.5,
the pair the published campaigns used) and the budget from `code/infra.bicep`:

```bash
./code/deploy.sh <subscription-id> <alert-email>
```

If the pinned models are unavailable in your region, edit the `models` array
in `infra.bicep` after checking the live listing (below) and re-run
`deploy.sh` - the Bicep template is the only path that creates the Cosmos
account, the `ontologies` database and the three graph containers, all of
which the campaigns require.

## Checking model availability, and what the template creates

To see what is deployable in your region before editing the template:

```bash
az cognitiveservices account list-models \
  --subscription "<subscription id>" -g rg-ontology-agents \
  -n <the ontagents... account> -o table
```

`infra.bicep` creates, in one deployment:

- an AIServices account (S0) with the two model deployments `agent-small` and
  `agent-large`, both GlobalStandard at capacity 10
- a serverless Cosmos DB for Apache Gremlin account, the `ontologies`
  database, and the three graph containers `flat`, `normalized` and `shaped`,
  each partitioned on `/pk`
- a $40 monthly budget with alerts at 50% and 90%

Grant yourself data-plane access if using Entra instead of keys:
`Cognitive Services OpenAI User` on the account, then `az login` locally.

## Configure and run

```bash
cd code
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in both endpoints and keys (see .env.example)

# data is committed, but can be regenerated deterministically:
python3 generate_facts.py && python3 build_ontologies.py
python3 verify_lossless.py     # must print three lossless lines
python3 questions.py
python3 smoke_test.py          # offline; must print ALL PATHS REACHABLE

# the campaign (3 runs, all variants, all bands):
set -a && source .env && set +a
# load the three graphs into Cosmos - the campaigns query these
# (needs COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_KEY in .env)
python3 load_cosmos.py            # loads all three, verifies counts
python3 load_cosmos.py --verify   # counts only
python3 equivalence_check.py      # tools answer the same from either store

python3 run_experiment.py --deployment agent-small --runs 3
python3 run_experiment.py --deployment agent-large --runs 1
python3 analyze.py

# optional: the cross-check the article discusses - the identical grid with
# the tools reading the generator's files instead of the database
python3 run_experiment.py --deployment agent-small --runs 3 --store json

# regenerate the article's figures and diagrams
python3 ../figures/table_results.py
python3 ../figures/json_triptych.py
python3 ../diagrams/render.py
```

## Cost expectations

Per full run: 3 variants x 40 questions = 120 agent episodes. Episodes are
multi-turn (tool loops), so expect a few thousand model calls per campaign.
Measured: the three small-model passes cost **$0.70**, the single large-model
pass **$7.39**, so **$8.09** for the full grid, plus cents for Cosmos request
units. The large model is 90% of that - it is 25 times dearer per input token
- so scope it to fewer bands if you want to economise.

Note the budget is sixteen *model turns* per question, not sixteen tool calls:
a turn may request several tools at once, and the busiest episode made sixty
calls inside its sixteen turns. The normalized ontology spends the most.

## Teardown

```bash
az group delete --subscription "$SUBSCRIPTION" -n "$RG" --yes --no-wait
```

Keep the resource group alive until the article's numbers are settled and any
follow-up measurements are done.
