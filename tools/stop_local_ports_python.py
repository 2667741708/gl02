from __future__ import annotations

import argparse
import subprocess
import time

try:
    import psutil  # type: ignore
except ModuleNotFoundError:
    psutil = None


def listener_pids(ports: set[int]) -> dict[int, set[int]]:
    found: dict[int, set[int]] = {port: set() for port in ports}
    if psutil is not None:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status != "LISTEN" or not conn.laddr or not conn.pid:
                continue
            port = int(conn.laddr.port)
            if port in ports:
                found.setdefault(port, set()).add(int(conn.pid))
        return found

    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        state = parts[-2].upper()
        if state not in {"LISTEN", "LISTENING"}:
            continue
        local_addr = parts[1]
        pid_text = parts[-1]
        for port in ports:
            if local_addr.endswith(f":{port}") and pid_text.isdigit():
                found.setdefault(port, set()).add(int(pid_text))
    return found


def stop_pid(pid: int, *, force: bool) -> None:
    if psutil is not None:
        proc = psutil.Process(pid)
        if force:
            proc.kill()
        else:
            proc.terminate()
        return
    cmd = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        cmd.append("/F")
    subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop local processes that listen on selected TCP ports.")
    parser.add_argument("--ports", nargs="+", type=int, required=True)
    parser.add_argument("--kill", action="store_true", help="Kill instead of graceful terminate.")
    parser.add_argument("--wait-seconds", type=float, default=3)
    args = parser.parse_args()

    ports = set(args.ports)
    found = listener_pids(ports)
    stopped: list[tuple[int, int, str]] = []
    for port, pids in found.items():
        for pid in sorted(pids):
            action = "kill" if args.kill else "terminate"
            stop_pid(pid, force=args.kill)
            stopped.append((port, pid, "killed" if args.kill else "terminated"))

    if not args.kill and stopped:
        time.sleep(max(0, args.wait_seconds))
        remaining = listener_pids(ports)
        for port, pids in remaining.items():
            for pid in sorted(pids):
                stop_pid(pid, force=True)
                stopped.append((port, pid, "killed_after_wait"))

    print("stopped_ports=", stopped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
