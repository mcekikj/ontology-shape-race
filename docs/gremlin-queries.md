# Gremlin queries for the three ontologies

The three shapes live in one Cosmos DB for Apache Gremlin account, database
`ontologies`, one graph per shape: `flat`, `normalized`, `shaped`. They are
loaded by `code/load_cosmos.py` from the fact base the
generator produces.

Two things to know before running anything:

- These graphs are what the measured campaigns query. Every tool call the
  agent makes during a campaign is a Gremlin query against one of these three
  containers.
- Vertex ids match the generator's node ids, except that `#` becomes `~`,
  because Cosmos item ids may not contain `#`. Every vertex also carries
  `source_id` with the untouched original.
- Properties are stored verbatim, including the flat graph's long JSON-string
  properties. An earlier version truncated them for portal readability, which
  quietly made the store differ from the source; `equivalence_check.py` caught
  it and the truncation was removed.

## The comparison that makes the article's point

Run the same conceptual question against each graph and count the hops. The
question: **who holds the policy that claim C-31020 was filed against, and
what city do they live in?**

### shaped - two hops, and the shortcut makes it one

```gremlin
g.V().has('number', 'C-31020').out('held_by').values('name', 'city')
```

The derived shortcut goes straight from claim to policyholder. Without it,
the honest path is still short:

```gremlin
g.V().has('number', 'C-31020').out('filed_against').out('held_by').values('city')
```

### flat - the claim is a node, the policy is not

```gremlin
g.V().has('number', 'C-31020').in('related').values('name', 'city')
```

It works, but notice what you cannot do: there is no `policy` label to query
at all. Try it and you get nothing back:

```gremlin
g.V().hasLabel('policy').count()
```

Run that same line against all three graphs and it is the article's central
finding in one result:

| graph | result | why |
|---|---|---|
| `flat` | **0** | policies are not nodes; they are text inside a property |
| `normalized` | **0** | policies *are* nodes, but every node is labelled `Resource` |
| `shaped` | **75** | a policy is a policy |

The two zeros mean different things, and that difference is the article's
"two failing shapes each got one half right". The flat graph lost the entity.
The normalized graph kept the entity and lost the vocabulary - you can reach a
policy, but only by walking to it, never by naming it.

### normalized - everything is reachable, nothing is close

```gremlin
g.V().has('value', 'C-31020').in('has')
     .in('subject').has('kind', 'filed_against').out('object')
     .in('subject').has('kind', 'held_by').out('object')
     .out('has').has('attr', 'city').values('value')
```

Same answer. Five traversal steps and two attribute unwrappings to reach a
fact the shaped graph hands over in one hop.

## Shape at a glance

Node-type distribution, which is the whole design in one result:

```gremlin
g.V().groupCount().by(label)
```

Verified output, 2026-08-29:

- `flat`: `{claim: 90, policyholder: 40}` - two labels, and the other six
  entity kinds exist only as text inside properties
- `normalized`: `{Resource: 507, Attribute: 1834, Relation: 601}` - every one
  of the 507 entities is present and reachable, and not one of them says what
  it is
- `shaped`: `{claim: 90, policy: 75, coverage: 216, policyholder: 40,
  payment: 59, provider: 12, adjuster: 10, region: 5}` - the domain, in the
  domain's own words

Edge-type distribution:

```gremlin
g.E().groupCount().by(label)
```

- `flat`: `{related: 90}` - one type, and it says nothing
- `normalized`: `{has: 1834, subject: 601, object: 601}` - three, all
  structural
- `shaped`: nine named types - `on_policy: 216`, `held_by: 165` (75 real plus
  the 90 derived shortcuts), `assessed_by: 90`, `filed_against: 90`,
  `settles: 59`, `repaired_at: 28`, `renewed_from: 21`, `located_in: 12`,
  `works_in: 10`

Counts, to confirm the store matches the committed JSON:

```gremlin
g.V().count()
g.E().count()
```

Expected: flat 130 / 90, shaped 507 / 691, normalized 2,942 / 3,036.

## Neighbourhood queries for the screenshots

These are scoped deliberately: the portal's graph explorer cannot usefully
draw 2,942 nodes, and the point is not size but shape. One claim and its
immediate surroundings shows the contrast honestly.

```gremlin
// shaped - a claim and everything one hop away
g.V().has('number', 'C-31020').bothE().otherV().path()

// flat - the same claim; almost nothing is connected
g.V().has('number', 'C-31020').bothE().otherV().path()

// normalized - the claim's entity vertex and its immediate attribute vertices
g.V().has('value', 'C-31020').in('has').bothE().otherV().path()
```

## The buried policy

The article's trace block turns on policy P-7009. These queries show why the
agent could find it in one graph and not the other.

```gremlin
// shaped - the policy is a vertex with the number on it
g.V().has('number', 'P-7009').valueMap(true)

// flat - no such vertex; the number lives inside a policyholder's property
g.V().has('number', 'P-7009').count()          // returns 0
g.V().hasLabel('policyholder').has('policies', containing('P-7009'))
     .values('name')                            // returns "Ivo Renner"
```

That second pair is the finding: the same search that returns the policy in
the shaped graph returns a person's name in the flat one.
