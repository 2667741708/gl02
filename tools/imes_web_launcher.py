"""Local GUI launcher for the IMES Web loopback relay.

The launcher starts the existing 220.12 SSH relay and opens the IMES Web page
on the local loopback address.  The relay's SSH credential is read from the
current process environment or entered into a transient GUI field; it is never
written to files, command-line arguments, or logs.  IMES Web login credentials
are kept separately in the Git-ignored local configuration documented in
``PT/imes.md`` and are not injected into the browser automatically (the site
requires its own login flow and captcha).
"""

from __future__ import annotations

import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk


ROOT = Path(__file__).resolve().parents[1]
RELAY_SCRIPT = ROOT / "tools" / "imes_22012_relay.py"
LOCAL_URL = "http://127.0.0.1:18080/imes.web/"
LOCAL_PORT = 18080
LOCAL_VASTBASE_HOST = "127.0.0.1"
LOCAL_VASTBASE_PORT = 15433


def python_environment() -> dict[str, str]:
    """Return a child environment with the project helper libraries available."""

    env = os.environ.copy()
    bundled = ROOT / ".tmp_pylibs"
    if bundled.is_dir():
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(bundled), current) if item
        )
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def build_relay_command(python_executable: str | None = None) -> list[str]:
    """Build the IMES Web + Vastbase loopback relay command without credentials.

    The old command passed ``--profile all`` and then one ``--forward`` entry.
    ``imes_22012_relay.py`` treats explicit forwards as a replacement for the
    profile, so that combination silently exposed only Web.  The ``imes``
    profile is the bounded two-target contract: Web on 18080 and Vastbase on
    15433.
    """

    executable = python_executable or sys.executable
    return [
        executable,
        str(RELAY_SCRIPT),
        "--profile",
        "imes",
    ]


