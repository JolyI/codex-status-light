from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple


DEFAULT_LOGS_DB = str(Path.home() / ".codex" / "logs_2.sqlite")
DEFAULT_SESSIONS_DIR = str(Path.home() / ".codex" / "sessions")
DEFAULT_PORT = "auto"
DEFAULT_BAUD_RATE = 115200
DEFAULT_POLL_SECONDS = 0.2
DEFAULT_SERIAL_OPEN_SETTLE_SECONDS = 0.8
DEFAULT_IDLE_DEBOUNCE_SECONDS = 1.5
DEFAULT_RESEND_SECONDS = 2.0
DEFAULT_BOOTSTRAP_WINDOW_SECONDS = 120
DEFAULT_MAX_BUSY_SECONDS = 20 * 60
DEFAULT_UNFINISHED_TASK_STALE_SECONDS = 120
SERIAL_PORT_PATTERNS = (
    "/dev/cu.usbmodem*",
    "/dev/cu.SLAB_USBtoUART*",
    "/dev/cu.wchusbserial*",
    "/dev/cu.usbserial*",
)
VISIBLE_STATES = ("idle", "busy", "attention")
USER_ATTENTION_KEYWORDS = (
    "需要你确认",
    "请确认",
    "确认一下",
    "需要你授权",
    "需要你输入",
    "需要你登录",
    "需要你处理",
    "需要你操作",
    "需要你介入",
    "确认后",
    "等待你",
    "等你确认",
    "browser is not available",
    "requires your confirmation",
    "please confirm",
    "need your confirmation",
    "need your approval",
    "need your permission",
    "need your input",
    "waiting for you",
    "waiting for user",
    "user input required",
)


def classify_desktop_event(body: str) -> Optional[str]:
    text = body or ""
    lowered = text.lower()

    if lowered.startswith("app-server event: item/started"):
        return "started"
    if lowered.startswith("app-server event: item/completed"):
        return "completed"

    if lowered.startswith("session_loop") and (
        "submission_dispatch{otel.name=\"op.dispatch.user_input\"" in lowered
        or "run_sampling_request{" in lowered
        or "try_run_sampling_request{" in lowered
        or "stream_request:model_client.stream_responses_api" in lowered
    ):
        return "started"

    if "event.name=\"codex.sse_event\"" in lowered:
        if "event.kind=response.in_progress" in lowered:
            return "started"
        if "event.kind=response.completed" in lowered:
            return "completed"
        if "event.kind=response.failed" in lowered:
            return "failed"

    if lowered.startswith("sse event: {\"type\":\"response.in_progress\""):
        return "started"
    if lowered.startswith("sse event: {\"type\":\"response.completed\""):
        return "completed"
    if lowered.startswith("sse event: {\"type\":\"response.failed\""):
        return "failed"

    return None


class DesktopStateMachine:
    def __init__(
        self,
        idle_debounce_seconds: float = DEFAULT_IDLE_DEBOUNCE_SECONDS,
        max_busy_seconds: float = DEFAULT_MAX_BUSY_SECONDS,
        initial_state: str = "idle",
    ):
        self.idle_debounce_seconds = idle_debounce_seconds
        self.max_busy_seconds = max_busy_seconds
        self.state = initial_state if initial_state in VISIBLE_STATES else "idle"
        self.pending_idle_at = None
        self.busy_started_at = None

    def apply(self, event: str, now: float) -> None:
        if event == "started":
            self.state = "busy"
            self.pending_idle_at = None
            if self.busy_started_at is None:
                self.busy_started_at = now
            return

        if event == "completed":
            self.pending_idle_at = now + self.idle_debounce_seconds
            return

        if event == "failed":
            self.state = "attention"
            self.pending_idle_at = None
            self.busy_started_at = None

    def current_state(self, now: float) -> str:
        if self.pending_idle_at is not None and now >= self.pending_idle_at:
            self.state = "idle"
            self.pending_idle_at = None
            self.busy_started_at = None

        if (
            self.state == "busy"
            and self.busy_started_at is not None
            and now - self.busy_started_at > self.max_busy_seconds
        ):
            self.state = "idle"
            self.pending_idle_at = None
            self.busy_started_at = None

        return self.state


def _connect_logs_db(logs_db_path: str):
    return sqlite3.connect(f"file:{logs_db_path}?mode=ro", uri=True)


def _logs_db_exists(logs_db_path: str) -> bool:
    return Path(logs_db_path).exists()


