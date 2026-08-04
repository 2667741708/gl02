"""Forward IMES and pSpace TCP services through the authorized 220.12 SSH host.

Requirement: REQ-IMES-22012-RELAY-MCP-20260716
The listeners bind to 127.0.0.1 by default and perform no protocol rewriting.
"""
from __future__ import annotations

import argparse
import json
import select
import socketserver
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import paramiko

import remote_22012_exec as remote_helper


@dataclass(frozen=True)
class RelaySpec:
    """One local listener mapped to a host/port reachable from 220.12."""

    name: str
    local_port: int
    remote_host: str
    remote_port: int


DEFAULT_RELAYS = (
    RelaySpec("imes_vastbase", 15433, "10.10.181.195", 5432),
    RelaySpec("imes_web", 18080, "10.10.181.209", 8080),
    RelaySpec("pspace", 18889, "10.22.181.243", 8889),
)


def parse_forward(value: str) -> RelaySpec:
    """Parse NAME:LOCAL_PORT:REMOTE_HOST:REMOTE_PORT."""

    parts = value.split(":")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "--forward 格式应为 NAME:LOCAL_PORT:REMOTE_HOST:REMOTE_PORT"
        )
    name, local_port, remote_host, remote_port = parts
    try:
        parsed = RelaySpec(name, int(local_port), remote_host, int(remote_port))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("转发端口必须是整数") from exc
    if not name or not remote_host or not 1 <= parsed.local_port <= 65535 or not 1 <= parsed.remote_port <= 65535:
        raise argparse.ArgumentTypeError("转发名称、主机和端口无效")
    return parsed


def selected_relays(profile: str, custom: Sequence[RelaySpec]) -> list[RelaySpec]:
    """Select defaults by profile unless explicit mappings were provided."""

    if custom:
        return list(custom)
    if profile == "imes":
        return [item for item in DEFAULT_RELAYS if item.name.startswith("imes_")]
    if profile == "pspace":
        return [item for item in DEFAULT_RELAYS if item.name == "pspace"]
    return list(DEFAULT_RELAYS)


def ssh_password_args(args: argparse.Namespace) -> argparse.Namespace:
    """Adapt relay arguments to the shared 220.12 credential resolver."""

    return argparse.Namespace(
        host=args.ssh_host,
        user=args.ssh_user,
        password_env=args.password_env,
        allow_agents_password=args.allow_agents_password,
        prompt_password=args.prompt_password,
    )


def connect_ssh(args: argparse.Namespace) -> paramiko.SSHClient:
    """Create the authorized SSH jump-host connection."""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.ssh_host,
        port=args.ssh_port,
        username=args.ssh_user,
        password=remote_helper.resolve_password(ssh_password_args(args)),
        timeout=args.connect_timeout,
        banner_timeout=max(args.connect_timeout, 30),
        auth_timeout=args.connect_timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    transport = client.get_transport()
    if not transport or not transport.is_active():
        client.close()
        raise RuntimeError("220.12 SSH transport is not active")
    transport.set_keepalive(args.keepalive_seconds)
    return client


def probe_relays(transport: paramiko.Transport, relays: Sequence[RelaySpec]) -> list[dict]:
    """Use SSH direct-tcpip channels to verify every remote target."""

    results: list[dict] = []
    for item in relays:
        started = time.monotonic()
        try:
            channel = transport.open_channel(
                "direct-tcpip",
                (item.remote_host, item.remote_port),
                ("127.0.0.1", 0),
                timeout=8,
            )
            channel.close()
            ok, error = True, None
        except Exception as exc:  # Paramiko exposes several SSH/channel errors
            ok, error = False, f"{type(exc).__name__}: {exc}"
        results.append(
            asdict(item)
            | {
                "ok": ok,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "error": error,
            }
        )
    return results


class RelayHandler(socketserver.BaseRequestHandler):
    """Bridge one local client socket to one Paramiko direct-tcpip channel."""

    def handle(self) -> None:
        server = self.server
        channel = server.transport.open_channel(
            "direct-tcpip",
            server.remote_address,
            self.client_address,
        )
        if channel is None:
            return
        try:
            while True:
                readable, _, _ = select.select([self.request, channel], [], [], 30)
                if self.request in readable:
                    try:
                        data = self.request.recv(65536)
                    except (ConnectionResetError, OSError):
                        break
                    if not data:
                        break
                    channel.sendall(data)
                if channel in readable:
                    data = channel.recv(65536)
                    if not data:
                        break
                    try:
                        self.request.sendall(data)
                    except (ConnectionResetError, OSError):
                        break
        finally:
            channel.close()


class RelayServer(socketserver.ThreadingTCPServer):
    """Threaded loopback-only relay server."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        bind_address: tuple[str, int],
        transport: paramiko.Transport,
        remote_address: tuple[str, int],
    ) -> None:
        self.transport = transport
        self.remote_address = remote_address
        super().__init__(bind_address, RelayHandler)


def build_parser() -> argparse.ArgumentParser:
    """Build the relay CLI."""

    parser = argparse.ArgumentParser(
        description="通过 220.12 SSH 将 IMES Vastbase/Web 与 pSpace 转发到本机回环端口。"
    )
    parser.add_argument("--ssh-host", default="10.30.220.12")
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--ssh-user", default="administrator")
    parser.add_argument("--password-env", default="BF_22012_SSH_PASSWORD")
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument("--prompt-password", action="store_true")
    parser.add_argument("--connect-timeout", type=int, default=30)
    parser.add_argument("--keepalive-seconds", type=int, default=30)
    parser.add_argument("--bind-host", default="127.0.0.1")
    parser.add_argument("--profile", choices=("all", "imes", "pspace"), default="all")
    parser.add_argument("--forward", action="append", type=parse_forward, default=[])
    parser.add_argument("--check", action="store_true", help="只验证 SSH 目标通道，不启动监听。")
    parser.add_argument("--status-file", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Check targets or serve loopback forwarders until interrupted."""

    args = build_parser().parse_args(argv)
    if args.bind_host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("为避免暴露生产端口，--bind-host 只允许本机回环地址")
    relays = selected_relays(args.profile, args.forward)
    client = connect_ssh(args)
    servers: list[RelayServer] = []
    try:
        transport = client.get_transport()
        assert transport is not None
        checks = probe_relays(transport, relays)
        payload = {
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "ssh_host": args.ssh_host,
            "bind_host": args.bind_host,
            "all_ok": all(item["ok"] for item in checks),
            "relays": checks,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text, flush=True)
        if args.status_file:
            args.status_file.parent.mkdir(parents=True, exist_ok=True)
            args.status_file.write_text(text, encoding="utf-8")
        if args.check:
            return 0 if payload["all_ok"] else 2
        if not payload["all_ok"]:
            return 2

        for item in relays:
            server = RelayServer(
                (args.bind_host, item.local_port),
                transport,
                (item.remote_host, item.remote_port),
            )
            thread = threading.Thread(
                target=server.serve_forever,
                name=f"relay-{item.name}",
                daemon=True,
            )
            thread.start()
            servers.append(server)
            print(
                f"[relay] {args.bind_host}:{item.local_port} -> "
                f"220.12 -> {item.remote_host}:{item.remote_port}",
                flush=True,
            )
        while transport.is_active():
            time.sleep(1)
        print("220.12 SSH transport closed", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
