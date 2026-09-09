# Author: Maharshi Soni | License: MIT
"""Graph engine implementing LangGraph-style node/edge/conditional routing.

This module provides a lightweight, framework-free graph execution engine that
mirrors the LangGraph architecture: named nodes, directed edges, conditional
routing functions, and a shared state that flows through the pipeline.

The graph compiles into an executable runner that processes nodes in topological
order, evaluating conditional edges at each transition to decide the next node.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.state import AgentState, NodeName

logger = logging.getLogger(__name__)

# Type aliases
NodeFunction = Callable[[AgentState], AgentState]
ConditionalRouter = Callable[[AgentState], NodeName]


class GraphNode:
    """A named node in the execution graph."""

    def __init__(self, name: NodeName, func: NodeFunction) -> None:
        self.name = name
        self.func = func

    def execute(self, state: AgentState) -> AgentState:
        """Run this node's function with the given state."""
        logger.info("Executing node: %s", self.name.value)
        state.current_node = self.name
        return self.func(state)


class Edge:
    """A directed edge connecting two nodes."""

    def __init__(self, source: NodeName, target: NodeName) -> None:
        self.source = source
        self.target = target


class ConditionalEdge:
    """An edge that routes to different targets based on state evaluation."""

    def __init__(
        self,
        source: NodeName,
        router: ConditionalRouter,
        route_map: Dict[NodeName, NodeName],
    ) -> None:
        self.source = source
        self.router = router
        self.route_map = route_map

    def resolve(self, state: AgentState) -> NodeName:
        """Evaluate the routing function and return the next node."""
        decision = self.router(state)
        resolved = self.route_map.get(decision, decision)
        logger.info(
            "Conditional edge from %s resolved to %s",
            self.source.value,
            resolved.value,
        )
        return resolved


class GraphBuilder:
    """Builder for constructing the agent execution graph.

    Usage::

        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, planner_func)
        builder.add_node(NodeName.TEST_EXECUTOR, executor_func)
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.TEST_EXECUTOR)
        builder.add_conditional_edge(
            NodeName.TEST_EXECUTOR,
            my_router,
            {NodeName.BUG_ANALYZER: NodeName.BUG_ANALYZER, ...}
        )
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()
        final_state = graph.run(initial_state)
    """

    def __init__(self) -> None:
        self._nodes: Dict[NodeName, GraphNode] = {}
        self._edges: List[Edge] = []
        self._conditional_edges: Dict[NodeName, ConditionalEdge] = {}
        self._entry_point: Optional[NodeName] = None

    def add_node(self, name: NodeName, func: NodeFunction) -> "GraphBuilder":
        """Register a node with its processing function."""
        self._nodes[name] = GraphNode(name, func)
        return self

    def add_edge(self, source: NodeName, target: NodeName) -> "GraphBuilder":
        """Add a fixed directed edge between two nodes."""
        self._edges.append(Edge(source, target))
        return self

    def add_conditional_edge(
        self,
        source: NodeName,
        router: ConditionalRouter,
        route_map: Dict[NodeName, NodeName],
    ) -> "GraphBuilder":
        """Add a conditional edge that routes based on state evaluation."""
        self._conditional_edges[source] = ConditionalEdge(source, router, route_map)
        return self

    def set_entry_point(self, name: NodeName) -> "GraphBuilder":
        """Set which node the graph begins execution at."""
        self._entry_point = name
        return self

    def compile(self) -> "CompiledGraph":
        """Compile the builder into an executable graph."""
        if self._entry_point is None:
            raise ValueError("Entry point must be set before compiling.")
        if self._entry_point not in self._nodes:
            raise ValueError(
                f"Entry point '{self._entry_point.value}' is not a registered node."
            )
        # Build adjacency: fixed edges take lower priority than conditional edges
        fixed_next: Dict[NodeName, NodeName] = {}
        for edge in self._edges:
            fixed_next[edge.source] = edge.target

        return CompiledGraph(
            nodes=dict(self._nodes),
            fixed_next=fixed_next,
            conditional_edges=dict(self._conditional_edges),
            entry_point=self._entry_point,
        )


class CompiledGraph:
    """An executable graph ready to process state through its nodes."""

    def __init__(
        self,
        nodes: Dict[NodeName, GraphNode],
        fixed_next: Dict[NodeName, NodeName],
        conditional_edges: Dict[NodeName, ConditionalEdge],
        entry_point: NodeName,
    ) -> None:
        self.nodes = nodes
        self.fixed_next = fixed_next
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self._max_iterations = 50  # safety limit to prevent infinite loops

    def _resolve_next(self, current: NodeName, state: AgentState) -> NodeName:
        """Determine the next node given the current node and state.

        Conditional edges are checked first; if none match, fall back to
        the fixed edge table; if nothing is found, go to END.
        """
        if current in self.conditional_edges:
            return self.conditional_edges[current].resolve(state)
        if current in self.fixed_next:
            return self.fixed_next[current]
        return NodeName.END

    def run(self, state: AgentState) -> AgentState:
        """Execute the graph from the entry point until reaching END.

        Returns the final state after all nodes have been processed.
        """
        current = self.entry_point
        iterations = 0

        logger.info("=== Graph execution started (run_id=%s) ===", state.run_id)

        while current != NodeName.END and iterations < self._max_iterations:
            iterations += 1
            node = self.nodes.get(current)
            if node is None:
                logger.error("Node '%s' not found in graph. Halting.", current.value)
                state.errors.append(f"Missing node: {current.value}")
                break

            try:
                state = node.execute(state)
            except Exception as exc:
                logger.exception("Node '%s' raised an exception.", current.value)
                state.errors.append(f"Node {current.value} error: {exc}")
                break

            next_node = self._resolve_next(current, state)
            logger.info(
                "Transition: %s -> %s", current.value, next_node.value
            )
            current = next_node

        if iterations >= self._max_iterations:
            logger.warning("Graph hit max iteration limit (%d).", self._max_iterations)
            state.errors.append("Max iteration limit reached.")

        logger.info("=== Graph execution completed ===")
        return state

    def get_node_names(self) -> List[str]:
        """Return a sorted list of all node names in the graph."""
        return sorted(n.value for n in self.nodes)

    def get_edges(self) -> List[Tuple[str, str]]:
        """Return all fixed edges as (source, target) tuples."""
        return [(s.value, t.value) for s, t in self.fixed_next.items()]

    def get_conditional_edge_sources(self) -> List[str]:
        """Return names of nodes that have conditional outgoing edges."""
        return [n.value for n in self.conditional_edges]
