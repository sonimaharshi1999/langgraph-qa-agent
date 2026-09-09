# Author: Maharshi Soni | License: MIT
"""Tests for core.graph module."""

import pytest

from core.graph import CompiledGraph, ConditionalEdge, Edge, GraphBuilder, GraphNode
from core.state import AgentState, NodeName


def _node_a(state: AgentState) -> AgentState:
    """Test node that appends 'A' to errors list (used as a trace)."""
    state.errors.append("A")
    return state


def _node_b(state: AgentState) -> AgentState:
    """Test node that appends 'B'."""
    state.errors.append("B")
    return state


def _node_c(state: AgentState) -> AgentState:
    """Test node that appends 'C'."""
    state.errors.append("C")
    return state


class TestGraphNode:
    """Tests for GraphNode."""

    def test_execute(self):
        node = GraphNode(NodeName.TEST_PLANNER, _node_a)
        state = AgentState()
        result = node.execute(state)
        assert result.errors == ["A"]
        assert result.current_node == NodeName.TEST_PLANNER

    def test_node_name(self):
        node = GraphNode(NodeName.REPORTER, _node_b)
        assert node.name == NodeName.REPORTER


class TestEdge:
    """Tests for Edge."""

    def test_edge_attributes(self):
        edge = Edge(NodeName.TEST_PLANNER, NodeName.TEST_EXECUTOR)
        assert edge.source == NodeName.TEST_PLANNER
        assert edge.target == NodeName.TEST_EXECUTOR


class TestConditionalEdge:
    """Tests for ConditionalEdge."""

    def test_resolve(self):
        def router(state: AgentState) -> NodeName:
            return NodeName.BUG_ANALYZER

        edge = ConditionalEdge(
            source=NodeName.TEST_EXECUTOR,
            router=router,
            route_map={NodeName.BUG_ANALYZER: NodeName.BUG_ANALYZER},
        )
        state = AgentState()
        result = edge.resolve(state)
        assert result == NodeName.BUG_ANALYZER

    def test_resolve_with_mapping(self):
        def router(state: AgentState) -> NodeName:
            return NodeName.REPORTER

        edge = ConditionalEdge(
            source=NodeName.BUG_ANALYZER,
            router=router,
            route_map={
                NodeName.REPORTER: NodeName.REPORTER,
                NodeName.SELF_HEALER: NodeName.SELF_HEALER,
            },
        )
        state = AgentState()
        assert edge.resolve(state) == NodeName.REPORTER


class TestGraphBuilder:
    """Tests for GraphBuilder."""

    def test_build_simple_graph(self):
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.add_node(NodeName.TEST_EXECUTOR, _node_b)
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.TEST_EXECUTOR)
        builder.add_edge(NodeName.TEST_EXECUTOR, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()
        assert isinstance(graph, CompiledGraph)

    def test_compile_without_entry_raises(self):
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        with pytest.raises(ValueError, match="Entry point must be set"):
            builder.compile()

    def test_compile_invalid_entry_raises(self):
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.set_entry_point(NodeName.REPORTER)
        with pytest.raises(ValueError, match="not a registered node"):
            builder.compile()

    def test_method_chaining(self):
        builder = (
            GraphBuilder()
            .add_node(NodeName.TEST_PLANNER, _node_a)
            .add_edge(NodeName.TEST_PLANNER, NodeName.END)
            .set_entry_point(NodeName.TEST_PLANNER)
        )
        graph = builder.compile()
        assert graph.entry_point == NodeName.TEST_PLANNER


class TestCompiledGraph:
    """Tests for CompiledGraph execution."""

    def test_linear_execution(self):
        """A -> B -> END"""
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.add_node(NodeName.TEST_EXECUTOR, _node_b)
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.TEST_EXECUTOR)
        builder.add_edge(NodeName.TEST_EXECUTOR, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)

        graph = builder.compile()
        state = AgentState()
        result = graph.run(state)
        assert result.errors == ["A", "B"]

    def test_conditional_routing(self):
        """A -> (condition) -> B or C -> END."""

        def router(state: AgentState) -> NodeName:
            if "go_c" in state.errors:
                return NodeName.REPORTER
            return NodeName.TEST_EXECUTOR

        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.add_node(NodeName.TEST_EXECUTOR, _node_b)
        builder.add_node(NodeName.REPORTER, _node_c)

        builder.add_conditional_edge(
            NodeName.TEST_PLANNER,
            router,
            {
                NodeName.TEST_EXECUTOR: NodeName.TEST_EXECUTOR,
                NodeName.REPORTER: NodeName.REPORTER,
            },
        )
        builder.add_edge(NodeName.TEST_EXECUTOR, NodeName.END)
        builder.add_edge(NodeName.REPORTER, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)

        graph = builder.compile()

        # Path 1: A -> B (no "go_c" flag)
        state1 = AgentState()
        result1 = graph.run(state1)
        assert result1.errors == ["A", "B"]

        # Path 2: A -> C (with "go_c" flag)
        state2 = AgentState()
        state2.errors.append("go_c")
        result2 = graph.run(state2)
        # _node_a appends "A", then router sees "go_c" and routes to C
        assert result2.errors == ["go_c", "A", "C"]

    def test_node_not_found_halts(self):
        """Graph halts gracefully when a node is missing."""
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        # Edge points to a node that does not exist
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.REPORTER)
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()

        state = AgentState()
        result = graph.run(state)
        assert "A" in result.errors
        assert any("Missing node" in e for e in result.errors)

    def test_node_exception_halts(self):
        """Graph halts gracefully when a node raises an exception."""

        def bad_node(state: AgentState) -> AgentState:
            raise RuntimeError("boom")

        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, bad_node)
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()

        state = AgentState()
        result = graph.run(state)
        assert any("boom" in e for e in result.errors)

    def test_get_node_names(self):
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.add_node(NodeName.REPORTER, _node_c)
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.REPORTER)
        builder.add_edge(NodeName.REPORTER, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()
        names = graph.get_node_names()
        assert "reporter" in names
        assert "test_planner" in names

    def test_get_edges(self):
        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.add_node(NodeName.REPORTER, _node_c)
        builder.add_edge(NodeName.TEST_PLANNER, NodeName.REPORTER)
        builder.add_edge(NodeName.REPORTER, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()
        edges = graph.get_edges()
        assert ("test_planner", "reporter") in edges

    def test_get_conditional_edge_sources(self):
        def router(state: AgentState) -> NodeName:
            return NodeName.REPORTER

        builder = GraphBuilder()
        builder.add_node(NodeName.TEST_PLANNER, _node_a)
        builder.add_node(NodeName.REPORTER, _node_c)
        builder.add_conditional_edge(
            NodeName.TEST_PLANNER,
            router,
            {NodeName.REPORTER: NodeName.REPORTER},
        )
        builder.add_edge(NodeName.REPORTER, NodeName.END)
        builder.set_entry_point(NodeName.TEST_PLANNER)
        graph = builder.compile()
        sources = graph.get_conditional_edge_sources()
        assert "test_planner" in sources
