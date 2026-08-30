"""The traversal agent: one model, four tools, no other way to the answer.

The scaffolding is deliberately minimal and IDENTICAL across ontologies and
models: a plain function-calling loop against a Microsoft Foundry deployment.
The agent never sees the graph itself, only what the four tools return, and the
transcript of tool calls IS the experiment's receipt - every answer arrives
with the path that produced it.

This module owns the model SDK. Two others reach the network - graph_cosmos.py
and load_cosmos.py, which speak Gremlin to Cosmos - and everything else runs
offline with the standard library alone.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from graph import TOOL_SPECS, dispatch

API_VERSION = "2024-10-21"
MAX_STEPS = 16
NOT_MODELED = "NOT_MODELED"

SYSTEM_PROMPT = """You answer questions about an insurance knowledge graph.

You can only learn facts by calling the four graph tools. Never guess and
never use outside knowledge: if the graph does not model the fact needed to
answer, reply with exactly ANSWER: NOT_MODELED.

Work step by step: find an entry node, inspect it, traverse edges, and stop as
soon as you can answer. Some properties contain JSON encoded text; read it
carefully. When aggregating, be exhaustive: check every relevant node before
answering.

When you know the answer, reply on a single line:
ANSWER: <the answer>

Give only the value asked for - a name, a number, a word - with no extra
commentary. For monetary amounts give a plain number without currency symbols.
"""


def build_client(endpoint: str, api_key: str = ""):
    from openai import AzureOpenAI

    if api_key:
        return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key,
                           api_version=API_VERSION)
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(azure_endpoint=endpoint,
                       azure_ad_token_provider=provider,
                       api_version=API_VERSION)


def client_from_env():
    endpoint = os.environ.get("ONTOLOGY_AGENTS_ENDPOINT", "")
    if not endpoint:
        raise SystemExit("set ONTOLOGY_AGENTS_ENDPOINT (and optionally "
                         "AZURE_OPENAI_API_KEY, or use az login)")
    return build_client(endpoint, os.environ.get("AZURE_OPENAI_API_KEY", ""))


@dataclass
class Step:
    tool: str
    arguments: dict
    result_chars: int


@dataclass
class RunResult:
    question_id: str
    variant: str
    deployment: str
    steps: List[Step] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    final_text: str = ""
    answer: Optional[str] = None
    hit_step_cap: bool = False

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id, "variant": self.variant,
            "deployment": self.deployment,
            "tool_calls": len(self.steps),
            "steps": [{"tool": s.tool, "arguments": s.arguments,
                       "result_chars": s.result_chars} for s in self.steps],
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_s": round(self.latency_s, 3),
            "final_text": self.final_text, "answer": self.answer,
            "hit_step_cap": self.hit_step_cap,
        }


def extract_answer(text: str) -> Optional[str]:
    for line in reversed(text.splitlines()):
        if line.strip().upper().startswith("ANSWER:"):
            return line.strip()[len("ANSWER:"):].strip()
    return None


def run_question(client, deployment: str, graph, question: dict,
                 max_steps: int = MAX_STEPS) -> RunResult:
    """Run one episode. `graph` is any object exposing the four tools -
    graph.Graph over the generator's files, or graph_cosmos.CosmosGraph over
    Cosmos DB; the agent cannot tell which it is holding."""
    tools = [{"type": "function", "function": spec} for spec in TOOL_SPECS]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question["question"]},
    ]
    result = RunResult(question_id=question["id"], variant=graph.variant,
                       deployment=deployment)
    t0 = time.perf_counter()
    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=deployment, messages=messages, tools=tools)
        usage = response.usage
        result.input_tokens += usage.prompt_tokens
        result.output_tokens += usage.completion_tokens
        message = response.choices[0].message
        if not message.tool_calls:
            result.final_text = message.content or ""
            result.answer = extract_answer(result.final_text)
            break
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ],
        })
        for tc in message.tool_calls:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            payload = dispatch(graph, tc.function.name, arguments)
            encoded = json.dumps(payload)
            result.steps.append(Step(tool=tc.function.name,
                                     arguments=arguments,
                                     result_chars=len(encoded)))
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": encoded})
    else:
        result.hit_step_cap = True
        result.final_text = ""
    result.latency_s = time.perf_counter() - t0
    return result


def score(question: dict, answer: Optional[str]) -> bool:
    """Deterministic scoring against the computed oracle answer.

    Numbers must match to within a cent; strings must contain the expected
    value. Containment is deliberately lenient about wrapping ("ANSWER: the
    adjuster was Elsa Duval" counts), which in principle could accept a
    negated or padded answer. It did not: across all 960 episodes of the
    published campaigns, no accepted answer was longer than the expected value
    itself, so no verdict in the results depended on that leniency. The rule is
    kept exactly as it ran rather than tightened afterwards, so that the shipped
    code reproduces the shipped results.
    """
    if answer is None:
        return False
    expected = question["answer"]
    if question["band"] == "U":
        return NOT_MODELED.lower() in answer.lower()
    if question["answer_type"] == "number":
        cleaned = answer.replace(",", "").replace("$", "").strip()
        token = cleaned.split()[0] if cleaned.split() else ""
        try:
            return abs(float(token) - float(expected)) < 0.01
        except ValueError:
            return False
    return str(expected).lower() in answer.lower()
