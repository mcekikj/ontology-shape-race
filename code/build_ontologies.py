"""Build the three ontologies from the same fact base.

Each variant is a different SHAPE of the same truth:

  flat        - few fat nodes, everything embedded as properties, one generic
                edge type. What most teams actually ship first.
  normalized  - academically pure reification: entities carry no properties,
                every attribute is its own node, every relationship is its own
                node. Nothing is wrong with it, except the cost of walking it.
  shaped      - typed nodes, typed directional edges, deliberate granularity,
                and derived shortcut edges exactly where traversal would
                otherwise be expensive. Designed for an agent, not a schema
                diagram.

Every builder has a matching reconstructor that walks the built graph back
into the canonical fact set. verify_lossless.py asserts all three reconstruct
to EXACTLY the same facts - no variant may know more or less than another.
Derived shortcut edges are marked derived and excluded from reconstruction:
they re-express facts already present, they do not add knowledge.

Graph format (shared): {"variant", "nodes": {id: {"type", "props"}},
"edges": [{"src", "type", "dst", "props"}]}
"""

from __future__ import annotations

import json
from pathlib import Path

from generate_facts import canonical_facts

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def nid(etype: str, eid: str) -> str:
    return f"{etype}:{eid}"


# ---------------------------------------------------------------- shaped ----

def build_shaped(data: dict) -> dict:
    e = data["entities"]
    nodes, edges = {}, []

    def node(etype, eid, props):
        nodes[nid(etype, eid)] = {"type": etype, "props": props}

    def edge(src, etype, dst, derived=False):
        rec = {"src": src, "type": etype, "dst": dst, "props": {}}
        if derived:
            rec["props"]["derived"] = True
        edges.append(rec)

    for r in e["regions"]:
        node("region", r["id"], {"name": r["name"]})
    for a in e["adjusters"]:
        node("adjuster", a["id"], {"name": a["name"], "seniority": a["seniority"]})
        edge(nid("adjuster", a["id"]), "works_in", nid("region", a["region_id"]))
    for p in e["providers"]:
        node("provider", p["id"], {"name": p["name"], "specialty": p["specialty"]})
        edge(nid("provider", p["id"]), "located_in", nid("region", p["region_id"]))
    for h in e["policyholders"]:
        node("policyholder", h["id"],
             {"name": h["name"], "city": h["city"], "since_year": h["since_year"]})
    for p in e["policies"]:
        node("policy", p["id"],
             {"number": p["number"], "product": p["product"],
              "start_year": p["start_year"], "premium": p["premium"]})
        edge(nid("policy", p["id"]), "held_by", nid("policyholder", p["holder_id"]))
        if p["renewed_from_id"]:
            edge(nid("policy", p["id"]), "renewed_from",
                 nid("policy", p["renewed_from_id"]))
    for c in e["coverages"]:
        node("coverage", c["id"],
             {"kind": c["kind"], "limit": c["limit"],
              "deductible": c["deductible"]})
        edge(nid("coverage", c["id"]), "on_policy", nid("policy", c["policy_id"]))
    holder_of_policy = {p["id"]: p["holder_id"] for p in e["policies"]}
    for c in e["claims"]:
        node("claim", c["id"],
             {"number": c["number"], "coverage_kind": c["coverage_kind"],
              "status": c["status"], "amount_claimed": c["amount_claimed"],
              "year": c["year"], "cause": c["cause"]})
        edge(nid("claim", c["id"]), "filed_against", nid("policy", c["policy_id"]))
        edge(nid("claim", c["id"]), "assessed_by",
             nid("adjuster", c["adjuster_id"]))
        if c["provider_id"]:
            edge(nid("claim", c["id"]), "repaired_at",
                 nid("provider", c["provider_id"]))
        # derived shortcut: claim to holder without the policy hop; this is
        # re-expression of held_by + filed_against, not new knowledge
        edge(nid("claim", c["id"]), "held_by",
             nid("policyholder", holder_of_policy[c["policy_id"]]), derived=True)
    for p in e["payments"]:
        node("payment", p["id"],
             {"amount": p["amount"], "year": p["year"], "method": p["method"]})
        edge(nid("payment", p["id"]), "settles", nid("claim", p["claim_id"]))

    return {"variant": "shaped", "nodes": nodes, "edges": edges}


RELATION_ATTRS = {
    ("adjuster", "works_in"), ("provider", "located_in"),
    ("policy", "held_by"), ("policy", "renewed_from"),
    ("coverage", "on_policy"), ("claim", "filed_against"),
    ("claim", "assessed_by"), ("claim", "repaired_at"),
    ("payment", "settles"),
}
RELATION_TARGET = {
    "works_in": "region", "located_in": "region", "held_by": "policyholder",
    "renewed_from": "policy", "on_policy": "policy", "filed_against": "policy",
    "assessed_by": "adjuster", "repaired_at": "provider", "settles": "claim",
}


