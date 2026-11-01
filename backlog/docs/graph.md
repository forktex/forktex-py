# forktex.graph

Pure in-memory typed multi-edge graph: Pydantic `Graph`/`GraphNode`/`GraphEdge` models with
deterministic edge ids, lazy adjacency indices, and BFS/DFS/closure/shortest-path/cycle algorithms
plus subgraph extraction. No I/O, no persistence, no backend.

## Install

```bash
pip install forktex
```

No extra required. Depends only on the standard library, `pydantic` and `forktex.error`.

## Wiring

A `Graph` is an ordinary value you construct, mutate and pass around. No registry, no `init()`.

```python
from forktex.graph import Graph, GraphNode, shortest_path, transitive_closure

g = Graph.empty()
for nid in ("a", "b", "c"):
    g.add_node(GraphNode(id=nid, kind="n"))
g.add_edge("k", "a", "b")
g.add_edge("k", "b", "c")

assert transitive_closure(g, "a") == {"a", "b", "c"}
assert shortest_path(g, "a", "c") == ["a", "b", "c"]

payload = g.sorted().model_dump_json()      # byte-stable snapshot
g2 = Graph.model_validate_json(payload)
```

`kind` is a free-form `str` on both nodes and edges; each consumer brings its own vocabulary.

## Public surface

```python
from forktex.graph import (
    EdgeKind,
    Graph,
    GraphEdge,
    GraphNode,
    InvalidDirectionError,
    NodeKind,
    NodeNotFoundError,
    bfs,
    cycles,
    dfs,
    edge_id,
    induced_subgraph,
    shortest_path,
    subgraph_around,
    transitive_closure,
)
```

| Name | Description |
|---|---|
| `Graph` | Pydantic model holding `meta`, `nodes`, `edges` plus private adjacency indices. |
| `GraphNode` | `id`, `kind`, `name`, `attrs`. |
| `GraphEdge` | `id`, `kind`, `src_id`, `dst_id`, `attrs`. |
| `NodeKind` / `EdgeKind` | Aliases for `str`, exported so consumers can narrow them. |
| `edge_id(kind, src_id, dst_id, attrs=None)` | `"<kind>:<src>-><dst>:<8hex>"`, blake2s over canonical-JSON attrs. |
| `bfs(graph, start_id, *, edge_kind=None, direction="out")` | Visited ids in BFS order, `start_id` first. |
| `dfs(...)` | Same signature; DFS pre-order. Recursive. |
| `transitive_closure(...)` | `set[str]` of ids reachable from `start_id`, inclusive. |
| `shortest_path(graph, src_id, dst_id, *, edge_kind=None, direction="out")` | Unweighted path as a list of ids, or `None`. |
| `cycles(graph, *, edge_kind=None)` | Tarjan SCC — one entry per cyclic component, plus self-loops as size-1 cycles. |
| `induced_subgraph(graph, node_ids)` | Those nodes plus every edge with both endpoints kept. Deep-copied. |
| `subgraph_around(graph, start_id, *, max_depth=1, edge_kind=None, direction="both")` | Layered BFS radius, then induced. |
| `NodeNotFoundError` | `NotFoundError` + `KeyError`, code `NOT_FOUND`. |
| `InvalidDirectionError` | `BadRequestError` + `ValueError`, code `BAD_REQUEST`. |

`Graph` methods: `add_node`, `add_edge`, `node`, `has_node`, `out_edges`, `in_edges`, `neighbors`,
`by_kind`, `edges_by_kind`, `sorted`, `merge`, and the classmethods `empty` and `from_iterables`.
`GraphMeta` (`name`, `generated_at`, `schema_version`) is reachable at `forktex.graph.models` but
is not in the package `__all__`:

```python
from forktex.graph.models import GraphMeta

g = Graph.empty(GraphMeta(name="org-chart"))
```

Constrain a traversal with `edge_kind` rather than pre-building a filtered copy:

```python
reached = transitive_closure(g, "alice", edge_kind="works_at")
```

## Errors

Both errors subclass `AppError` *and* the plain-Python exception callers already catch.

| Raised | When | Catch? |
|---|---|---|
| `NodeNotFoundError` | `add_edge()` where `src_id` or `dst_id` is not already a node. | Yes, if you build edges from untrusted input. |
| `InvalidDirectionError` | `direction=` anything but `"out"`, `"in"`, `"both"`, in `neighbors` or any algorithm forwarding it. | No — a programming error. |

Nothing else raises; an unknown id returns an empty result.

## Gotchas

- **`add_node` is a lookup, not an upsert.** With a duplicate id it returns the *existing* node and
  discards the argument, so field updates in the second call are silently lost. Mutate `attrs` on
  the returned node instead.
- **`add_edge` collapses on `(kind, src_id, dst_id, attrs)`.** Differ on any one of those and both
  edges coexist between the same pair — that is the multi-edge behaviour. Identical tuples return
  the existing edge.
- **`add_edge` requires both endpoints to exist**; ordering matters when building from a stream.
- **Edge ids depend on `attrs` content**, hashed as `json.dumps(attrs, sort_keys=True,
  default=str)`. A `datetime` and its string render alike, and mutating `attrs` after insertion
  desynchronises the edge from its id.
- **Direct list mutation does not invalidate the adjacency index.** Only `add_node`/`add_edge`
  keep it in sync, so appending to `g.nodes` or `g.edges` yourself leaves lookups stale.
- **`dfs` is recursive** and will hit Python's recursion limit on a deep chain. `bfs` is iterative.
  `cycles` is also recursive (Tarjan).
- **`shortest_path` is unweighted**; encode weights in `attrs` and run your own Dijkstra.
- **`cycles` returns one representative per cyclic SCC**, not every simple cycle, and the node order
  within a component is Tarjan's stack-pop order, not a traversal order.
- **`sorted()`, `merge()` and `induced_subgraph()` deep-copy** nodes and edges; `sorted()` carries
  `meta` over by reference.
- **`merge()` mutates the receiver** and keeps the receiver's `meta`; it returns `self`, not a new
  graph.
- **`subgraph_around` with an unknown `start_id`** returns an empty `Graph` carrying the source's
  `meta`; `max_depth <= 0` returns just the start node.
- **`induced_subgraph` silently drops ids** that are not in the graph.
