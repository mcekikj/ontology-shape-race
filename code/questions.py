"""Generate the question set and compute every answer from the raw facts.

Four bands:
  L - lookup: one fact about one entity
  M - near: two to three conceptual hops
  H - far: four or more hops, or aggregation across a subgraph
  U - unanswerable: asks for facts the fact base deliberately never models;
      the correct answer is to say so, and the expected string is NOT_MODELED

The oracle is this module: answers are computed from facts.json by plain code,
never by a model and never from any ontology. All three graphs are scored
against the same computed answer.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED = 20260829
NOT_MODELED = "NOT_MODELED"
PER_TEMPLATE = 4


def index(data):
    e = data["entities"]
    return {
        "regions": {r["id"]: r for r in e["regions"]},
        "adjusters": {a["id"]: a for a in e["adjusters"]},
        "providers": {p["id"]: p for p in e["providers"]},
        "holders": {h["id"]: h for h in e["policyholders"]},
        "policies": {p["id"]: p for p in e["policies"]},
        "coverages": e["coverages"],
        "claims": e["claims"],
        "payments": e["payments"],
    }


def build_questions(data) -> list:
    rng = random.Random(SEED)
    ix = index(data)
    claims = ix["claims"]
    pays_by_claim = {}
    for p in ix["payments"]:
        pays_by_claim.setdefault(p["claim_id"], []).append(p)

    questions = []

    def add(band, template_id, question, answer, answer_type):
        questions.append({
            "id": f"{band}-{len([q for q in questions if q['band'] == band]) + 1:02d}",
            "band": band, "template": template_id,
            "question": question, "answer": answer, "answer_type": answer_type,
        })

    # ------------------------------------------------------------- band L ----
    for c in rng.sample(claims, PER_TEMPLATE):
        add("L", "claim-status",
            f"What is the current status of claim {c['number']}?",
            c["status"], "string")
    for p in rng.sample(list(ix["policies"].values()), PER_TEMPLATE):
        add("L", "policy-premium",
            f"What is the annual premium of policy {p['number']}?",
            p["premium"], "number")
    for pr in rng.sample(list(ix["providers"].values()), 2):
        add("L", "provider-specialty",
            f"What is the specialty of the repair provider called "
            f"{pr['name']}?", pr["specialty"], "string")

    # ------------------------------------------------------------- band M ----
    for c in rng.sample(claims, PER_TEMPLATE):
        adj = ix["adjusters"][c["adjuster_id"]]
        add("M", "claim-adjuster",
            f"Which adjuster assessed claim {c['number']}? Give the name.",
            adj["name"], "string")
    paid_claims = [c for c in claims if c["id"] in pays_by_claim]
    for c in rng.sample(paid_claims, PER_TEMPLATE):
        total = sum(p["amount"] for p in pays_by_claim[c["id"]])
        add("M", "claim-paid-total",
            f"What is the total amount paid out so far on claim "
            f"{c['number']}?", total, "number")
    repaired = [c for c in claims if c["provider_id"]]
    for c in rng.sample(repaired, 2):
        region = ix["regions"][ix["providers"][c["provider_id"]]["region_id"]]
        add("M", "claim-repair-region",
            f"In which region is the repair provider handling claim "
            f"{c['number']} located?", region["name"], "string")

    # ------------------------------------------------------------- band H ----
    def holder_paid_total(holder_id):
        total = 0
        for c in claims:
            if ix["policies"][c["policy_id"]]["holder_id"] != holder_id:
                continue
            total += sum(p["amount"] for p in pays_by_claim.get(c["id"], []))
        return total

    rich_holders = [h for h in ix["holders"].values()
                    if holder_paid_total(h["id"]) > 0]
    for h in rng.sample(rich_holders, PER_TEMPLATE):
        add("H", "holder-paid-total",
            f"Across all claims filed against any policy held by "
            f"{h['name']}, what is the total amount that has been paid out?",
            holder_paid_total(h["id"]), "number")

    for c in rng.sample(claims, PER_TEMPLATE):
        holder = ix["holders"][ix["policies"][c["policy_id"]]["holder_id"]]
        add("H", "claim-holder-city",
            f"In which city does the policyholder whose policy claim "
            f"{c['number']} was filed against live?", holder["city"], "string")

    def distinct_kinds(holder_id):
        kinds = set()
        for cov in ix["coverages"]:
            pol = ix["policies"][cov["policy_id"]]
            if pol["holder_id"] == holder_id:
                kinds.add(cov["kind"])
        return len(kinds)

    multi = [h for h in ix["holders"].values() if distinct_kinds(h["id"]) >= 3]
    for h in rng.sample(multi, 2):
        add("H", "holder-coverage-kinds",
            f"How many distinct coverage kinds exist across all policies "
            f"held by {h['name']}?", distinct_kinds(h["id"]), "number")

    # ------------------------------------------------------------- band U ----
    for h in rng.sample(list(ix["holders"].values()), 3):
        add("U", "holder-phone",
            f"What is the phone number of policyholder {h['name']}?",
            NOT_MODELED, "string")
    for c in rng.sample(claims, 3):
        add("U", "claim-weather",
            f"What was the weather like on the day the incident behind claim "
            f"{c['number']} happened?", NOT_MODELED, "string")
    for a in rng.sample(list(ix["adjusters"].values()), 2):
        add("U", "adjuster-email",
            f"What is the work email address of adjuster {a['name']}?",
            NOT_MODELED, "string")
    for c in rng.sample([c for c in claims
                         if "vehicle" in c["cause"] or "collision" in c["cause"]], 2):
        add("U", "claim-vin",
            f"What is the VIN of the vehicle involved in claim "
            f"{c['number']}?", NOT_MODELED, "string")

    return questions


def main() -> None:
    data = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    questions = build_questions(data)
    out = DATA_DIR / "questions.json"
    out.write_text(json.dumps(questions, indent=2) + "\n", encoding="utf-8")
    bands = {}
    for q in questions:
        bands[q["band"]] = bands.get(q["band"], 0) + 1
    print(f"{out}: {len(questions)} questions {bands}")


if __name__ == "__main__":
    main()