def reconstruct_shaped(graph: dict) -> set:
    facts = set()
    for node_id, rec in graph["nodes"].items():
        etype, eid = node_id.split(":", 1)
        for attr, value in rec["props"].items():
            facts.add((etype, eid, attr, value))
    for edge in graph["edges"]:
        if edge["props"].get("derived"):
            continue
        setype, seid = edge["src"].split(":", 1)
        _, deid = edge["dst"].split(":", 1)
        facts.add((setype, seid, edge["type"], deid))
    return facts


# ------------------------------------------------------------------ flat ----

def build_flat(data: dict) -> dict:
    """Two fat node types and one generic edge. Adjusters, providers, regions,
    coverages and payments exist only as JSON blobs inside properties - which
    is exactly how denormalized stores look in the wild."""
    e = data["entities"]
    regions = {r["id"]: r for r in e["regions"]}
    adjusters = {a["id"]: a for a in e["adjusters"]}
    providers = {p["id"]: p for p in e["providers"]}
    covs_by_policy = {}
    for c in e["coverages"]:
        covs_by_policy.setdefault(c["policy_id"], []).append(
            {"id": c["id"], "kind": c["kind"], "limit": c["limit"],
             "deductible": c["deductible"]})
    pays_by_claim = {}
    for p in e["payments"]:
        pays_by_claim.setdefault(p["claim_id"], []).append(
            {"id": p["id"], "amount": p["amount"], "year": p["year"],
             "method": p["method"]})

    nodes, edges = {}, []
    for h in e["policyholders"]:
        pols = []
        for p in e["policies"]:
            if p["holder_id"] != h["id"]:
                continue
            pols.append({
                "id": p["id"], "number": p["number"], "product": p["product"],
                "start_year": p["start_year"], "premium": p["premium"],
                "renewed_from_id": p["renewed_from_id"],
                "coverages": covs_by_policy.get(p["id"], []),
            })
        nodes[nid("policyholder", h["id"])] = {
            "type": "policyholder",
            "props": {"name": h["name"], "city": h["city"],
                      "since_year": h["since_year"],
                      "policies": json.dumps(pols)},
        }
    holder_of_policy = {p["id"]: p["holder_id"] for p in e["policies"]}
    for c in e["claims"]:
        adj = adjusters[c["adjuster_id"]]
        adj_blob = {"id": adj["id"], "name": adj["name"],
                    "seniority": adj["seniority"],
                    "region": {"id": adj["region_id"],
                               "name": regions[adj["region_id"]]["name"]}}
        prov_blob = None
        if c["provider_id"]:
            prov = providers[c["provider_id"]]
            prov_blob = {"id": prov["id"], "name": prov["name"],
                         "specialty": prov["specialty"],
                         "region": {"id": prov["region_id"],
                                    "name": regions[prov["region_id"]]["name"]}}
        nodes[nid("claim", c["id"])] = {
            "type": "claim",
            "props": {"number": c["number"], "policy_id": c["policy_id"],
                      "coverage_kind": c["coverage_kind"], "status": c["status"],
                      "amount_claimed": c["amount_claimed"], "year": c["year"],
                      "cause": c["cause"], "adjuster": json.dumps(adj_blob),
                      "provider": json.dumps(prov_blob),
                      "payments": json.dumps(pays_by_claim.get(c["id"], []))},
        }
        edges.append({"src": nid("policyholder", holder_of_policy[c["policy_id"]]),
                      "type": "related", "dst": nid("claim", c["id"]),
                      "props": {}})
    return {"variant": "flat", "nodes": nodes, "edges": edges}


def reconstruct_flat(graph: dict) -> set:
    facts = set()
    for node_id, rec in graph["nodes"].items():
        etype, eid = node_id.split(":", 1)
        props = rec["props"]
        if etype == "policyholder":
            for attr in ("name", "city", "since_year"):
                facts.add((etype, eid, attr, props[attr]))
            for pol in json.loads(props["policies"]):
                for attr in ("number", "product", "start_year", "premium"):
                    facts.add(("policy", pol["id"], attr, pol[attr]))
                facts.add(("policy", pol["id"], "held_by", eid))
                if pol["renewed_from_id"]:
                    facts.add(("policy", pol["id"], "renewed_from",
                               pol["renewed_from_id"]))
                for cov in pol["coverages"]:
                    for attr in ("kind", "limit", "deductible"):
                        facts.add(("coverage", cov["id"], attr, cov[attr]))
                    facts.add(("coverage", cov["id"], "on_policy", pol["id"]))
        elif etype == "claim":
            for attr in ("number", "coverage_kind", "status", "amount_claimed",
                         "year", "cause"):
                facts.add((etype, eid, attr, props[attr]))
            facts.add((etype, eid, "filed_against", props["policy_id"]))
            adj = json.loads(props["adjuster"])
            facts.add((etype, eid, "assessed_by", adj["id"]))
            facts.add(("adjuster", adj["id"], "name", adj["name"]))
            facts.add(("adjuster", adj["id"], "seniority", adj["seniority"]))
            facts.add(("adjuster", adj["id"], "works_in", adj["region"]["id"]))
            facts.add(("region", adj["region"]["id"], "name",
                       adj["region"]["name"]))
            prov = json.loads(props["provider"])
            if prov:
                facts.add((etype, eid, "repaired_at", prov["id"]))
                facts.add(("provider", prov["id"], "name", prov["name"]))
                facts.add(("provider", prov["id"], "specialty",
                           prov["specialty"]))
                facts.add(("provider", prov["id"], "located_in",
                           prov["region"]["id"]))
                facts.add(("region", prov["region"]["id"], "name",
                           prov["region"]["name"]))
            for pay in json.loads(props["payments"]):
                for attr in ("amount", "year", "method"):
                    facts.add(("payment", pay["id"], attr, pay[attr]))
                facts.add(("payment", pay["id"], "settles", eid))
    return facts


