"""Per-request MCP client manager with host-side namespaced tool routing."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Iterable

from .server_registry import McpServerConfig, McpServerRegistry


class McpHostError(RuntimeError):
    """Base error for a multi-server MCP host failure."""


class McpServerUnavailable(McpHostError):
    """Raised when none of the selected MCP servers can be attached."""


class McpToolNotAttached(McpHostError):
    """Raised when a requested exposed tool is not attached to this request."""


@dataclass(frozen=True)
class McpToolBinding:
    exposed_name: str
    native_name: str
    server_id: str
    description: str
    input_schema: dict[str, Any]


def exposed_tool_name(server: McpServerConfig, native_name: str) -> str:
    return f"{server.namespace}__{native_name}" if server.namespace else native_name


class McpClientManager:
    """Attach selected stdio servers and route exposed tool names to their sessions."""

    def __init__(self, registry: McpServerRegistry, python_command: str) -> None:
        self._registry = registry
        self._python_command = python_command
        self._stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}
        self._bindings: dict[str, McpToolBinding] = {}
        self._errors: dict[str, str] = {}

    async def __aenter__(self) -> "McpClientManager":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._stack.aclose()

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    @property
    def bindings(self) -> tuple[McpToolBinding, ...]:
        return tuple(self._bindings.values())

    @asynccontextmanager
    async def execution_scope(self):
        """Expose an already-attached manager as the request's routed tool session."""

        if not self._sessions:
            raise McpServerUnavailable("MCP execution scope requires at least one attached server")
        yield self

    async def attach(self, server_ids: Iterable[str]) -> tuple[McpToolBinding, ...]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise McpServerUnavailable(f"MCP Python dependency is unavailable: {exc}") from exc

        requested = tuple(dict.fromkeys(str(value) for value in server_ids if str(value)))
        for server_id in requested:
            server = self._registry.by_id(server_id)
            try:
                params = StdioServerParameters(
                    command=self._python_command,
                    args=[str(server.script_path)],
                    env=server.process_env(),
                )
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                response = await session.list_tools()
                pending: list[McpToolBinding] = []
                for tool in response.tools:
                    if tool.name in server.excluded_tools:
                        continue
                    exposed = exposed_tool_name(server, tool.name)
                    if exposed in self._bindings or any(item.exposed_name == exposed for item in pending):
                        raise McpHostError(f"Duplicate exposed MCP tool name: {exposed}")
                    pending.append(
                        McpToolBinding(
                            exposed_name=exposed,
                            native_name=tool.name,
                            server_id=server_id,
                            description=tool.description or "",
                            input_schema=dict(tool.inputSchema or {}),
                        )
                    )
                self._sessions[server_id] = session
                self._bindings.update((item.exposed_name, item) for item in pending)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._errors[server_id] = f"{type(exc).__name__}: {exc}"
        if not self._sessions:
            detail = "; ".join(f"{key}={value}" for key, value in self._errors.items()) or "no selected server"
            raise McpServerUnavailable(f"No selected MCP server could be attached: {detail}")
        return self.bindings

    def ollama_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": binding.exposed_name,
                    "description": binding.description,
                    "parameters": binding.input_schema,
                },
            }
            for binding in self.bindings
        ]

    async def call_tool(self, exposed_name: str, arguments: dict[str, Any]) -> Any:
        binding = self._bindings.get(exposed_name)
        if binding is None:
            raise McpToolNotAttached(f"MCP tool is not attached to this request: {exposed_name}")
        session = self._sessions.get(binding.server_id)
        if session is None:
            raise McpServerUnavailable(f"MCP session is unavailable: {binding.server_id}")
        return await session.call_tool(binding.native_name, arguments)
