"""Keep one localhost-only authenticated SSH transport open for 220.12.

The broker opens a fresh SSH channel for each request while reusing the same
Paramiko transport. Credentials stay in daemon memory. The state file contains
only localhost broker metadata and a random capability token.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import io
import json
import os
import secrets
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import paramiko
import remote_22012_exec as remote_exec


LOCAL_APP_DATA = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
DEFAULT_STATE = LOCAL_APP_DATA / "Codex" / "ssh-sessions" / "22012.json"
DEFAULT_REMOTE_ROOT = r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
KEEPALIVE_SECONDS = 30
MONITOR_SECONDS = 30


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(temporary, path)


def _load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _remove_owned_state(path: Path, session_id: str) -> None:
    try:
        state = _load_state(path)
    except (OSError, ValueError):
        return
    if state.get("session_id") == session_id:
        path.unlink(missing_ok=True)


def _pid_is_running(pid: int) -> bool:
    """Check daemon liveness without sending a signal to the process."""

    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):  # type: ignore[attr-defined]
                return False
            return exit_code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_daemon(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"ok": True, "stopped": False, "state_missing": True}
    state = _load_state(state_path)
    try:
        return _request(state_path, {"operation": "stop"}, 20)
    except (OSError, ValueError, KeyError, ConnectionError) as exc:
        pid = int(state.get("pid") or 0)
        if _pid_is_running(pid):
            return {
                "ok": False,
                "stopped": False,
                "error": "broker process is alive but its localhost endpoint is unreachable",
                "error_type": type(exc).__name__,
                "pid": pid,
            }
        state_path.unlink(missing_ok=True)
        return {
            "ok": True,
            "stopped": False,
            "stale_state_removed": True,
            "pid": pid,
        }


class SessionManager:
    def __init__(self, connection_args: argparse.Namespace, session_id: str) -> None:
        self.connection_args = connection_args
        self.session_id = session_id
        self.client: paramiko.SSHClient | None = None
        self.sftp: paramiko.SFTPClient | None = None
        self.lock = threading.RLock()
        self.connected_at: float | None = None
        self.connection_id: str | None = None
        self.connection_count = 0
        self.request_count = 0

    def close(self) -> None:
        with self.lock:
            if self.sftp is not None:
                try:
                    self.sftp.close()
                finally:
                    self.sftp = None
            if self.client is not None:
                self.client.close()
                self.client = None

    def _active(self) -> bool:
        if self.client is None:
            return False
        transport = self.client.get_transport()
        return bool(transport and transport.is_active() and transport.is_authenticated())

    def ensure(self) -> tuple[paramiko.SSHClient, bool]:
        with self.lock:
            if self._active():
                assert self.client is not None
                return self.client, True
            self.close()
            self.client = remote_exec.connect(self.connection_args)
            transport = self.client.get_transport()
            if transport is not None:
                transport.set_keepalive(KEEPALIVE_SECONDS)
            self.connected_at = time.time()
            self.connection_id = uuid.uuid4().hex
            self.connection_count += 1
            return self.client, False

    def ensure_sftp(self, client: paramiko.SSHClient) -> paramiko.SFTPClient:
        if self.sftp is not None:
            channel = self.sftp.get_channel()
            if not channel.closed and channel.active:
                return self.sftp
            self.sftp.close()
        self.sftp = client.open_sftp()
        return self.sftp

    def monitor(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(MONITOR_SECONDS):
            try:
                self.ensure()
            except (paramiko.SSHException, EOFError, OSError):
                self.close()

    def _metadata(self, reused: bool) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "connection_id": self.connection_id,
            "connected_at": self.connected_at,
            "request_count": self.request_count,
            "reconnect_count": max(0, self.connection_count - 1),
            "reused_connection": reused,
            "keepalive_seconds": KEEPALIVE_SECONDS,
        }

    def status(self) -> dict[str, Any]:
        with self.lock:
            client, reused = self.ensure()
            transport = client.get_transport()
            return {
                "ok": True,
                "ssh_active": bool(transport and transport.is_active()),
                "ssh_authenticated": bool(transport and transport.is_authenticated()),
                **self._metadata(reused),
            }

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run exactly once; never replay a possibly dispatched remote command."""

        request_started = time.perf_counter()
        lock_wait_started = time.perf_counter()
        with self.lock:
            phase_timings: dict[str, float] = {
                "broker_lock_wait_ms": round((time.perf_counter() - lock_wait_started) * 1000, 3)
            }
            argv = list(request.get("argv") or [])
            args = remote_exec.parse_args(argv)
            if args.host.casefold() != self.connection_args.host.casefold():
                return {"ok": False, "error": "run host differs from persistent session host"}
            if args.user.casefold() != self.connection_args.user.casefold():
                return {"ok": False, "error": "run user differs from persistent session user"}

            ensure_started = time.perf_counter()
            client, reused = self.ensure()
            phase_timings["session_ensure_ms"] = round((time.perf_counter() - ensure_started) * 1000, 3)
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            self.request_count += 1
            try:
                with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                    exit_code = remote_exec.execute(
                        args,
                        client=client,
                        sftp=self.ensure_sftp(client),
                        timings=phase_timings,
                    )
                phase_timings["broker_request_total_ms"] = round((time.perf_counter() - request_started) * 1000, 3)
                return {
                    "ok": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout_buffer.getvalue(),
                    "stderr": stderr_buffer.getvalue(),
                    "uncertain_execution": False,
                    "phase_duration_ms": phase_timings,
                    **self._metadata(reused),
                }
            except (paramiko.SSHException, EOFError, OSError) as exc:
                self.close()
                phase_timings["broker_request_total_ms"] = round((time.perf_counter() - request_started) * 1000, 3)
                return {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "stdout": stdout_buffer.getvalue(),
                    "stderr": stderr_buffer.getvalue(),
                    "uncertain_execution": not args.upload_only,
                    "automatic_replay": False,
                    "phase_duration_ms": phase_timings,
                    **self._metadata(reused),
                }
            except BaseException as exc:
                phase_timings["broker_request_total_ms"] = round((time.perf_counter() - request_started) * 1000, 3)
                return {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "stdout": stdout_buffer.getvalue(),
                    "stderr": stderr_buffer.getvalue(),
                    "uncertain_execution": False,
                    "phase_duration_ms": phase_timings,
                    **self._metadata(reused),
                }


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request = json.loads(self.rfile.readline().decode("utf-8"))
        server = self.server
        if not secrets.compare_digest(str(request.get("token", "")), server.token):  # type: ignore[attr-defined]
            response = {"ok": False, "error": "unauthorized"}
        else:
            try:
                operation = request.get("operation")
                if operation == "status":
                    response = server.manager.status()  # type: ignore[attr-defined]
                elif operation == "stop":
                    response = {"ok": True, "stopping": True}
                    server.stop_event.set()  # type: ignore[attr-defined]
                    threading.Thread(target=server.shutdown, daemon=True).start()
                elif operation == "run":
                    response = server.manager.execute(request)  # type: ignore[attr-defined]
                else:
                    response = {"ok": False, "error": "unknown_operation"}
            except BaseException as exc:
                response = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
        self.wfile.write((json.dumps(response, ensure_ascii=False, default=str) + "\n").encode("utf-8"))


class ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _request(state_path: Path, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    state = _load_state(state_path)
    payload["token"] = state["token"]
    with socket.create_connection((state["broker_host"], int(state["broker_port"])), timeout=5) as sock:
        sock.settimeout(timeout)
        stream = sock.makefile("rwb")
        stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        stream.flush()
        line = stream.readline()
    if not line:
        raise ConnectionError("persistent SSH broker returned no response")
    return json.loads(line.decode("utf-8"))


def _add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=os.getenv("BF_22012_HOST", "10.30.220.12"))
    parser.add_argument("--user", default=os.getenv("BF_22012_USER", "administrator"))
    parser.add_argument("--workdir", default=os.getenv("BF_22012_PROJECT_ROOT", DEFAULT_REMOTE_ROOT))
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument("--password-env", default="BF_22012_SSH_PASSWORD")
    parser.add_argument(
        "--password-file",
        default=os.getenv(
            "BF_22012_SSH_PASSWORD_FILE",
            str(remote_exec.DEFAULT_PASSWORD_FILE),
        ),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="action", required=True)
    ensure = sub.add_parser("ensure", help="Reuse a healthy daemon or start one hidden.")
    _add_connection_arguments(ensure)
    serve = sub.add_parser("serve", help=argparse.SUPPRESS)
    _add_connection_arguments(serve)
    serve.add_argument("--broker-port", type=int, default=0)
    sub.add_parser("status")
    sub.add_parser("stop")
    run = sub.add_parser("run", help="Run remote_22012_exec arguments through the broker.")
    run.add_argument("remote_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def _validate_existing_state(args: argparse.Namespace, state: dict[str, Any]) -> None:
    expected = {
        "remote_host": args.host.casefold(),
        "remote_user": args.user.casefold(),
        "workdir": args.workdir.casefold(),
    }
    actual = {key: str(state.get(key, "")).casefold() for key in expected}
    if actual != expected:
        raise RuntimeError("existing persistent session identity differs; stop it explicitly before changing host, user, or workdir")


def _launch_daemon(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--state",
        str(args.state.resolve()),
        "serve",
        "--host",
        args.host,
        "--user",
        args.user,
        "--workdir",
        args.workdir,
        "--password-env",
        args.password_env,
        "--password-file",
        args.password_file,
    ]
    if args.allow_agents_password:
        command.append("--allow-agents-password")
    kwargs: dict[str, Any] = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000 | 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _ensure_daemon(args: argparse.Namespace) -> dict[str, Any]:
    if args.state.exists():
        state = _load_state(args.state)
        _validate_existing_state(args, state)
        try:
            response = _request(args.state, {"operation": "status"}, 20)
            if response.get("ok"):
                response["daemon_reused"] = True
                response["state_path"] = str(args.state)
                return response
        except (OSError, ValueError, KeyError, ConnectionError):
            args.state.unlink(missing_ok=True)

    process = _launch_daemon(args)
    deadline = time.monotonic() + 35
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"persistent SSH daemon exited with code {process.returncode}")
        if args.state.exists():
            try:
                response = _request(args.state, {"operation": "status"}, 20)
                if response.get("ok"):
                    response["daemon_reused"] = False
                    response["state_path"] = str(args.state)
                    return response
            except (OSError, ValueError, KeyError, ConnectionError) as exc:
                last_error = exc
        time.sleep(0.25)
    raise TimeoutError(f"persistent SSH daemon did not become ready: {last_error}")