# ------------------------------------------------------------ normalized ----

def build_normalized(data: dict) -> dict:
    """Full reification: entities are bare Resource nodes, every attribute is
    an Attribute node reached by a generic has edge, every relationship is a
    Relation node with subject and object edges. Four hops to learn anything -
    and not one fact more or less than the other two variants.

    This builder works from the canonical fact set rather than the entity
    lists, because reification is a mechanical transform of triples: every
    fact becomes either an Attribute node or a Relation node, with no
    knowledge of the domain required.

    One honest consequence: because this encodes the fact set directly and
    reconstruct_normalized decodes it, their round trip is close to an
    identity and cannot fail except on an encode/decode asymmetry. The flat
    and shaped builders are written independently of canonical_facts, so
    their checks are substantive; this one is better described as lossless
    by construction."""
    nodes, edges = {}, []

    def resource(etype, eid):
        nodes[nid(etype, eid)] = {"type": "Resource",
                                  "props": {"entity_type": etype}}

    def attribute(etype, eid, attr, value):
        aid = f"{nid(etype, eid)}#{attr}"
        nodes[aid] = {"type": "Attribute", "props": {"attr": attr, "value": value}}
        edges.append({"src": nid(etype, eid), "type": "has", "dst": aid,
                      "props": {}})

    def relation(setype, seid, kind, detype, deid):
        rid = f"rel:{nid(setype, seid)}:{kind}:{nid(detype, deid)}"
        nodes[rid] = {"type": "Relation", "props": {"kind": kind}}
        edges.append({"src": rid, "type": "subject", "dst": nid(setype, seid),
                      "props": {}})
        edges.append({"src": rid, "type": "object", "dst": nid(detype, deid),
                      "props": {}})

    # sorted, because canonical_facts returns a set and set iteration order
    # varies with PYTHONHASHSEED. Without this the emitted edge list differs
    # between processes, the committed graph stops being reproducible, and the
    # neighbour order the agent traverses changes from run to run.
    plain = sorted(canonical_facts(data))
    seen_entities = set()
    for etype, eid, attr, value in plain:
        if (etype, eid) not in seen_entities:
            resource(etype, eid)
            seen_entities.add((etype, eid))
    for etype, eid, attr, value in plain:
        if (etype, attr) in RELATION_ATTRS:
            relation(etype, eid, attr, RELATION_TARGET[attr], value)
        else:
            attribute(etype, eid, attr, value)
    return {"variant": "normalized", "nodes": nodes, "edges": edges}


def reconstruct_normalized(graph: dict) -> set:
    facts = set()
    subjects, objects = {}, {}
    for edge in graph["edges"]:
        if edge["type"] == "subject":
            subjects[edge["src"]] = edge["dst"]
        elif edge["type"] == "object":
            objects[edge["src"]] = edge["dst"]
        elif edge["type"] == "has":
            etype, eid = edge["src"].split(":", 1)
            attr_node = graph["nodes"][edge["dst"]]
            facts.add((etype, eid, attr_node["props"]["attr"],
                       attr_node["props"]["value"]))
    for rel_id, rec in graph["nodes"].items():
        if rec["type"] != "Relation":
            continue
        setype, seid = subjects[rel_id].split(":", 1)
        _, deid = objects[rel_id].split(":", 1)
        facts.add((setype, seid, rec["props"]["kind"], deid))
    return facts


# ------------------------------------------------------------------ main ----

BUILDERS = {
    "flat": (build_flat, reconstruct_flat),
    "normalized": (build_normalized, reconstruct_normalized),
    "shaped": (build_shaped, reconstruct_shaped),
}


def main() -> None:
    data = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    for name, (build, _) in BUILDERS.items():
        graph = build(data)
        out = DATA_DIR / f"ontology-{name}.json"
        out.write_text(json.dumps(graph, indent=1, sort_keys=True) + "\n",
                       encoding="utf-8")
        print(f"{out.name}: {len(graph['nodes'])} nodes, "
              f"{len(graph['edges'])} edges")


if __name__ == "__main__":
    main()