def _event_filter_sql() -> str:
    return """
      feedback_log_body like 'event.name="codex.sse_event" event.kind=response.in_progress%'
      or feedback_log_body like 'event.name="codex.sse_event" event.kind=response.completed%'
      or feedback_log_body like 'event.name="codex.sse_event" event.kind=response.failed%'
      or feedback_log_body like 'SSE event: {"type":"response.in_progress"%'
      or feedback_log_body like 'SSE event: {"type":"response.completed"%'
      or feedback_log_body like 'SSE event: {"type":"response.failed"%'
      or feedback_log_body like 'session_loop%submission_dispatch{otel.name="op.dispatch.user_input"%'
      or feedback_log_body like 'session_loop%run_sampling_request%'
      or feedback_log_body like 'session_loop%try_run_sampling_request%'
      or feedback_log_body like 'session_loop%stream_request:model_client.stream_responses_api%'
      or feedback_log_body like 'app-server event: item/started%'
      or feedback_log_body like 'app-server event: item/completed%'
    """


def get_last_log_id(logs_db_path: str) -> int:
    if not _logs_db_exists(logs_db_path):
        return 0

    try:
        conn = _connect_logs_db(logs_db_path)
    except sqlite3.Error:
        return 0

    try:
        row = conn.execute("select coalesce(max(id), 0) from logs").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def get_new_desktop_events(logs_db_path: str, last_id: int, limit: int = 200) -> Tuple[List[str], int]:
    if not _logs_db_exists(logs_db_path):
        return [], last_id

    try:
        conn = _connect_logs_db(logs_db_path)
    except sqlite3.Error:
        return [], last_id

    try:
        rows = conn.execute(
            f"""
            select id, feedback_log_body
            from logs
            where id > ?
              and feedback_log_body is not null
              and ({_event_filter_sql()})
            order by id asc
            limit ?
            """,
            (last_id, limit),
        ).fetchall()
    except sqlite3.Error:
        return [], last_id
    finally:
        conn.close()

    events = []
    next_last_id = last_id
    for row_id, body in rows:
        next_last_id = max(next_last_id, int(row_id))
        event = classify_desktop_event(body or "")
        if event is not None:
            events.append(event)
    return events, next_last_id


def get_initial_desktop_state(
    logs_db_path: str,
    now: float,
    window_seconds: int = DEFAULT_BOOTSTRAP_WINDOW_SECONDS,
) -> Tuple[str, int]:
    if not _logs_db_exists(logs_db_path):
        return "idle", 0

    try:
        conn = _connect_logs_db(logs_db_path)
    except sqlite3.Error:
        return "idle", 0

    try:
        last_row = conn.execute("select coalesce(max(id), 0) from logs").fetchone()
        last_id = int(last_row[0]) if last_row else 0
        rows = conn.execute(
            f"""
            select id, feedback_log_body
            from logs
            where ts >= ?
              and feedback_log_body is not null
              and ({_event_filter_sql()})
            order by id asc
            """,
            (int(now - window_seconds),),
        ).fetchall()
    except sqlite3.Error:
        return "idle", 0
    finally:
        conn.close()

    machine = DesktopStateMachine(idle_debounce_seconds=0)
    for _row_id, body in rows:
        event = classify_desktop_event(body or "")
        if event is not None:
            machine.apply(event, now)
    return machine.current_state(now), last_id


