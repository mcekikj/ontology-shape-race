"""Take the winning ontology apart: derive the ablation variants.

Article 3 measured three shapes and shaped won. But "shaped" bundles two
design decisions - a domain VOCABULARY (typed vertices, named edges) and a
GEOMETRY (ninety derived held_by shortcuts) - and the follow-up experiment
separates them. Each variant here is a mechanical transform of the committed
shaped graph, not a redesign: nothing is rebuilt from the facts, nothing is
tuned, and the transforms are invertible, which is what verify_ablations.py
proves.

    variant        vocabulary   shortcuts   transform
    shaped         domain       kept        (the article-3 baseline, as is)
    shaped-minus   domain       removed     drop edges flagged derived
    shaped-anon    anonymous    kept        rename types, edges and id
                                            prefixes to type_N / rel_N
    shaped-bare    anonymous    removed     both transforms

The anonymisation renames everything the tool surface shows the agent:
vertex types (get_node, find_nodes, traverse), edge names (traverse,
describe_edges) and the type prefix of every node id, because ids like
`claim:CL-021` appear in every tool response and would hand the vocabulary
straight back. Property keys and values are untouched: the facts are the
experiment's constant, and data that smells like what it is biases the test
AGAINST finding a vocabulary effect, not toward one.

The mapping is not configured anywhere - it is derived from the graph by
sorted order, so it is deterministic, and it is embedded in each output
file under "mapping" so the artifact documents itself.

Output: data/ontology-shaped-{minus,anon,bare}.json
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_shaped() -> dict:
    return json.loads(
        (DATA_DIR / "ontology-shaped.json").read_text(encoding="utf-8"))


def vocabulary_mapping(graph: dict) -> dict:
    """type_N / rel_N names for the graph's types and edges, by sorted order."""
    types = sorted({rec["type"] for rec in graph["nodes"].values()})
    rels = sorted({edge["type"] for edge in graph["edges"]})
    return {
        "types": {t: f"type_{i}" for i, t in enumerate(types, 1)},
        "edges": {r: f"rel_{i}" for i, r in enumerate(rels, 1)},
    }


def rename_id(node_id: str, types: dict) -> str:
    """`claim:CL-021` -> `type_2:CL-021`. Every shaped id is `type:eid`."""
    prefix, eid = node_id.split(":", 1)
    return f"{types[prefix]}:{eid}"


def drop_shortcuts(graph: dict) -> dict:
    """Remove the derived edges - geometry off, vocabulary untouched.

    The losslessness reconstructor already skips edges flagged derived, so
    this provably removes reachability, never knowledge.
    """
    return {
        "variant": graph["variant"] + "-minus",
        "nodes": graph["nodes"],
        "edges": [e for e in graph["edges"] if not e["props"].get("derived")],
    }


def anonymize(graph: dict) -> dict:
    """Rename the schema's self-description - vocabulary off, geometry
    untouched. Invertible by construction; verify_ablations.py round-trips
    it against the input byte for byte."""
    mapping = vocabulary_mapping(graph)
    types, rels = mapping["types"], mapping["edges"]
    nodes = {rename_id(node_id, types): {"type": types[rec["type"]],
                                         "props": rec["props"]}
             for node_id, rec in graph["nodes"].items()}
    edges = [{"src": rename_id(e["src"], types),
              "dst": rename_id(e["dst"], types),
              "type": rels[e["type"]],
              "props": e["props"]}
             for e in graph["edges"]]
    return {"variant": graph["variant"] + "-anon", "nodes": nodes,
            "edges": edges, "mapping": mapping}


def deanonymize(graph: dict) -> dict:
    """The inverse transform - the proof machinery's way back."""
    types = {v: k for k, v in graph["mapping"]["types"].items()}
    rels = {v: k for k, v in graph["mapping"]["edges"].items()}
    nodes = {rename_id(node_id, types): {"type": types[rec["type"]],
                                         "props": rec["props"]}
             for node_id, rec in graph["nodes"].items()}
    edges = [{"src": rename_id(e["src"], types),
              "dst": rename_id(e["dst"], types),
              "type": rels[e["type"]],
              "props": e["props"]}
             for e in graph["edges"]]
    return {"variant": graph["variant"].rsplit("-", 1)[0], "nodes": nodes,
            "edges": edges}


ABLATIONS = {
    "shaped-minus": lambda g: drop_shortcuts(g),
    "shaped-anon": lambda g: anonymize(g),
    "shaped-bare": lambda g: {**anonymize(drop_shortcuts(g)),
                              "variant": "shaped-bare"},
}


def main() -> None:
    shaped = load_shaped()
    for name, transform in ABLATIONS.items():
        graph = transform(shaped)
        graph["variant"] = name
        out = DATA_DIR / f"ontology-{name}.json"
        out.write_text(json.dumps(graph, indent=1, sort_keys=True) + "\n",
                       encoding="utf-8")
        print(f"{out.name}: {len(graph['nodes'])} nodes, "
              f"{len(graph['edges'])} edges")


if __name__ == "__main__":
    main()
