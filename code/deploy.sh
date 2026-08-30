#!/usr/bin/env bash
# Deploy the ontology-experiment environment. Idempotent; safe to re-run.
# Usage: ./deploy.sh <subscription-id> <alert-email>
set -euo pipefail

SUBSCRIPTION="${1:?usage: deploy.sh <subscription-id> <alert-email>}"
ALERT_EMAIL="${2:?usage: deploy.sh <subscription-id> <alert-email>}"
RG="rg-ontology-agents"
LOCATION="swedencentral"

az group create --subscription "$SUBSCRIPTION" -n "$RG" -l "$LOCATION" \
  --tags purpose=ontology-agents-article-demo teardown-by=2026-09-30 -o none

az deployment group create --subscription "$SUBSCRIPTION" -g "$RG" \
  -f "$(dirname "$0")/infra.bicep" -p alertEmail="$ALERT_EMAIL" \
  --query 'properties.outputs' -o json

echo
cat <<'NEXT'

Next steps - the agent queries the graphs, so Cosmos must be populated first:

  1. Put both endpoints in code/.env (see the outputs above and .env.example):
       ONTOLOGY_AGENTS_ENDPOINT, COSMOS_GREMLIN_ENDPOINT
  2. Fetch the keys:
       az cognitiveservices account keys list -g rg-ontology-agents \
         -n <foundry-account> --query key1 -o tsv
       az cosmosdb keys list -g rg-ontology-agents \
         -n <cosmos-account> --query primaryMasterKey -o tsv
  3. Load the graphs and run:
       cd code && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
       set -a && source .env && set +a
       .venv/bin/python load_cosmos.py
       .venv/bin/python run_experiment.py --deployment agent-small --runs 3
NEXT