def _serve(args: argparse.Namespace) -> int:
    connection_args = SimpleNamespace(
        host=args.host,
        user=args.user,
        workdir=args.workdir,
        password_env=args.password_env,
        password_file=args.password_file,
        allow_agents_password=args.allow_agents_password,
        prompt_password=False,
        timeout=30,
    )
    session_id = uuid.uuid4().hex
    manager = SessionManager(connection_args, session_id)
    manager.ensure()
    token = secrets.token_urlsafe(32)
    stop_event = threading.Event()
    with ThreadedServer(("127.0.0.1", args.broker_port), RequestHandler) as server:
        server.manager = manager  # type: ignore[attr-defined]
        server.token = token  # type: ignore[attr-defined]
        server.stop_event = stop_event  # type: ignore[attr-defined]
        broker_host, broker_port = server.server_address
        _write_json(
            args.state,
            {
                "pid": os.getpid(),
                "session_id": session_id,
                "broker_host": broker_host,
                "broker_port": broker_port,
                "token": token,
                "remote_host": args.host,
                "remote_user": args.user,
                "workdir": args.workdir,
                "started_at": time.time(),
            },
        )
        monitor = threading.Thread(target=manager.monitor, args=(stop_event,), daemon=True)
        monitor.start()
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            stop_event.set()
            manager.close()
            _remove_owned_state(args.state, session_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.action == "serve":
        return _serve(args)
    if args.action == "ensure":
        response = _ensure_daemon(args)
    elif args.action == "status":
        response = _request(args.state, {"operation": "status"}, 20)
    elif args.action == "stop":
        response = _stop_daemon(args.state)
    else:
        remote_args = list(args.remote_args)
        if remote_args and remote_args[0] == "--":
            remote_args = remote_args[1:]
        if not remote_args:
            raise SystemExit("run requires remote_22012_exec arguments after --")
        parsed = remote_exec.parse_args(remote_args)
        response = _request(
            args.state,
            {"operation": "run", "argv": remote_args},
            max(30, int(parsed.timeout) + 30),
        )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
