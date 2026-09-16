"""Owner-scoped cancellation for interactive QA; no model request replay."""
from contextlib import contextmanager
import re
import socket
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse


class Cancelled(BaseException):
    pass


_local = threading.local()
_lock = threading.RLock()
_requests = {}
TERMINAL = {"completed", "cancelled", "failed"}


class RequestState:
    def __init__(self, request_id, owner, conversation):
        self.id = request_id
        self.owner = owner
        self.conversation = conversation
        self.state = "running"
        self.created = time.monotonic()
        self.cancel = threading.Event()
        self.finished = threading.Event()
        self.transport = None
        self.write_lock = threading.RLock()

    def public(self):
        return {"request_id": self.id, "conversation_id": self.conversation,
                "state": self.state, "terminal": self.finished.is_set()}

    def stop(self):
        with self.write_lock:
            if self.state in TERMINAL:
                return
            self.state = "cancelling"
            self.cancel.set()
            response = self.transport
        # Interrupt an active upstream socket without closing the shared model service.
        try:
            response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (AttributeError, OSError):
            pass


def checkpoint():
    state = getattr(_local, "state", None)
    if state and (state.cancel.is_set() or time.monotonic() - state.created > 600):
        state.stop()
        raise Cancelled()


async def call_tool(session, name, arguments):
    checkpoint()
    result = await session.call_tool(name, arguments)
    checkpoint()
    return result


def install(handler, namespace):
    original_open = namespace["urlopen"]
    original_db = namespace["db_connect"]
    original_event = handler.write_qa_event

    def tracked_open(*args, **kwargs):
        checkpoint()
        response = original_open(*args, **kwargs)
        state = getattr(_local, "state", None)
        if state:
            state.transport = response
            if state.cancel.is_set():
                response.close()
                checkpoint()
        return response

    @contextmanager
    def tracked_db(*args, **kwargs):
        checkpoint()
        with original_db(*args, **kwargs) as conn:
            state = getattr(_local, "state", None)
            if not state:
                yield conn
                return
            class GuardedConnection:
                def __getattr__(self, name):
                    return getattr(conn, name)
                def __setattr__(self, name, value):
                    setattr(conn, name, value)
                def commit(self):
                    with state.write_lock:
                        checkpoint()
                        return conn.commit()
            yield GuardedConnection()
            with state.write_lock:
                checkpoint()
                conn.commit()

    def event(self, name, payload):
        state = getattr(_local, "state", None)
        if not state:
            return original_event(self, name, payload)
        with state.write_lock:
            checkpoint()
            if isinstance(payload, dict):
                payload = {**payload, "request_id": state.id}
            written = original_event(self, name, payload)
            if not written:
                state.stop()
                raise Cancelled()
            if name == "final":
                state.state = "completed"
            elif name == "error":
                state.state = "failed"
            return written

    def wrap(original, stream):
        def run(self, payload, question):
            request_id = str(payload.get("client_request_id") or uuid.uuid4())
            if not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", request_id.replace("-", "_")):
                self.send_json({"ok": False, "error": "invalid_request_id"}, status=400)
                return
            with _lock:
                for key, old in list(_requests.items()):
                    if old.finished.is_set() and time.monotonic() - old.created > 3600:
                        del _requests[key]
                if request_id in _requests or len(_requests) >= 2048:
                    self.send_json({"ok": False, "error": "request_already_exists"}, status=409)
                    return
                if any(not old.finished.is_set() for old in _requests.values()):
                    self.send_json({"ok": False, "error": "assistant_in_use",
                                    "message": "智能助手正在使用中，请等待当前请求结束后手动发送。",
                                    "retryable": True, "automatic_replay": False}, status=409)
                    return
                conversation = payload.get("conversation_id")
                for old in _requests.values():
                    if conversation and old.conversation == conversation and old.owner == payload["_qa_owner_subject"] and not old.finished.is_set():
                        self.send_json({"ok": False, "error": "request_already_running", "request_id": old.id}, status=409)
                        return
                state = RequestState(request_id, payload["_qa_owner_subject"], payload.get("conversation_id"))
                _requests[request_id] = state
            _local.state = state

            def heartbeat():
                while not state.finished.wait(10):
                    if time.monotonic() - state.created > 600:
                        state.stop()
                    with state.write_lock:
                        if state.state in TERMINAL:
                            return
                        if not original_event(self, "heartbeat", state.public()):
                            state.stop()
                            return

            # Heartbeats begin only after the HTTP stream has sent its headers/start.
            original_start = None
            started = False
            guest_lock = None
            try:
                if stream:
                    original_start = self.write_qa_event
                    def start_event(name, value):
                        nonlocal started
                        result = original_start(name, value)
                        if not started:
                            started = True
                            threading.Thread(target=heartbeat, daemon=True).start()
                        return result
                    self.write_qa_event = start_event
                if payload.get("_qa_access_mode") == "guest_shared":
                    candidate_lock = namespace["guest_room_generation_lock"](state.owner)
                    while not candidate_lock.acquire(timeout=0.2):
                        checkpoint()
                    guest_lock = candidate_lock
                checkpoint()
                original(self, payload, question)
                checkpoint()
                if state.state == "running":
                    state.state = "failed" if stream else "completed"
            except Cancelled:
                state.state = "cancelled"
                if stream and started:
                    with state.write_lock:
                        original_event(self, "error", {"ok": False, "error": "request_cancelled", "request_id": request_id})
                else:
                    self.send_json({"ok": False, "error": "request_cancelled"}, status=409)
            finally:
                if guest_lock:
                    guest_lock.release()
                if state.cancel.is_set() and state.state != "completed":
                    state.state = "cancelled"
                elif state.state not in TERMINAL:
                    state.state = "failed"
                state.finished.set()
                _local.state = None
                if original_start:
                    self.write_qa_event = original_start
        return run

    def control(self, cancel=False):
        if cancel and not self.qa_write_request_allowed():
            return
        session = self.qa_session_required()
        if session is None:
            return
        try:
            request_id = (self.read_json_body().get("request_id") if cancel else
                          parse_qs(urlparse(self.path).query).get("request_id", [""])[0])
        except (ValueError, AttributeError):
            self.send_json({"ok": False, "error": "invalid_request_id"}, status=400)
            return
        with _lock:
            state = _requests.get(str(request_id))
            # A cancel arriving before request preparation seals the ID against late execution.
            if not state and cancel and re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", str(request_id)):
                if len(_requests) >= 2048:
                    self.send_json({"ok": False, "error": "request_capacity"}, status=503)
                    return
                state = RequestState(str(request_id), str(session.get("sub") or ""), None)
                state.state = "cancelled"
                state.cancel.set()
                state.finished.set()
                _requests[str(request_id)] = state
        if not state or state.owner != str(session.get("sub") or ""):
            self.send_json({"ok": False, "error": "request_not_found"}, status=404)
            return
        if cancel:
            state.stop()
        self.send_json({"ok": True, **state.public()})

    get = handler.do_GET
    post = handler.do_POST
    def do_get(self):
        if urlparse(self.path).path == "/api/qa/request-status":
            return control(self)
        return get(self)
    def do_post(self):
        if urlparse(self.path).path == "/api/qa/cancel":
            return control(self, True)
        return post(self)

    namespace["urlopen"] = tracked_open
    namespace["db_connect"] = tracked_db
    handler.write_qa_event = event
    handler.handle_qa_chat_stream = wrap(handler.handle_qa_chat_stream, True)
    handler.handle_qa_chat_json = wrap(handler.handle_qa_chat_json, False)
    handler.do_GET = do_get
    handler.do_POST = do_post
