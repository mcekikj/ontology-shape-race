"""Generate the synthetic fact base - the single source of truth.

Every name here is invented: people, companies, places and the insurer itself
are fictional and generated from made-up word lists. Nothing refers to any real
person, organisation or location. The generator is seeded, so the same facts
come out every time; the experiment is reproducible from this file alone.

All three ontologies are built FROM this file and must re-express it without
gain or loss. The oracle also answers FROM this file, never from an ontology,
so no graph design ever grades its own homework.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20260828
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FIRST = ["Maren", "Tobin", "Elsa", "Rurik", "Sanne", "Dario", "Ilka", "Bram",
         "Odile", "Petra", "Lior", "Anouk", "Casper", "Vera", "Jonas", "Malin",
         "Ivo", "Greet", "Stellan", "Noor", "Fenna", "Aldo", "Mireille", "Sten"]
LAST = ["Voss", "Aldering", "Kraal", "Ostrander", "Fenwick", "Duval", "Harmsen",
        "Lindqvist", "Abernath", "Corvelle", "Stroud", "Vantour", "Bexley",
        "Marwick", "Oduya", "Sablon", "Renner", "Quist", "Halloway", "Ferber"]
REGIONS = ["Northreach", "Veyland", "Amberfen", "Stonehollow", "Cresmoor"]
CITIES = ["Veldmark", "Corriston", "Ostbay", "Larkfield", "Dunmere",
          "Brackwell", "Tarnholm", "Silverden"]
PROVIDER_STEMS = ["Cedarline", "Amberfen", "Stonehollow", "Bluegate", "Ironquay",
                  "Larkfield", "Veyland", "Marrowpoint", "Duskwater", "Fernvale",
                  "Coldharbour", "Wrenfield"]
PROVIDER_KINDS = ["Auto Body", "Collision Works", "Motorworks", "Repair Co",
                  "Panel and Paint", "Restoration"]
SPECIALTIES = ["bodywork", "glass", "electrical", "frame", "paint", "interior"]
PRODUCTS = ["auto", "home", "marine"]
COVERAGE_KINDS = {
    "auto": ["collision", "liability", "theft", "glass"],
    "home": ["fire", "flood", "theft", "liability"],
    "marine": ["hull", "liability", "salvage"],
}
CAUSES = {
    "auto": ["rear-end collision", "hail damage", "theft from vehicle",
             "single-vehicle accident", "windscreen crack"],
    "home": ["kitchen fire", "burst pipe", "storm flooding", "break-in",
             "lightning strike"],
    "marine": ["grounding", "collision at mooring", "storm damage",
               "engine-room fire"],
}
STATUSES = ["submitted", "in_review", "approved", "denied", "settled"]
PAY_METHODS = ["bank transfer", "cheque"]


def money(rng: random.Random, lo: int, hi: int) -> int:
    return rng.randrange(lo, hi, 50)


def generate() -> dict:
    rng = random.Random(SEED)

    regions = [{"id": f"RG-{i+1:02d}", "name": name}
               for i, name in enumerate(REGIONS)]

    names = rng.sample([f"{f} {l}" for f in FIRST for l in LAST], 62)
    adjusters = [
        {"id": f"AJ-{i+1:02d}", "name": names.pop(),
         "region_id": regions[i % len(regions)]["id"],
         "seniority": rng.choice(["junior", "senior", "principal"])}
        for i in range(10)
    ]
    providers = [
        {"id": f"PR-{i+1:02d}",
         "name": f"{PROVIDER_STEMS[i]} {rng.choice(PROVIDER_KINDS)}",
         "region_id": regions[i % len(regions)]["id"],
         "specialty": rng.choice(SPECIALTIES)}
        for i in range(12)
    ]
    holders = [
        {"id": f"PH-{i+1:02d}", "name": names.pop(),
         "city": rng.choice(CITIES), "since_year": rng.randint(2012, 2024)}
        for i in range(40)
    ]

    policies, coverages = [], []
    pol_n = 0
    for holder in holders:
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            pol_n += 1
            product = rng.choice(PRODUCTS)
            pol = {"id": f"PL-{pol_n:03d}", "number": f"P-{7000 + pol_n}",
                   "holder_id": holder["id"], "product": product,
                   "start_year": rng.randint(2018, 2025),
                   "premium": money(rng, 400, 3200),
                   "renewed_from_id": None}
            policies.append(pol)
            kinds = rng.sample(COVERAGE_KINDS[product],
                               rng.randint(2, len(COVERAGE_KINDS[product])))
            for kind in kinds:
                coverages.append({
                    "id": f"CV-{len(coverages)+1:03d}", "policy_id": pol["id"],
                    "kind": kind, "limit": money(rng, 5000, 90000),
                    "deductible": money(rng, 100, 1500),
                })
    # renewal chains: some policies renew an older policy of the same holder
    by_holder = {}
    for pol in policies:
        by_holder.setdefault(pol["holder_id"], []).append(pol)
    for pols in by_holder.values():
        if len(pols) >= 2 and rng.random() < 0.6:
            pols_sorted = sorted(pols, key=lambda p: p["start_year"])
            pols_sorted[-1]["renewed_from_id"] = pols_sorted[0]["id"]

    claims, payments = [], []
    # Shuffled cycles, sized so that every adjuster and provider is very likely
    # to appear in at least one claim. This matters more than it looks: in the
    # flat ontology a provider exists ONLY inside a claim's JSON blob, so a
    # provider that no claim references would be unrecoverable and the flat
    # variant would fail the losslessness proof. The committed SEED satisfies
    # this (verify_lossless.py passes); a different seed is not guaranteed to,
    # which is itself a small demonstration of the article's argument - the
    # flat shape can only represent what something else happens to point at.
    adj_cycle = adjusters * 9
    prov_cycle = providers * 8
    rng.shuffle(adj_cycle)
    rng.shuffle(prov_cycle)
    claim_policies = [rng.choice(policies) for _ in range(90)]
    for i, pol in enumerate(claim_policies):
        pol_covs = [c for c in coverages if c["policy_id"] == pol["id"]]
        cov = rng.choice(pol_covs)
        status = rng.choices(STATUSES, weights=[1, 2, 3, 2, 3])[0]
        claim = {
            "id": f"CL-{i+1:03d}", "number": f"C-{31000 + i}",
            "policy_id": pol["id"], "coverage_kind": cov["kind"],
            "adjuster_id": adj_cycle[i]["id"],
            "provider_id": (prov_cycle[i]["id"]
                            if pol["product"] == "auto" and rng.random() < 0.85
                            else None),
            "status": status,
            "amount_claimed": money(rng, 500, 40000),
            "year": rng.randint(2023, 2026),
            "cause": rng.choice(CAUSES[pol["product"]]),
        }
        claims.append(claim)
        if status in ("approved", "settled"):
            paid_total = int(claim["amount_claimed"] * rng.uniform(0.5, 1.0))
            parts = rng.choice([1, 1, 2])
            split = ([paid_total] if parts == 1
                     else [paid_total // 2, paid_total - paid_total // 2])
            for part in split:
                payments.append({
                    "id": f"PM-{len(payments)+1:03d}", "claim_id": claim["id"],
                    "amount": part, "year": claim["year"],
                    "method": rng.choice(PAY_METHODS),
                })

    return {
        "insurer": "Aldervane Mutual (fictional)",
        "seed": SEED,
        "entities": {
            "regions": regions, "adjusters": adjusters, "providers": providers,
            "policyholders": holders, "policies": policies,
            "coverages": coverages, "claims": claims, "payments": payments,
        },
    }


def canonical_facts(data: dict) -> set:
    """The fact base as a flat set of tuples - the losslessness yardstick.

    Every ontology reconstructor must reproduce exactly this set from its own
    graph, or the variant added, dropped or blurred a fact.
    """
    e = data["entities"]
    facts = set()
    for r in e["regions"]:
        facts.add(("region", r["id"], "name", r["name"]))
    for a in e["adjusters"]:
        facts.add(("adjuster", a["id"], "name", a["name"]))
        facts.add(("adjuster", a["id"], "seniority", a["seniority"]))
        facts.add(("adjuster", a["id"], "works_in", a["region_id"]))
    for p in e["providers"]:
        facts.add(("provider", p["id"], "name", p["name"]))
        facts.add(("provider", p["id"], "specialty", p["specialty"]))
        facts.add(("provider", p["id"], "located_in", p["region_id"]))
    for h in e["policyholders"]:
        facts.add(("policyholder", h["id"], "name", h["name"]))
        facts.add(("policyholder", h["id"], "city", h["city"]))
        facts.add(("policyholder", h["id"], "since_year", h["since_year"]))
    for p in e["policies"]:
        facts.add(("policy", p["id"], "number", p["number"]))
        facts.add(("policy", p["id"], "product", p["product"]))
        facts.add(("policy", p["id"], "start_year", p["start_year"]))
        facts.add(("policy", p["id"], "premium", p["premium"]))
        facts.add(("policy", p["id"], "held_by", p["holder_id"]))
        if p["renewed_from_id"]:
            facts.add(("policy", p["id"], "renewed_from", p["renewed_from_id"]))
    for c in e["coverages"]:
        facts.add(("coverage", c["id"], "kind", c["kind"]))
        facts.add(("coverage", c["id"], "limit", c["limit"]))
        facts.add(("coverage", c["id"], "deductible", c["deductible"]))
        facts.add(("coverage", c["id"], "on_policy", c["policy_id"]))
    for c in e["claims"]:
        facts.add(("claim", c["id"], "number", c["number"]))
        facts.add(("claim", c["id"], "coverage_kind", c["coverage_kind"]))
        facts.add(("claim", c["id"], "status", c["status"]))
        facts.add(("claim", c["id"], "amount_claimed", c["amount_claimed"]))
        facts.add(("claim", c["id"], "year", c["year"]))
        facts.add(("claim", c["id"], "cause", c["cause"]))
        facts.add(("claim", c["id"], "filed_against", c["policy_id"]))
        facts.add(("claim", c["id"], "assessed_by", c["adjuster_id"]))
        if c["provider_id"]:
            facts.add(("claim", c["id"], "repaired_at", c["provider_id"]))
    for p in e["payments"]:
        facts.add(("payment", p["id"], "amount", p["amount"]))
        facts.add(("payment", p["id"], "year", p["year"]))
        facts.add(("payment", p["id"], "method", p["method"]))
        facts.add(("payment", p["id"], "settles", p["claim_id"]))
    return facts


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    data = generate()
    out = DATA_DIR / "facts.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    e = data["entities"]
    counts = {k: len(v) for k, v in e.items()}
    print(f"{out}: {counts}, {len(canonical_facts(data))} canonical facts")


if __name__ == "__main__":
    main()
