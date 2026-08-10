"""Validated configuration contract for MCP servers attached to the QA host."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class McpRegistryError(RuntimeError):
    """Raised when the MCP server registry is missing or internally inconsistent."""


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    display_name: str
    domains: tuple[str, ...]
    script_path: Path
    namespace: str = ""
    enabled: bool = True
    default: bool = False
    env_defaults: tuple[tuple[str, str], ...] = ()
    excluded_tools: tuple[str, ...] = ()

    def process_env(self, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return a child environment where explicit process values beat safe defaults."""

        result = dict(base_env if base_env is not None else os.environ)
        for key, value in self.env_defaults:
            result.setdefault(key, value)
        return result


@dataclass(frozen=True)
class McpServerRegistry:
    version: int
    servers: tuple[McpServerConfig, ...]

    def enabled_servers(self) -> tuple[McpServerConfig, ...]:
        return tuple(server for server in self.servers if server.enabled)

    def by_id(self, server_id: str) -> McpServerConfig:
        for server in self.enabled_servers():
            if server.server_id == server_id:
                return server
        raise McpRegistryError(f"MCP server is not enabled or registered: {server_id}")


def _required_string(item: Mapping[str, Any], key: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise McpRegistryError(f"MCP registry field must be a non-empty string: {key}")
    return value


def load_server_registry(path: str | Path, *, require_scripts: bool = True) -> McpServerRegistry:
    """Load and validate a versioned MCP server registry JSON document."""

    registry_path = Path(path).resolve()
    if not registry_path.is_file():
        raise McpRegistryError(f"MCP server registry does not exist: {registry_path}")
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise McpRegistryError(f"Cannot read MCP server registry: {registry_path}") from exc
    if not isinstance(payload, dict):
        raise McpRegistryError("MCP server registry root must be an object")
    version = int(payload.get("version") or 0)
    if version != 1:
        raise McpRegistryError(f"Unsupported MCP server registry version: {version}")
    raw_servers = payload.get("servers")
    if not isinstance(raw_servers, list) or not raw_servers:
        raise McpRegistryError("MCP server registry must contain at least one server")

    servers: list[McpServerConfig] = []
    seen_ids: set[str] = set()
    seen_namespaces: set[str] = set()
    for raw in raw_servers:
        if not isinstance(raw, dict):
            raise McpRegistryError("Each MCP server entry must be an object")
        server_id = _required_string(raw, "server_id")
        if server_id in seen_ids:
            raise McpRegistryError(f"Duplicate MCP server_id: {server_id}")
        namespace = str(raw.get("namespace") or "").strip()
        if namespace and namespace in seen_namespaces:
            raise McpRegistryError(f"Duplicate MCP namespace: {namespace}")
        domains = tuple(str(value).strip() for value in raw.get("domains") or () if str(value).strip())
        if not domains:
            raise McpRegistryError(f"MCP server must declare at least one domain: {server_id}")
        script_value = _required_string(raw, "script")
        script_path = (registry_path.parent / script_value).resolve()
        if require_scripts and not script_path.is_file():
            raise McpRegistryError(f"MCP server script does not exist: {server_id} -> {script_path}")
        env_raw = raw.get("env_defaults") or {}
        if not isinstance(env_raw, dict):
            raise McpRegistryError(f"env_defaults must be an object: {server_id}")
        env_defaults = tuple((str(key), str(value)) for key, value in env_raw.items())
        servers.append(
            McpServerConfig(
                server_id=server_id,
                display_name=str(raw.get("display_name") or server_id),
                domains=domains,
                script_path=script_path,
                namespace=namespace,
                enabled=bool(raw.get("enabled", True)),
                default=bool(raw.get("default", False)),
                env_defaults=env_defaults,
                excluded_tools=tuple(
                    str(value).strip()
                    for value in raw.get("excluded_tools") or ()
                    if str(value).strip()
                ),
            )
        )
        seen_ids.add(server_id)
        if namespace:
            seen_namespaces.add(namespace)
    if not any(server.enabled and server.default for server in servers):
        raise McpRegistryError("At least one enabled MCP server must be marked as default")
    return McpServerRegistry(version=version, servers=tuple(servers))
