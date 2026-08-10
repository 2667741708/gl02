"""Host-side multi-server MCP orchestration for the blast-furnace assistant."""

from .client_manager import McpClientManager, McpHostError, McpToolBinding
from .domain_router import DomainSelection, select_mcp_servers
from .server_registry import McpRegistryError, McpServerConfig, McpServerRegistry, load_server_registry

__all__ = [
    "DomainSelection",
    "McpClientManager",
    "McpHostError",
    "McpRegistryError",
    "McpServerConfig",
    "McpServerRegistry",
    "McpToolBinding",
    "load_server_registry",
    "select_mcp_servers",
]
