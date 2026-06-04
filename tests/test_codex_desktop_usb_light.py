import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout

from tools.codex_desktop_usb_light import (
    DesktopStateMachine,
    classify_desktop_event,
    get_initial_desktop_state,
    get_new_desktop_events,
    get_rollout_desktop_state,
    main,
    PersistentUsbStateSender,
    read_rollout_file_state,
)


class DesktopEventClassificationTests(unittest.TestCase):
    def test_classifies_structured_sse_events(self):
        self.assertEqual(
            classify_desktop_event('event.name="codex.sse_event" event.kind=response.in_progress'),
            "started",
        )
        self.assertEqual(
            classify_desktop_event('SSE event: {"type":"response.completed","response":{"error":null}}'),
            "completed",
        )
        self.assertEqual(
            classify_desktop_event('SSE event: {"type":"response.failed","response":{"error":{"code":"x"}}}'),
            "failed",
        )

    def test_classifies_preflight_sampling_logs_as_started(self):
        self.assertEqual(
            classify_desktop_event(
                'session_loop{thread_id=thread-1}:submission_dispatch{codex.op="user_input"}:'
                'turn{otel.name="session_task.turn" turn.id=turn-1}:run_turn:'
                'run_sampling_request{turn_id=turn-1 model=gpt-5.5}:try_run_sampling_request{turn_id=turn-1}'
            ),
            "started",
        )

    def test_ignores_failed_text_inside_logged_content(self):
        body = (
            "session_loop{thread_id=thread-1}:run_sampling_request:"
            "Output item item=Message { content: 'response.failed turn error' }"
        )
        self.assertIsNone(classify_desktop_event(body))

    def test_classifies_app_server_fallback_events(self):
        self.assertEqual(classify_desktop_event("app-server event: item/started targeted_connections=1"), "started")
        self.assertEqual(classify_desktop_event("app-server event: item/completed targeted_connections=1"), "completed")


class DesktopStateMachineTests(unittest.TestCase):
    def test_completed_waits_for_quiet_period_before_idle(self):
        machine = DesktopStateMachine(idle_debounce_seconds=1.5)
        machine.apply("started", now=10.0)
        self.assertEqual(machine.current_state(now=10.0), "busy")

        machine.apply("completed", now=11.0)
        self.assertEqual(machine.current_state(now=12.0), "busy")
        self.assertEqual(machine.current_state(now=12.6), "idle")

    def test_new_started_cancels_pending_idle(self):
        machine = DesktopStateMachine(idle_debounce_seconds=1.5)
        machine.apply("started", now=10.0)
        machine.apply("completed", now=11.0)
        machine.apply("started", now=12.0)
        self.assertEqual(machine.current_state(now=20.0), "busy")

    def test_failed_is_attention_until_recovered_or_completed(self):
        machine = DesktopStateMachine(idle_debounce_seconds=1.0)
        machine.apply("failed", now=10.0)
        self.assertEqual(machine.current_state(now=10.0), "attention")
        machine.apply("started", now=11.0)
        self.assertEqual(machine.current_state(now=11.0), "busy")
        machine.apply("failed", now=12.0)
        machine.apply("completed", now=13.0)
        self.assertEqual(machine.current_state(now=14.1), "idle")


