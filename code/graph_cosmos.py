"""The four tools, backed by Azure Cosmos DB for Apache Gremlin.

This is what the measured campaigns run against: every tool call the agent
makes is a Gremlin query to a live graph database. All three ontologies sit in
the same account under the same tool layer, so the store is held constant and
the ontology's shape stays the only variable.

It implements exactly the same tool contract as graph.py - same names, same
arguments, same caps, same response shape - over Gremlin instead of a dict.
Keeping the two interchangeable is what lets equivalence_check.py replay real
tool calls against both and confirm the engine underneath is not quietly
changing the answers the agent sees.

Environment: COSMOS_GREMLIN_ENDPOINT, COSMOS_GREMLIN_KEY.
"""

from __future__ import annotations

import json
import os
import time
from typing import List

from graph import FIND_CAP, TRAVERSE_CAP
from load_cosmos import DATABASE, cosmos_id

# Cosmos ids swap '#' for '~'; every vertex keeps the original in source_id,
# so the tools can speak the JSON layer's vocabulary in and out.
SOURCE_ID = "source_id"


def _q(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


class CosmosGraph:
    """Duck-compatible with graph.Graph for the four tool methods."""

    def __init__(self, variant: str):
        from gremlin_python.driver import client as gremlin_client
        from gremlin_python.driver import serializer

        endpoint = os.environ.get("COSMOS_GREMLIN_ENDPOINT", "")
        key = os.environ.get("COSMOS_GREMLIN_KEY", "")
        if not endpoint or not key:
            raise SystemExit(
                "set COSMOS_GREMLIN_ENDPOINT and COSMOS_GREMLIN_KEY")
        self.variant = variant
        self._client = gremlin_client.Client(
            endpoint, "g",
            username=f"/dbs/{DATABASE}/colls/{variant}",
            password=key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )

    def close(self) -> None:
        self._client.close()

    def _submit(self, query: str, attempts: int = 4) -> list:
        """Retry transient Cosmos failures. Serverless throttles under load,
        and a campaign is thousands of sequential queries: without this, one
        429 three hours in would end the run and take the whole grid with it.
        A persistent failure still raises, because a silently wrong tool
        answer would be far worse than a stopped campaign."""
        for attempt in range(attempts):
            try:
                return self._client.submit(query).all().result()
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(1.0 * (attempt + 1))

    # ------------------------------------------------------------- helpers --

    @staticmethod
    def _props(raw: dict) -> dict:
        """GraphSON valueMap gives {key: [value]}; flatten and drop the
        bookkeeping properties the JSON layer never had."""
        out = {}
        for key, value in raw.items():
            if key in ("id", "label", "pk", SOURCE_ID):
                continue
            out[key] = value[0] if isinstance(value, list) and value else value
        return out

    def _label_of(self, raw: dict) -> str:
        return raw.get("label", "")

    def _source_id(self, raw: dict) -> str:
        value = raw.get(SOURCE_ID, raw.get("id"))
        if isinstance(value, list) and value:
            value = value[0]
        return str(value)

    @staticmethod
    def _label_for_props(props: dict, node_id: str) -> str:
        for key in ("name", "number", "attr", "kind", "entity_type"):
            if key in props:
                if key == "attr":
                    return f"{props['attr']}={props.get('value')}"
                return str(props[key])
        return node_id

    # --------------------------------------------------------------- tools --

    def find_nodes(self, query: str, node_type: str = "") -> dict:
        """Substring match over properties and id, exactly as graph.py does.

        Gremlin has no case-insensitive contains across arbitrary properties,
        so the scan happens here: the shapes are small, and matching the JSON
        layer's semantics exactly matters more than pushing work down.
        """
        needle = str(query).lower()
        clause = f".hasLabel({_q(node_type)})" if node_type else ""
        rows = self._submit(f"g.V(){clause}.valueMap(true)")
        hits = []
        for raw in rows:
            props = self._props(raw)
            node_id = self._source_id(raw)
            haystack = json.dumps(props).lower()
            if needle in haystack or needle in node_id.lower():
                hits.append({"id": node_id,
                             "type": self._label_of(raw),
                             "label": self._label_for_props(props, node_id)})
        hits.sort(key=lambda h: h["id"])
        return {"total_matches": len(hits), "returned": len(hits[:FIND_CAP]),
                "nodes": hits[:FIND_CAP]}

    def get_node(self, node_id: str) -> dict:
        rows = self._submit(f"g.V({_q(cosmos_id(node_id))}).valueMap(true)")
        if not rows:
            return {"error": f"no node with id {node_id!r}"}
        return {"id": node_id, "type": self._label_of(rows[0]),
                "props": self._props(rows[0])}

    def traverse(self, node_id: str, edge_type: str = "",
                 direction: str = "any") -> dict:
        exists = self._submit(f"g.V({_q(cosmos_id(node_id))}).count()")[0]
        if not exists:
            return {"error": f"no node with id {node_id!r}"}
        hits: List[dict] = []
        for way in ("out", "in"):
            if direction not in (way, "any"):
                continue
            step = "outE" if way == "out" else "inE"
            other = "inV" if way == "out" else "outV"
            filt = f".hasLabel({_q(edge_type)})" if edge_type else ""
            rows = self._submit(
                f"g.V({_q(cosmos_id(node_id))}).{step}(){filt}"
                f".project('etype','node')"
                f".by(label).by({other}().valueMap(true))")
            for row in rows:
                raw = row["node"]
                nid = self._source_id(raw)
                hits.append({"edge_type": row["etype"], "direction": way,
                             "node_id": nid,
                             "node_type": self._label_of(raw),
                             "label": self._label_for_props(
                                 self._props(raw), nid)})
        return {"total_neighbours": len(hits),
                "returned": len(hits[:TRAVERSE_CAP]),
                "neighbours": hits[:TRAVERSE_CAP]}

    def describe_edges(self, node_id: str) -> dict:
        exists = self._submit(f"g.V({_q(cosmos_id(node_id))}).count()")[0]
        if not exists:
            return {"error": f"no node with id {node_id!r}"}
        summary = {}
        for way, step in (("out", "outE"), ("in", "inE")):
            rows = self._submit(
                f"g.V({_q(cosmos_id(node_id))}).{step}().groupCount().by(label)")
            for etype, count in (rows[0] if rows else {}).items():
                summary[(etype, way)] = summary.get((etype, way), 0) + count
        return {"edges": [{"edge_type": t, "direction": d, "count": n}
                          for (t, d), n in sorted(summary.items())]}