def local_web_is_ready(timeout: float = 2.0) -> bool:
    """Return whether the local IMES page responds over the loopback relay."""

    try:
        with urllib.request.urlopen(LOCAL_URL, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (OSError, urllib.error.URLError):
        return False


def local_vastbase_is_ready(timeout: float = 1.5) -> bool:
    """Return whether the loopback Vastbase relay listener is accepting TCP."""

    try:
        with socket.create_connection(
            (LOCAL_VASTBASE_HOST, LOCAL_VASTBASE_PORT), timeout=timeout
        ):
            return True
    except OSError:
        return False


class ImesWebLauncher(tk.Tk):
    """Small operator-facing launcher for the IMES Web relay."""

    def __init__(self) -> None:
        super().__init__()
        self.title("IMES Web 本地转发")
        self.geometry("650x430")
        self.minsize(560, 360)
        self.relay_process: subprocess.Popen[str] | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.password_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未启动")
        self._build_ui()
        self.after(150, self._drain_log)
        self.after(1000, self._poll_process)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="IMES Web 本地转发", font=("SimSun", 15, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text="通过 220.12 跳板建立 127.0.0.1:18080 → IMES Web、127.0.0.1:15433 → Vastbase。仅绑定本机回环地址。",
            wraplength=600,
        ).pack(anchor="w", pady=(6, 12))

        password_row = ttk.Frame(frame)
        password_row.pack(fill="x", pady=(0, 8))
        ttk.Label(password_row, text="SSH 密码（仅临时使用）：").pack(side="left")
        ttk.Entry(password_row, textvariable=self.password_var, show="*", width=30).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            frame,
            text="若已设置 BF_22012_SSH_PASSWORD，可留空；密码不会保存。",
            foreground="#555555",
        ).pack(anchor="w")

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=14)
        self.start_button = ttk.Button(actions, text="启动转发", command=self.start_relay)
        self.start_button.pack(side="left")
        self.open_button = ttk.Button(
            actions, text="打开 IMES 页面", command=self.open_page, state="disabled"
        )
        self.open_button.pack(side="left", padx=8)
        self.check_button = ttk.Button(actions, text="检查状态", command=self.check_status)
        self.check_button.pack(side="left")
        self.stop_button = ttk.Button(
            actions, text="停止转发", command=self.stop_relay, state="disabled"
        )
        self.stop_button.pack(side="left", padx=8)
        ttk.Label(actions, textvariable=self.status_var).pack(side="right")

        self.log_text = tk.Text(frame, height=14, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self._append_log(f"本地页面：{LOCAL_URL}")

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_log(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)
        self.after(150, self._drain_log)

    def _read_output(self, stream: object) -> None:
        if not hasattr(stream, "__iter__"):
            return
        for line in stream:  # type: ignore[union-attr]
            self.log_queue.put(str(line))

    def start_relay(self) -> None:
        if self.relay_process and self.relay_process.poll() is None:
            self.status_var.set("运行中")
            return
        if not RELAY_SCRIPT.exists():
            messagebox.showerror("启动失败", f"找不到转发脚本：{RELAY_SCRIPT}")
            return

        env = python_environment()
        password = self.password_var.get()
        if password:
            env["BF_22012_SSH_PASSWORD"] = password
        elif not env.get("BF_22012_SSH_PASSWORD"):
            messagebox.showwarning("需要密码", "请临时输入 SSH 密码，或先设置 BF_22012_SSH_PASSWORD。")
            return

        try:
            self.relay_process = subprocess.Popen(
                build_relay_command(),
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            messagebox.showerror("启动失败", str(exc))
            return

        self.password_var.set("")
        self.status_var.set("连接中…")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        threading.Thread(
            target=self._read_output,
            args=(self.relay_process.stdout,),
            daemon=True,
        ).start()
        self._wait_until_ready(time.monotonic() + 25)

    def _wait_until_ready(self, deadline: float) -> None:
        if self.relay_process and self.relay_process.poll() is not None:
            self.status_var.set("启动失败")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            return
        web_ready = local_web_is_ready()
        vastbase_ready = local_vastbase_is_ready()
        if web_ready and vastbase_ready:
            self.status_var.set("运行中")
            self.open_button.configure(state="normal")
            self._append_log(
                f"转发就绪：Web={LOCAL_URL}；Vastbase={LOCAL_VASTBASE_HOST}:{LOCAL_VASTBASE_PORT}"
            )
            if messagebox.askyesno("IMES Web 已就绪", f"是否立即打开本机页面？\n{LOCAL_URL}"):
                self.open_page()
            return
        if time.monotonic() >= deadline:
            self.status_var.set("转发未完全就绪")
            self._append_log(
                f"状态：Web={'OK' if web_ready else 'FAIL'}；"
                f"Vastbase={'OK' if vastbase_ready else 'FAIL'}。"
            )
            self._append_log("请检查 SSLVPN、220.12 SSH、IMES Web 和 Vastbase 服务状态。")
            return
        self.after(400, lambda: self._wait_until_ready(deadline))

    def open_page(self) -> None:
        if not local_web_is_ready():
            self.check_status()
            return
        webbrowser.open(LOCAL_URL, new=2)
        self._append_log(f"已打开：{LOCAL_URL}")

    def check_status(self) -> None:
        web_ready = local_web_is_ready()
        vastbase_ready = local_vastbase_is_ready()
        ready = web_ready and vastbase_ready
        self.status_var.set("运行中" if ready else "未完全就绪")
        self.open_button.configure(state="normal" if web_ready else "disabled")
        self._append_log(
            f"检查：Web={'HTTP 可访问' if web_ready else '未响应'}；"
            f"Vastbase={'TCP 可达' if vastbase_ready else '未监听'}"
        )

    def stop_relay(self) -> None:
        process = self.relay_process
        if not process or process.poll() is not None:
            self.status_var.set("未启动")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.open_button.configure(state="disabled")
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        self.relay_process = None
        self.status_var.set("已停止")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self._append_log("转发已停止，本机 18080 已释放。")

    def _poll_process(self) -> None:
        if self.relay_process and self.relay_process.poll() is not None:
            self.status_var.set("进程已退出")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.open_button.configure(state="disabled")
        self.after(1000, self._poll_process)

    def close(self) -> None:
        self.stop_relay()
        self.destroy()


def main() -> int:
    app = ImesWebLauncher()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