class DesktopLogQueryTests(unittest.TestCase):
    def test_reads_only_structured_desktop_events_since_last_id(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as handle:
            conn = sqlite3.connect(handle.name)
            conn.execute(
                """
                create table logs (
                    id integer primary key autoincrement,
                    ts integer not null,
                    ts_nanos integer not null,
                    thread_id text,
                    feedback_log_body text
                )
                """
            )
            conn.execute(
                "insert into logs (ts, ts_nanos, thread_id, feedback_log_body) values (?, ?, ?, ?)",
                (100, 0, None, 'session text contains response.failed but is not an event'),
            )
            conn.execute(
                "insert into logs (ts, ts_nanos, thread_id, feedback_log_body) values (?, ?, ?, ?)",
                (101, 0, None, 'event.name="codex.sse_event" event.kind=response.in_progress'),
            )
            conn.execute(
                "insert into logs (ts, ts_nanos, thread_id, feedback_log_body) values (?, ?, ?, ?)",
                (102, 0, None, 'SSE event: {"type":"response.completed"}'),
            )
            conn.commit()
            conn.close()

            events, last_id = get_new_desktop_events(handle.name, last_id=1)

            self.assertEqual(events, ["started", "completed"])
            self.assertEqual(last_id, 3)

    def test_reads_preflight_sampling_logs_as_started(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as handle:
            conn = sqlite3.connect(handle.name)
            conn.execute(
                """
                create table logs (
                    id integer primary key autoincrement,
                    ts integer not null,
                    ts_nanos integer not null,
                    thread_id text,
                    feedback_log_body text
                )
                """
            )
            conn.execute(
                "insert into logs (ts, ts_nanos, thread_id, feedback_log_body) values (?, ?, ?, ?)",
                (
                    100,
                    0,
                    None,
                    'session_loop{thread_id=thread-1}:submission_dispatch{otel.name="op.dispatch.user_input"}:'
                    'turn{otel.name="session_task.turn"}:run_turn:run_sampling_request{turn_id=turn-1}',
                ),
            )
            conn.commit()
            conn.close()

            events, last_id = get_new_desktop_events(handle.name, last_id=0)

            self.assertEqual(events, ["started"])
            self.assertEqual(last_id, 1)

    def test_initial_state_uses_recent_start_after_completed(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as handle:
            conn = sqlite3.connect(handle.name)
            conn.execute(
                """
                create table logs (
                    id integer primary key autoincrement,
                    ts integer not null,
                    ts_nanos integer not null,
                    thread_id text,
                    feedback_log_body text
                )
                """
            )
            conn.execute(
                "insert into logs (ts, ts_nanos, thread_id, feedback_log_body) values (?, ?, ?, ?)",
                (90, 0, None, 'SSE event: {"type":"response.completed"}'),
            )
            conn.execute(
                "insert into logs (ts, ts_nanos, thread_id, feedback_log_body) values (?, ?, ?, ?)",
                (100, 0, None, 'event.name="codex.sse_event" event.kind=response.in_progress'),
            )
            conn.commit()
            conn.close()

            state, last_id = get_initial_desktop_state(handle.name, now=100, window_seconds=30)

            self.assertEqual(state, "busy")
            self.assertEqual(last_id, 2)

    def test_unopenable_sqlite_fallback_does_not_crash_initial_state(self):
        with tempfile.TemporaryDirectory() as root:
            state, last_id = get_initial_desktop_state(root, now=100, window_seconds=30)

            self.assertEqual(state, "idle")
            self.assertEqual(last_id, 0)

    def test_unopenable_sqlite_fallback_does_not_crash_new_events(self):
        with tempfile.TemporaryDirectory() as root:
            events, last_id = get_new_desktop_events(root, last_id=42)

            self.assertEqual(events, [])
            self.assertEqual(last_id, 42)

    def test_invalid_sqlite_fallback_does_not_crash_initial_state(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as handle:
            handle.write(b"not a sqlite database")
            handle.flush()

            state, last_id = get_initial_desktop_state(handle.name, now=100, window_seconds=30)

            self.assertEqual(state, "idle")
            self.assertEqual(last_id, 0)

    def test_invalid_sqlite_fallback_does_not_crash_new_events(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as handle:
            handle.write(b"not a sqlite database")
            handle.flush()

            events, last_id = get_new_desktop_events(handle.name, last_id=42)

            self.assertEqual(events, [])
            self.assertEqual(last_id, 42)


class DesktopRolloutStateTests(unittest.TestCase):
    def test_started_without_complete_is_busy(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as handle:
            handle.write(
                b'{"timestamp":"2026-06-03T07:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"turn-1"}}\n'
            )
            handle.flush()

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0), "busy")

    def test_stale_started_without_recent_writes_is_idle(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as handle:
            handle.write(
                b'{"timestamp":"2026-06-03T07:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"turn-1"}}\n'
            )
            handle.flush()
            os.utime(handle.name, (80.0, 80.0))

            self.assertEqual(read_rollout_file_state(handle.name, now=300.0, recent_mtime_window_seconds=5.0), "idle")

    def test_started_then_quiet_confirmation_message_is_attention(self):
        records = [
            {"timestamp": "2026-06-03T07:00:00Z", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"timestamp": "2026-06-03T07:00:20Z", "type": "event_msg", "payload": {"type": "agent_message", "message": "确认后我只动一个试点点位。"}},
        ]

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.utime(handle.name, (80.0, 80.0))

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0, recent_mtime_window_seconds=5.0), "attention")

    def test_started_then_active_confirmation_message_is_busy(self):
        records = [
            {"timestamp": "2026-06-03T07:00:00Z", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"timestamp": "2026-06-03T07:00:20Z", "type": "event_msg", "payload": {"type": "agent_message", "message": "确认后我会继续处理。"}},
        ]

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.utime(handle.name, (99.5, 99.5))

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0, recent_mtime_window_seconds=5.0), "busy")

    def test_complete_after_started_is_idle(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as handle:
            handle.write(
                b'{"timestamp":"2026-06-03T07:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"turn-1"}}\n'
                b'{"timestamp":"2026-06-03T07:00:01Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1"}}\n'
            )
            handle.flush()

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0), "idle")

    def test_abort_after_started_is_idle(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as handle:
            handle.write(
                b'{"timestamp":"2026-06-03T07:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"turn-1"}}\n'
                b'{"timestamp":"2026-06-03T07:00:01Z","type":"event_msg","payload":{"type":"turn_aborted","turn_id":"turn-1"}}\n'
            )
            handle.flush()

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0), "idle")

    def test_completion_after_user_confirmation_request_is_attention(self):
        message = (
            "Browser is not available: extension\n\n"
            "按 Chrome 插件的处理流程，下一步需要你确认一下："
            "我可以帮你打开一个 Chrome 窗口并重试连接吗？"
        )
        records = [
            {"timestamp": "2026-06-03T07:00:00Z", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"timestamp": "2026-06-03T07:00:01Z", "type": "event_msg", "payload": {"type": "agent_message", "message": message}},
            {"timestamp": "2026-06-03T07:00:02Z", "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": message}},
        ]

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0), "attention")

    def test_abort_after_user_confirmation_request_is_idle(self):
        message = "下一步需要你确认一下：我可以打开 Chrome 窗口吗？"
        records = [
            {"timestamp": "2026-06-03T07:00:00Z", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"timestamp": "2026-06-03T07:00:01Z", "type": "event_msg", "payload": {"type": "agent_message", "message": message}},
            {"timestamp": "2026-06-03T07:00:02Z", "type": "event_msg", "payload": {"type": "turn_aborted", "turn_id": "turn-1"}},
        ]

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0), "idle")

    def test_recent_unfinished_response_item_is_busy(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as handle:
            handle.write(
                b'{"timestamp":"2026-06-03T07:00:00Z","type":"response_item","payload":{"type":"function_call","name":"exec_command"}}\n'
            )
            handle.flush()

            self.assertEqual(read_rollout_file_state(handle.name, now=100.0, recent_mtime_window_seconds=999999), "busy")

    def test_rollout_state_aggregates_recent_busy_file(self):
        with tempfile.TemporaryDirectory() as root:
            idle_path = f"{root}/rollout-idle.jsonl"
            busy_path = f"{root}/rollout-busy.jsonl"
            with open(idle_path, "wb") as handle:
                handle.write(
                    b'{"timestamp":"2026-06-03T07:00:00Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-1"}}\n'
                )
            with open(busy_path, "wb") as handle:
                handle.write(
                    b'{"timestamp":"2026-06-03T07:00:01Z","type":"event_msg","payload":{"type":"task_started","turn_id":"turn-2"}}\n'
                )

            self.assertEqual(get_rollout_desktop_state(root, now=100.0, active_window_seconds=999999), "busy")


class DesktopUsbLightCliTests(unittest.TestCase):
    def test_persistent_usb_sender_keeps_one_open_handle(self):
        writes = []
        closes = []
        opens = []
        configs = []

        class FakeHandle:
            def write(self, payload):
                writes.append(payload)

            def close(self):
                closes.append(True)

        def fake_open(path, mode, buffering=0):
            opens.append((path, mode, buffering))
            return FakeHandle()

        sender = PersistentUsbStateSender(
            port="auto",
            baud_rate=115200,
            open_settle_seconds=0,
            port_resolver=lambda port: "/dev/test",
            configurator=lambda port, baud_rate: configs.append((port, baud_rate)),
            opener=fake_open,
        )

        sender.send("busy")
        sender.send("idle")
        sender.close()

        self.assertEqual(opens, [("/dev/test", "wb", 0)])
        self.assertEqual(configs, [("/dev/test", 115200)])
        self.assertEqual(writes, [b"busy\n", b"idle\n"])
        self.assertEqual(closes, [True])

    def test_persistent_usb_sender_closes_stale_handle_after_write_failure(self):
        closes = []

        class FailingHandle:
            def write(self, _payload):
                raise OSError(6, "Device not configured")

            def close(self):
                closes.append(True)

        sender = PersistentUsbStateSender(
            port="auto",
            baud_rate=115200,
            open_settle_seconds=0,
            port_resolver=lambda port: "/dev/test",
            configurator=lambda port, baud_rate: None,
            opener=lambda path, mode, buffering=0: FailingHandle(),
        )

        with self.assertRaises(OSError):
            sender.send("busy")

        self.assertEqual(closes, [True])
        self.assertIsNone(sender.handle)

    def test_once_dry_run_prints_initial_state(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as handle:
            conn = sqlite3.connect(handle.name)
            conn.execute(
                """
                create table logs (
                    id integer primary key autoincrement,
                    ts integer not null,
                    ts_nanos integer not null,
                    thread_id text,
                    feedback_log_body text
                )
                """
            )
            conn.commit()
            conn.close()

            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--logs-db", handle.name, "--sessions-dir", "/tmp/does-not-exist-codex-sessions", "--once", "--dry-run"])

            self.assertEqual(code, 0)
            self.assertIn("idle", output.getvalue())

    def test_once_dry_run_works_without_sqlite_fallback_db(self):
        with tempfile.TemporaryDirectory() as root:
            missing_db = f"{root}/missing.sqlite"
            missing_sessions = f"{root}/missing-sessions"

            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--logs-db", missing_db, "--sessions-dir", missing_sessions, "--once", "--dry-run"])

            self.assertEqual(code, 0)
            self.assertIn("idle", output.getvalue())


if __name__ == "__main__":
    unittest.main()