def read_jsonl_tail(path: str, max_bytes: int = 128 * 1024) -> List[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    size = file_path.stat().st_size
    offset = max(0, size - max_bytes)
    with file_path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read().decode("utf-8", errors="replace")

    if offset > 0 and "\n" in data:
        data = data.split("\n", 1)[1]

    records = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _rollout_payload_type(record: dict) -> Optional[str]:
    payload = record.get("payload")
    if isinstance(payload, dict):
        payload_type = payload.get("type")
        if isinstance(payload_type, str):
            return payload_type
    record_type = record.get("type")
    return record_type if isinstance(record_type, str) else None


def _rollout_payload(record: dict) -> dict:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def needs_user_attention(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in USER_ATTENTION_KEYWORDS)


def _rollout_message_text(record: dict) -> str:
    payload = _rollout_payload(record)
    for key in ("message", "last_agent_message"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def read_rollout_file_state(
    path: str,
    now: float,
    tail_max_bytes: int = 128 * 1024,
    recent_mtime_window_seconds: float = 5.0,
    unfinished_task_stale_seconds: float = DEFAULT_UNFINISHED_TASK_STALE_SECONDS,
) -> str:
    records = read_jsonl_tail(path, max_bytes=tail_max_bytes)
    if not records:
        return "idle"

    last_task_marker = None
    last_payload_type = None
    last_agent_needs_attention = False
    for record in records:
        payload_type = _rollout_payload_type(record)
        if payload_type is None:
            continue
        last_payload_type = payload_type
        if payload_type == "task_started":
            last_task_marker = "started"
            last_agent_needs_attention = False
        elif payload_type == "agent_message":
            last_agent_needs_attention = needs_user_attention(_rollout_message_text(record))
        elif payload_type == "task_complete":
            if needs_user_attention(_rollout_message_text(record)) or last_agent_needs_attention:
                last_task_marker = "attention"
                continue
            last_task_marker = "complete"
        elif payload_type in ("turn_aborted", "task_aborted"):
            last_task_marker = "complete"
            last_agent_needs_attention = False
        elif payload_type in ("task_failed", "task_error", "task_errored"):
            return "attention"

    if last_task_marker == "started":
        try:
            mtime = Path(path).stat().st_mtime
        except FileNotFoundError:
            return "idle"
        if now - mtime <= recent_mtime_window_seconds:
            return "busy"
        if last_agent_needs_attention:
            return "attention"
        return "busy" if now - mtime <= unfinished_task_stale_seconds else "idle"
    if last_task_marker == "attention":
        return "attention"
    if last_task_marker == "complete":
        return "idle"

    try:
        mtime = Path(path).stat().st_mtime
    except FileNotFoundError:
        return "idle"

    if now - mtime <= recent_mtime_window_seconds and last_payload_type != "task_complete":
        return "busy"
    return "idle"


def get_recent_rollout_files(
    sessions_dir: str,
    now: float,
    active_window_seconds: float = DEFAULT_MAX_BUSY_SECONDS,
    limit: int = 40,
) -> List[Path]:
    root = Path(sessions_dir)
    if not root.exists():
        return []

    files = []
    for path in root.rglob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if now - mtime <= active_window_seconds:
            files.append((mtime, path))
    files.sort(reverse=True, key=lambda item: item[0])
    return [path for _mtime, path in files[:limit]]


def get_rollout_desktop_state(
    sessions_dir: str,
    now: float,
    active_window_seconds: float = DEFAULT_MAX_BUSY_SECONDS,
    unfinished_task_stale_seconds: float = DEFAULT_UNFINISHED_TASK_STALE_SECONDS,
) -> Optional[str]:
    files = get_recent_rollout_files(
        sessions_dir,
        now=now,
        active_window_seconds=active_window_seconds,
    )
    if not files:
        return None

    states = [
        read_rollout_file_state(
            str(path),
            now=now,
            recent_mtime_window_seconds=DEFAULT_POLL_SECONDS * 4,
            unfinished_task_stale_seconds=unfinished_task_stale_seconds,
        )
        for path in files
    ]
    if "attention" in states:
        return "attention"
    if "busy" in states:
        return "busy"
    return "idle"


def discover_serial_port(globber: Optional[Callable[[str], List[str]]] = None) -> Optional[str]:
    expand = globber or glob.glob
    for pattern in SERIAL_PORT_PATTERNS:
        matches = sorted(expand(pattern))
        if matches:
            return matches[0]
    return None


def resolve_serial_port(port: str) -> str:
    if port != "auto":
        return port
    discovered = discover_serial_port()
    if discovered:
        return discovered
    raise FileNotFoundError("No ESP32 USB serial port found.")


def configure_serial_port(port: str, baud_rate: int = DEFAULT_BAUD_RATE) -> None:
    subprocess.run(["stty", "-f", port, str(baud_rate), "raw", "-echo"], check=True)


def send_usb_state(port: str, state: str, baud_rate: int = DEFAULT_BAUD_RATE) -> None:
    if state not in VISIBLE_STATES:
        raise ValueError(f"Unsupported state: {state}")
    resolved_port = resolve_serial_port(port)
    configure_serial_port(resolved_port, baud_rate)
    with open(resolved_port, "wb", buffering=0) as handle:
        handle.write(f"{state}\n".encode("utf-8"))


class PersistentUsbStateSender:
    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud_rate: int = DEFAULT_BAUD_RATE,
        open_settle_seconds: float = DEFAULT_SERIAL_OPEN_SETTLE_SECONDS,
        port_resolver=None,
        configurator=None,
        opener=None,
        sleeper=None,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.open_settle_seconds = open_settle_seconds
        self.port_resolver = port_resolver or resolve_serial_port
        self.configurator = configurator or configure_serial_port
        self.opener = opener or open
        self.sleeper = sleeper or time.sleep
        self.resolved_port = None
        self.handle = None

    def open(self) -> None:
        if self.handle is not None:
            return
        self.resolved_port = self.port_resolver(self.port)
        self.configurator(self.resolved_port, self.baud_rate)
        self.handle = self.opener(self.resolved_port, "wb", buffering=0)
        if self.open_settle_seconds > 0:
            self.sleeper(self.open_settle_seconds)

    def send(self, state: str) -> None:
        if state not in VISIBLE_STATES:
            raise ValueError(f"Unsupported state: {state}")
        self.open()
        try:
            self.handle.write(f"{state}\n".encode("utf-8"))
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.handle is None:
            return
        self.handle.close()
        self.handle = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive a USB Codex Desktop status light on macOS.")
    parser.add_argument("--logs-db", default=DEFAULT_LOGS_DB)
    parser.add_argument("--sessions-dir", default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud-rate", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--serial-open-settle-seconds", type=float, default=DEFAULT_SERIAL_OPEN_SETTLE_SECONDS)
    parser.add_argument("--idle-debounce-seconds", type=float, default=DEFAULT_IDLE_DEBOUNCE_SECONDS)
    parser.add_argument("--resend-seconds", type=float, default=DEFAULT_RESEND_SECONDS)
    parser.add_argument("--bootstrap-window-seconds", type=int, default=DEFAULT_BOOTSTRAP_WINDOW_SECONDS)
    parser.add_argument("--max-busy-seconds", type=float, default=DEFAULT_MAX_BUSY_SECONDS)
    parser.add_argument("--unfinished-task-stale-seconds", type=float, default=DEFAULT_UNFINISHED_TASK_STALE_SECONDS)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-loops", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None, sender=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    now = time.time()
    initial_state, last_id = get_initial_desktop_state(
        args.logs_db,
        now=now,
        window_seconds=args.bootstrap_window_seconds,
    )
    machine = DesktopStateMachine(
        idle_debounce_seconds=args.idle_debounce_seconds,
        max_busy_seconds=args.max_busy_seconds,
        initial_state=initial_state,
    )
    persistent_sender = None
    if sender is None and not args.dry_run:
        persistent_sender = PersistentUsbStateSender(
            args.port,
            args.baud_rate,
            open_settle_seconds=args.serial_open_settle_seconds,
        )

        def send(port, state, baud_rate=DEFAULT_BAUD_RATE):
            persistent_sender.send(state)
    else:
        send = sender or send_usb_state

    last_sent_state = None
    last_sent_at = None
    loop_count = 0

    try:
        while True:
            loop_count += 1
            now = time.time()
            rollout_state = get_rollout_desktop_state(
                args.sessions_dir,
                now=now,
                active_window_seconds=args.max_busy_seconds,
                unfinished_task_stale_seconds=args.unfinished_task_stale_seconds,
            )
            if rollout_state is not None:
                state = rollout_state
            else:
                events, last_id = get_new_desktop_events(args.logs_db, last_id)
                for event in events:
                    machine.apply(event, now)
                state = machine.current_state(now)
            state_changed = state != last_sent_state
            should_send = state_changed
            if (
                not should_send
                and last_sent_at is not None
                and args.resend_seconds >= 0
                and now - last_sent_at >= args.resend_seconds
            ):
                should_send = True

            if should_send:
                if state_changed:
                    print(state, flush=True)
                if not args.dry_run:
                    try:
                        send(args.port, state, baud_rate=args.baud_rate)
                    except Exception as exc:
                        print(f"usb send failed: {exc}", file=sys.stderr, flush=True)
                        time.sleep(max(args.poll_seconds, 1.0))
                        continue
                last_sent_state = state
                last_sent_at = now

            if args.once:
                return 0
            if args.max_loops is not None and loop_count >= args.max_loops:
                return 0

            time.sleep(args.poll_seconds)
    finally:
        if persistent_sender is not None:
            persistent_sender.close()


if __name__ == "__main__":
    sys.exit(main())
