"""Single-node execution engine integrating with the Agent Loop."""

from __future__ import annotations

import asyncio
import logging
import time
from string import Template
from typing import Any

from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage
from openharness.engine.query import QueryContext, run_query
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
)
from openharness.tools.base import ToolRegistry

from openharness.workflow.types import NodeResult, NodeStatus, WorkflowNode

log = logging.getLogger(__name__)


class NodeExecutor:
    """Executes a single workflow node through the Agent Loop."""

    def __init__(
        self,
        query_context: QueryContext,
        default_tools: list[str] | None = None,
    ) -> None:
        self._query_context = query_context
        self._default_tools = default_tools

    async def execute(
        self,
        node: WorkflowNode,
        upstream_results: dict[str, NodeResult],
        global_variables: dict[str, Any] | None = None,
    ) -> NodeResult:
        """
        Execute a workflow node.

        Args:
            node: The workflow node to execute.
            upstream_results: Results from dependency nodes, keyed by node ID.
            global_variables: Global variables for prompt interpolation.

        Returns:
            NodeResult with status, output, and metrics.
        """
        start_time = time.monotonic()
        prompt = self._render_prompt(node, upstream_results, global_variables)
        messages = [ConversationMessage.from_user_text(prompt)]

        # Build a node-specific context if tools are restricted
        ctx = self._query_context
        if node.tools is not None:
            ctx = self._build_restricted_context(node.tools)

        result = NodeResult(node_id=node.id, status=NodeStatus.RUNNING)
        total_usage = UsageSnapshot()

        try:
            async for event, usage in run_query(ctx, messages):
                if usage is not None:
                    total_usage = UsageSnapshot(
                        input_tokens=total_usage.input_tokens + usage.input_tokens,
                        output_tokens=total_usage.output_tokens + usage.output_tokens,
                    )

                if isinstance(event, AssistantTextDelta):
                    result.output += event.text
                elif isinstance(event, AssistantTurnComplete):
                    # Extract text from the message if output is still empty
                    if not result.output and event.message.content:
                        for block in event.message.content:
                            if hasattr(block, 'text'):
                                result.output += block.text

            result.status = NodeStatus.COMPLETED
            result.input_tokens = total_usage.input_tokens
            result.output_tokens = total_usage.output_tokens
            result.duration_seconds = time.monotonic() - start_time

        except asyncio.TimeoutError:
            result.status = NodeStatus.FAILED
            result.error_message = f"Node timed out after {node.timeout_seconds}s"
            result.duration_seconds = time.monotonic() - start_time
            log.warning("Node %s timed out", node.id)

        except Exception as exc:
            result.status = NodeStatus.FAILED
            result.error_message = str(exc)
            result.duration_seconds = time.monotonic() - start_time
            log.exception("Node %s failed with error: %s", node.id, exc)

        return result

    def _render_prompt(
        self,
        node: WorkflowNode,
        upstream_results: dict[str, NodeResult],
        global_variables: dict[str, Any] | None,
    ) -> str:
        """Render the prompt template with variables and upstream results."""
        variables: dict[str, Any] = {**(global_variables or {}), **node.variables}

        # Inject upstream results as variables
        for nid, nresult in upstream_results.items():
            var_name = f"{nid}_output"
            variables[var_name] = nresult.output
            variables[f"{nid}_status"] = nresult.status.value

        # Use Python's string.Template for safe interpolation
        try:
            prompt = Template(node.prompt_template).safe_substitute(variables)
        except Exception:
            # Fallback: return raw template if interpolation fails
            log.warning("Failed to interpolate template for node %s", node.id)
            prompt = node.prompt_template

        return prompt

    def _build_restricted_context(self, allowed_tools: list[str]) -> QueryContext:
        """Create a QueryContext with a restricted tool set."""
        from openharness.tools.base import ToolRegistry

        # Build a new registry with only the allowed tools
        restricted = ToolRegistry()
        for tool_name in allowed_tools:
            if tool_name in self._query_context.tool_registry._tools:
                tool = self._query_context.tool_registry._tools[tool_name]
                restricted.register(tool)
            else:
                log.warning("Tool '%s' not found in registry, skipping", tool_name)

        # Build a new QueryContext with the restricted tool registry
        # We can't deepcopy because of unpicklable objects (HTTP clients, locks)
        ctx = QueryContext(
            api_client=self._query_context.api_client,
            tool_registry=restricted,
            permission_checker=self._query_context.permission_checker,
            cwd=self._query_context.cwd,
            model=self._query_context.model,
            system_prompt=self._query_context.system_prompt,
            max_tokens=self._query_context.max_tokens,
            permission_prompt=self._query_context.permission_prompt,
            ask_user_prompt=self._query_context.ask_user_prompt,
            max_turns=self._query_context.max_turns,
            hook_executor=self._query_context.hook_executor,
            tool_metadata=self._query_context.tool_metadata,
        )
        return ctx
