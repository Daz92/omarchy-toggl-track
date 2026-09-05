import base64
import hashlib
import json
import os
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import toggl_api


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, params=None, body=None, mutation=False):
        self.calls.append((method, path, params, body, mutation))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class CacheClient:
    def __init__(self, token="cache-token"):
        self.account_key = hashlib.sha256(token.encode()).hexdigest()[:32]
        self.responses = {}
        self.calls = []

    def respond(self, path, value):
        self.responses[path] = [value]

    def queue(self, path, *values):
        self.responses[path] = list(values)

    def request(self, method, path, params=None, body=None, mutation=False):
        self.calls.append((method, path, params, body, mutation))
        values = self.responses[path]
        response = values.pop(0) if len(values) > 1 else values[0]
        if isinstance(response, Exception):
            raise response
        return response


class TestClock:
    def __init__(self):
        self.value = datetime(2026, 8, 19, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


def cache_client(token="cache-token"):
    client = CacheClient(token)
    client.respond("/me", {"id": 1, "fullname": "Ada"})
    client.respond("/me/workspaces", [{"id": 4, "name": "Work"}])
    client.respond("/workspaces/4/projects", [{"id": 12, "workspace_id": 4, "name": "Project"}])
    client.respond("/workspaces/4/tasks", {"data": [], "total_count": 0})
    client.respond("/me/time_entries", [])
    client.respond("/workspaces/4/tags", [])
    client.respond("/workspaces/4/clients", [])
    client.respond("/me/time_entries/current", None)
    return client


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def aw_event(timestamp, duration, data):
    return {"timestamp": timestamp, "duration": duration, "data": data}


def aw_opener(buckets, events):
    responses = [Response(buckets)] + [Response(events.get(kind, [])) for kind in ("window", "afk", "web")]

    def opener(request, timeout):
        return responses.pop(0)

    return opener


class TogglApiTests(unittest.TestCase):
    def test_process_frames_one_request_without_waiting_for_stdin_eof(self):
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "toggl_api.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdin = process.stdin
        stdout = process.stdout
        stderr = process.stderr
        try:
            if stdin is None or stdout is None or stderr is None:
                raise RuntimeError("subprocess pipes were not created")
            stdin.write('{"action":"unsupported"}\n')
            stdin.flush()
            process.wait(timeout=2)
            output = stdout.read()
            result = json.loads(output)
            self.assertEqual(process.returncode, 1)
            self.assertEqual(result, {"ok": False, "error": {"message": "unsupported action.", "status": 400, "retryable": False}})
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if stdin is not None:
                stdin.close()
            if stdout is not None:
                stdout.close()
            if stderr is not None:
                stderr.close()

    def test_error_envelope_exits_nonzero(self):
        output = io.StringIO()
        with patch("toggl_api.handle", return_value=toggl_api._error("bootstrap failed", 401, False)), patch(
            "toggl_api.sys.stdin", io.StringIO('{"action":"bootstrap"}')
        ), patch("toggl_api.sys.stdout", output):
            status = toggl_api.main()
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["ok"], False)

    def test_validation(self):
        result = toggl_api.handle({"action": "start", "workspace_id": "bad"}, FakeClient([]))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["status"], 400)
        self.assertFalse(result["error"]["retryable"])

    def test_auth_creation_does_not_put_token_in_request_url(self):
        seen = {}

        def opener(request, timeout):
            seen["request"] = request
            return Response({"id": 1})

        client = toggl_api.TogglClient("secret-token", opener=opener)
        client.request("GET", "/me")
        self.assertEqual(seen["request"].get_header("Authorization"), "Basic " + base64.b64encode(b"secret-token:api_token").decode())
        self.assertNotIn("secret-token", seen["request"].full_url)

    def test_bootstrap_normalization(self):
        client = FakeClient([
            {"id": 7, "fullname": "Ada", "email": "private@example.test"},
            [{"id": 2, "name": "Work"}],
            {"id": 11, "workspace_id": 2, "description": "build", "tags": ["dev"]},
        ])
        result = toggl_api.handle({"action": "bootstrap", "skip_sync": True}, client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["user"]["name"], "Ada")
        self.assertNotIn("email", result["data"]["user"])
        self.assertEqual(result["data"]["current"]["workspace_id"], 2)

    def test_cache_bootstrap_cold_warm_and_forced_requests(self):
        with tempfile.TemporaryDirectory() as root:
            client = cache_client()
            api = toggl_api.TogglAPI(client, cache_root=root, clock=TestClock())

            api.bootstrap({"skip_sync": True})
            self.assertEqual([call[1] for call in client.calls], [
                "/me", "/me/workspaces", "/me/time_entries/current",
            ])
            client.calls.clear()
            api.bootstrap({"skip_sync": True})
            self.assertEqual([call[1] for call in client.calls], ["/me/time_entries/current"])
            client.calls.clear()
            api.bootstrap({"force_refresh": True, "skip_sync": True})
            self.assertEqual([call[1] for call in client.calls], [
                "/me", "/me/workspaces", "/me/time_entries/current",
            ])

    def test_cache_sync_cold_warm_skip_current_and_forced_requests(self):
        with tempfile.TemporaryDirectory() as root:
            client = cache_client()
            api = toggl_api.TogglAPI(client, cache_root=root, clock=TestClock())

            api.sync({"workspace_id": 4})
            expected = [
                "/workspaces/4/projects", "/workspaces/4/tasks",
                "/workspaces/4/tags", "/workspaces/4/clients", "/me/time_entries",
                "/me/time_entries/current",
            ]
            self.assertEqual([call[1] for call in client.calls], expected)
            client.calls.clear()
            api.sync({"workspace_id": 4})
            self.assertEqual([call[1] for call in client.calls], [
                "/me/time_entries", "/me/time_entries/current",
            ])
            client.calls.clear()
            api.sync({"workspace_id": 4, "skip_current": True})
            self.assertEqual([call[1] for call in client.calls], ["/me/time_entries"])
            client.calls.clear()
            api.sync({"workspace_id": 4, "force_refresh": True})
            self.assertEqual([call[1] for call in client.calls], expected)

    def test_expired_workspace_cache_falls_back_after_refresh_failure(self):
        with tempfile.TemporaryDirectory() as root:
            clock = TestClock()
            client = cache_client()
            api = toggl_api.TogglAPI(client, cache_root=root, clock=clock)
            api.sync({"workspace_id": 4})

            clock.value += timedelta(minutes=61)
            client.calls.clear()
            client.queue(
                "/workspaces/4/projects",
                toggl_api.ApiError("temporarily unavailable", 503, True),
            )
            client.queue("/me/time_entries", [{"id": 22, "workspace_id": 4}])
            client.queue("/me/time_entries/current", {"id": 23, "workspace_id": 4})
            result = api.sync({"workspace_id": 4})

            self.assertEqual([call[1] for call in client.calls], [
                "/workspaces/4/projects", "/me/time_entries", "/me/time_entries/current",
            ])
            self.assertEqual(result["cache"]["workspace"], "stale")
            self.assertTrue(result["cache"]["stale"])
            self.assertEqual([entry["id"] for entry in result["entries"]], [22])
            self.assertEqual(result["current"]["id"], 23)

    def test_corrupt_and_mismatched_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            client = cache_client()
            api = toggl_api.TogglAPI(client, cache_root=root, clock=TestClock())
            api.bootstrap({"skip_sync": True})
            account_path = Path(root) / ("account-%s.json" % client.account_key)
            account_path.write_text("not json", encoding="utf-8")
            client.calls.clear()
            api.bootstrap({"skip_sync": True})
            self.assertEqual([call[1] for call in client.calls], [
                "/me", "/me/workspaces", "/me/time_entries/current",
            ])

            account = json.loads(account_path.read_text(encoding="utf-8"))
            account["account_key"] = "0" * 32
            account_path.write_text(json.dumps(account), encoding="utf-8")
            client.calls.clear()
            api.bootstrap({"skip_sync": True})
            self.assertEqual([call[1] for call in client.calls], [
                "/me", "/me/workspaces", "/me/time_entries/current",
            ])

            api.sync({"workspace_id": 4})
            workspace_path = Path(root) / ("workspace-%s-4.json" % client.account_key)
            workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
            workspace["workspace_id"] = 99
            workspace_path.write_text(json.dumps(workspace), encoding="utf-8")
            client.calls.clear()
            api.sync({"workspace_id": 4})
            self.assertEqual([call[1] for call in client.calls], [
                "/workspaces/4/projects", "/workspaces/4/tasks",
                "/workspaces/4/tags", "/workspaces/4/clients", "/me/time_entries",
                "/me/time_entries/current",
            ])

    def test_cache_is_token_isolated_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            token_a = "raw-token-a"
            token_b = "raw-token-b"
            client_a = cache_client(token_a)
            client_b = cache_client(token_b)
            toggl_api.TogglAPI(client_a, cache_root=root, clock=TestClock()).sync({"workspace_id": 4})
            toggl_api.TogglAPI(client_b, cache_root=root, clock=TestClock()).sync({"workspace_id": 4})

            cache_root = Path(root)
            self.assertEqual((cache_root.stat().st_mode & 0o777), 0o700)
            files = list(cache_root.iterdir())
            self.assertEqual(len(files), 4)
            self.assertNotEqual(client_a.account_key, client_b.account_key)
            for path in files:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                contents = path.read_bytes()
                self.assertNotIn(token_a.encode(), contents)
                self.assertNotIn(token_b.encode(), contents)
                self.assertNotIn(token_a, str(path))
                self.assertNotIn(token_b, str(path))
            self.assertFalse(any(path.name.startswith(".omarchy-toggl-") or path.suffix == ".tmp" for path in files))

    def test_sync_paginates_and_pairs_history_dates(self):
        page = [{"id": i, "name": "P%d" % i, "active": i != 0} for i in range(200)]
        client = FakeClient([page, [{"id": 201, "name": "Archived", "archived": True}], {"data": [], "total_count": 0}, [{"id": 1, "name": "tag"}], [{"id": 3, "name": "client"}], [{"id": 8, "workspace_id": 4, "project_id": 201}], None])
        with patch("toggl_api.datetime") as clock:
            clock.now.return_value = datetime(2026, 8, 19, tzinfo=timezone.utc)
            clock.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = toggl_api.handle({"action": "sync", "workspace_id": 4, "days": 30}, client)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["data"]["projects"]), 201)
        self.assertTrue(result["data"]["tasks_available"])
        history_call = next(call for call in client.calls if call[1] == "/me/time_entries")
        self.assertEqual(history_call[2], {"start_date": "2026-07-21", "end_date": "2026-08-19", "meta": "true"})
        self.assertEqual(result["data"]["entries"][0]["project_name"], "Archived")

    def test_task_normalization_preserves_metadata_and_normalizes_color(self):
        task = toggl_api._normalized_task(
            {
                "id": 13,
                "wid": 4,
                "pid": 12,
                "name": "Implement task",
                "active": True,
                "status": "active",
                "at": "2026-08-19T10:00:00Z",
                "estimated_seconds": 3600,
                "tracked_seconds": 123456,
                "client_id": 8,
                "client_name": "Client",
                "project_name": "Project",
                "project_color": "#12AbEf",
                "project_billable": True,
                "project_is_private": False,
                "external_reference": "ref-13",
            }
        )
        self.assertEqual(task["workspace_id"], 4)
        self.assertEqual(task["project_id"], 12)
        self.assertEqual(task["project_color"], "#12abef")
        self.assertEqual(task["tracked_seconds"], 123456)
        self.assertEqual(task["external_reference"], "ref-13")
        self.assertEqual(toggl_api._normalized_task({"project_color": "red"})["project_color"], "")

    def test_sync_paginates_tasks_using_total_count(self):
        first = [{"id": i, "project_id": 1, "name": "Task %d" % i} for i in range(200)]
        second = [{"id": 200 + i, "project_id": 1, "name": "Task %d" % (200 + i)} for i in range(198)]
        client = FakeClient([[], {"data": first, "total_count": 398}, {"data": second, "total_count": 398}, [], [], [], None])
        result = toggl_api.handle({"action": "sync", "workspace_id": 4}, client)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["data"]["tasks"]), 398)
        self.assertTrue(result["data"]["tasks_available"])
        task_calls = [call for call in client.calls if call[1] == "/workspaces/4/tasks"]
        self.assertEqual([call[2] for call in task_calls], [
            {"active": "both", "page": 1, "per_page": 200},
            {"active": "both", "page": 2, "per_page": 200},
        ])

    def test_sync_gracefully_disables_tasks_when_access_is_forbidden(self):
        client = FakeClient([[], toggl_api.ApiError("access denied", 403, False), [], [], [], None])
        result = toggl_api.handle({"action": "sync", "workspace_id": 4}, client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["tasks"], [])
        self.assertFalse(result["data"]["tasks_available"])

    def test_sync_enriches_entries_and_current_from_fetched_maps(self):
        client = FakeClient([
            [{"id": 12, "name": "Project", "client_id": 8, "client_name": "Client"}],
            {"data": [{"id": 13, "project_id": 12, "name": "Task", "client_id": 8}], "total_count": 1},
            [],
            [{"id": 8, "name": "Client"}],
            [{"id": 1, "workspace_id": 4, "project_id": 12, "task_id": 13}],
            {"workspace_id": 4, "project_id": 12, "task_id": 13},
        ])
        result = toggl_api.handle({"action": "sync", "workspace_id": 4}, client)
        self.assertTrue(result["ok"])
        entry = result["data"]["entries"][0]
        self.assertEqual((entry["task_name"], entry["client_name"]), ("Task", "Client"))
        self.assertEqual((result["data"]["current"]["task_name"], result["data"]["current"]["client_name"]), ("Task", "Client"))

    def test_sync_enriches_tasks_from_projects_and_clients(self):
        client = FakeClient([
            [{"id": 12, "name": "Project", "client_id": 8, "billable": True, "is_private": False, "color": "#12AbEf"}],
            {"data": [{"id": 13, "project_id": 12, "name": "Task"}], "total_count": 1},
            [],
            [{"id": 8, "name": "Client from map"}],
            [{"id": 1, "workspace_id": 4, "project_id": 12, "task_id": 13}],
            {"workspace_id": 4, "project_id": 12, "task_id": 13},
        ])
        result = toggl_api.handle({"action": "sync", "workspace_id": 4}, client)
        self.assertTrue(result["ok"])
        task = result["data"]["tasks"][0]
        self.assertEqual(
            {task[field] for field in ("project_name", "project_color", "client_id", "client_name")},
            {"Project", "#12abef", 8, "Client from map"},
        )
        self.assertEqual((task["project_billable"], task["project_is_private"]), (True, False))
        self.assertEqual(result["data"]["entries"][0]["client_name"], "Client from map")
        self.assertEqual(result["data"]["current"]["client_name"], "Client from map")

    def test_sync_keeps_explicit_task_metadata(self):
        client = FakeClient([
            [{"id": 12, "name": "Parent", "client_id": 8, "client_name": "Parent client", "billable": True, "is_private": True, "color": "#123456"}],
            {"data": [{
                "id": 13,
                "project_id": 12,
                "name": "Task",
                "client_id": 9,
                "client_name": "Task client",
                "project_name": "Task project",
                "project_color": "#abcdef",
                "project_billable": False,
                "project_is_private": False,
            }], "total_count": 1},
            [],
            [],
            [{"id": 9, "name": "Other client"}],
            None,
        ])
        result = toggl_api.handle({"action": "sync", "workspace_id": 4}, client)
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["data"]["tasks"][0],
            {
                "id": 13,
                "workspace_id": None,
                "project_id": 12,
                "name": "Task",
                "active": True,
                "status": "active",
                "at": None,
                "estimated_seconds": None,
                "tracked_seconds": None,
                "client_id": 9,
                "client_name": "Task client",
                "project_name": "Task project",
                "project_color": "#abcdef",
                "project_billable": False,
                "project_is_private": False,
                "external_reference": None,
            },
        )

    def test_project_normalization_preserves_metadata(self):
        project = toggl_api._normalized_project(
            {
                "id": 12,
                "workspace_id": 4,
                "name": "Website",
                "client_id": 8,
                "client_name": "Acme",
                "active": True,
                "billable": True,
                "status": "active",
                "is_private": True,
                "external_reference": "crm-12",
                "created_at": "2026-01-02T03:04:05Z",
                "at": "2026-01-03T03:04:05Z",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "estimated_hours": 40,
                "estimated_seconds": 144000,
                "fixed_fee": 1200.5,
                "color": "#12AbEf",
            }
        )
        self.assertEqual(
            project,
            {
                "id": 12,
                "workspace_id": 4,
                "name": "Website",
                "client_id": 8,
                "client_name": "Acme",
                "client": "Acme",
                "archived": False,
                "active": True,
                "status": "active",
                "is_private": True,
                "external_reference": "crm-12",
                "created_at": "2026-01-02T03:04:05Z",
                "at": "2026-01-03T03:04:05Z",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "estimated_hours": 40,
                "estimated_seconds": 144000,
                "fixed_fee": 1200.5,
                "billable": True,
                "color": "#12abef",
            },
        )

    def test_project_status_falls_back_to_activity(self):
        self.assertEqual(toggl_api._normalized_project({"active": False})["status"], "archived")
        self.assertEqual(toggl_api._normalized_project({"active": True, "status": ""})["status"], "active")

    def test_project_color_preserves_valid_six_digit_value(self):
        self.assertEqual(toggl_api._normalized_project({"color": "#aBcD09"})["color"], "#abcd09")

    def test_project_color_falls_back_for_invalid_values(self):
        self.assertEqual(toggl_api._normalized_project({"color": "red"})["color"], "")
        self.assertEqual(toggl_api._normalized_project({})["color"], "")

    def test_project_optional_metadata_is_nullable(self):
        project = toggl_api._normalized_project({"name": "Minimal"})
        for field in (
            "is_private",
            "external_reference",
            "created_at",
            "at",
            "start_date",
            "end_date",
            "estimated_hours",
            "estimated_seconds",
            "fixed_fee",
        ):
            self.assertIsNone(project[field])

    def test_sync_filters_history_workspace_but_keeps_current(self):
        client = FakeClient([
            [],
            {"data": [], "total_count": 0},
            [],
            [],
            [{"id": 8, "wid": 4, "pid": 12, "task_id": 13, "tags": ["one"], "billable": True}],
            {"id": 99, "wid": 9, "description": "other workspace"},
        ])
        result = toggl_api.handle({"action": "sync", "workspace_id": 4}, client)
        self.assertTrue(result["ok"])
        self.assertEqual([entry["id"] for entry in result["data"]["entries"]], [8])
        self.assertEqual(result["data"]["entries"][0]["project_id"], 12)
        self.assertEqual(result["data"]["entries"][0]["task_id"], 13)
        self.assertEqual(result["data"]["entries"][0]["tags"], ["one"])
        self.assertTrue(result["data"]["entries"][0]["billable"])
        self.assertEqual(result["data"]["current"]["workspace_id"], 9)

    def test_legacy_data_envelope_merges_with_top_level_precedence(self):
        client = FakeClient([[], {"data": [], "total_count": 0}, [], [], [], None])
        with patch("toggl_api.datetime") as clock:
            clock.now.return_value = datetime(2026, 8, 19, tzinfo=timezone.utc)
            clock.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            result = toggl_api.handle(
                {"action": "sync", "workspace_id": 4, "data": {"workspace_id": 8, "days": 90}}, client
            )
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[0][1], "/workspaces/4/projects")
        history_call = next(call for call in client.calls if call[1] == "/me/time_entries")
        self.assertEqual(history_call[2], {"start_date": "2026-05-22", "end_date": "2026-08-19", "meta": "true"})

    def test_legacy_data_envelope_rejects_non_object(self):
        result = toggl_api.handle({"action": "sync", "data": []}, FakeClient([]))
        self.assertEqual(result["error"]["message"], "data must be an object.")

    def test_start_stops_current_then_creates(self):
        client = FakeClient([
            {"id": 10, "workspace_id": 3, "description": "old"},
            {"id": 10, "workspace_id": 3, "stop": "2026-08-19T10:00:00Z"},
            {"id": 11, "workspace_id": 3, "description": "new"},
        ])
        with patch("toggl_api._now", return_value="2026-08-19T10:00:00Z"):
            result = toggl_api.handle({"action": "start", "workspace_id": 3, "description": "new", "project_id": None, "tags": ["one"], "billable": True}, client)
        self.assertTrue(result["ok"])
        self.assertEqual(client.calls[1][0:2], ("PATCH", "/workspaces/3/time_entries/10/stop"))
        self.assertEqual(client.calls[2][0:2], ("POST", "/workspaces/3/time_entries"))
        self.assertEqual(client.calls[2][3]["duration"], -1)
        self.assertEqual(client.calls[2][3]["created_with"], "omarchy-shell")

    def test_start_rejects_task_without_project(self):
        result = toggl_api.handle(
            {"action": "start", "workspace_id": 3, "description": "task", "task_id": 10},
            FakeClient([]),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["status"], 400)
        self.assertIn("project_id", result["error"]["message"])

    def test_continue_rejects_task_without_project(self):
        result = toggl_api.handle(
            {
                "action": "continue",
                "workspace_id": 3,
                "entry": {"description": "task", "task_id": 10},
            },
            FakeClient([]),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["status"], 400)

    def test_mutation_does_not_retry(self):
        error = HTTPError("https://example.test", 500, "error", Message(), BytesIO(b"secret response"))
        sleeps = []
        client = toggl_api.TogglClient("token", opener=lambda *args, **kwargs: (_ for _ in ()).throw(error), sleep=sleeps.append)
        with self.assertRaises(toggl_api.ApiError) as raised:
            client.request("POST", "/workspaces/1/time_entries", body={}, mutation=True)
        self.assertEqual(raised.exception.status, 500)
        self.assertFalse(sleeps)

    def test_400_body_surfaces_verbatim(self):
        error = HTTPError(
            "https://example.test", 400, "Bad Request", Message(),
            BytesIO(b"start_date must not be earlier than 2026-06-04"),
        )
        client = toggl_api.TogglClient(
            "token",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(error),
            sleep=lambda *_: None,
        )
        with self.assertRaises(toggl_api.ApiError) as raised:
            client.request("GET", "/me/time_entries", mutation=False)
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(raised.exception.message, "start_date must not be earlier than 2026-06-04")

    def test_400_with_no_body_falls_back_to_generic_message(self):
        error = HTTPError("https://example.test", 400, "Bad Request", Message(), BytesIO(b""))
        client = toggl_api.TogglClient(
            "token",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(error),
            sleep=lambda *_: None,
        )
        with self.assertRaises(toggl_api.ApiError) as raised:
            client.request("GET", "/me/time_entries", mutation=False)
        self.assertEqual(raised.exception.message, "Toggl rejected the request.")

    def test_continue_preserves_editable_fields(self):
        client = FakeClient([
            {"id": 1, "workspace_id": 8},
            {"id": 1, "workspace_id": 8, "stop": "2026-08-19T10:00:00Z"},
            {"id": 2, "workspace_id": 8},
        ])
        entry = {"id": 44, "description": "old work", "project_id": 9, "task_id": 10, "tags": ["a"], "billable": True}
        with patch("toggl_api._now", return_value="2026-08-19T10:00:00Z"):
            result = toggl_api.handle({"action": "continue", "workspace_id": 8, "entry": entry}, client)
        self.assertTrue(result["ok"])
        body = client.calls[2][3]
        self.assertEqual({body[k] for k in ("description", "project_id", "task_id", "billable")}, {"old work", 9, 10, True})
        self.assertEqual(body["tags"], ["a"])

    def test_error_envelope_and_missing_token(self):
        result = toggl_api.handle({"action": "bootstrap"}, FakeClient([toggl_api.ApiError("safe", 503, True)]))
        self.assertEqual(result, {"ok": False, "error": {"message": "safe", "status": 503, "retryable": True}})
        # The diagnosis asks D-Bus what is actually wrong, so it is pinned here
        # rather than left to whatever keyring the test machine happens to run.
        with patch("toggl_api.subprocess.run", return_value=type("R", (), {"stdout": "", "returncode": 1})()), \
             patch("toggl_api._token_diagnosis", return_value="Toggl API token not found; run setup first."):
            result = toggl_api.handle({"action": "bootstrap"})
        self.assertFalse(result["ok"])
        self.assertIn("run setup", result["error"]["message"])

    def test_a_locked_keyring_is_refused_before_secret_tool_can_summon_a_prompt(self):
        # `secret-tool lookup` against a locked collection blocks on a GUI
        # password dialog until someone answers it. The panel runs this with
        # stdin closed on a ten-second leash, so the wait would end in a
        # timeout with a dialog stranded on screen and nothing to explain it.
        import toggl_secret

        with patch.object(toggl_secret, "mode", return_value=toggl_secret.MODE_SECURE), \
             patch.object(toggl_secret, "secure_ready",
                          return_value=(None, "the keyring is locked; unlock it with: setup --unlock")), \
             patch("toggl_api.subprocess.run") as run:
            result = toggl_api.handle({"action": "bootstrap"})
        run.assert_not_called()
        self.assertIn("setup --unlock", result["error"]["message"])

    def test_the_default_keyring_path_never_pays_for_the_lock_check(self):
        import toggl_secret

        with patch.object(toggl_secret, "mode", return_value=toggl_secret.MODE_DEFAULT), \
             patch.object(toggl_secret, "secure_ready") as ready:
            self.assertIsNone(toggl_api._secure_keyring_block())
        ready.assert_not_called()

    def test_a_diagnosis_that_cannot_run_leaves_the_old_message_standing(self):
        with patch.dict(sys.modules, {"toggl_secret": None}):
            self.assertIn("run setup", toggl_api._token_diagnosis())

    def test_forbidden_does_not_request_token_replacement(self):
        self.assertIn("workspace permissions", toggl_api._http_message(403))
        self.assertNotIn("refresh", toggl_api._http_message(403))

    def test_activity_intersects_not_afk_and_discards_idle(self):
        start = "2026-08-19T10:00:00Z"
        afk = [
            aw_event(start, 300, {"status": "not-afk"}),
            aw_event("2026-08-19T10:05:00Z", 120, {"status": "afk"}),
            aw_event("2026-08-19T10:07:00Z", 300, {"status": "not-afk"}),
        ]
        window = [aw_event(start, 720, {"app": "Editor", "title": "work"})]
        # The 2 min idle sits inside the default 5 min break, so it stays one
        # block whose active time excludes the idle.
        blocks = toggl_api.segment_blocks(window, afk)
        self.assertEqual([block["seconds"] for block in blocks], [600])
        self.assertEqual(blocks[0]["span_seconds"], 720)
        # A break shorter than the idle splits it.
        blocks = toggl_api.segment_blocks(window, afk, config={"min_block_minutes": 1})
        self.assertEqual([block["seconds"] for block in blocks], [300, 300])

    def test_activity_sorts_descending_events_and_bridges_fragments(self):
        blocks = toggl_api.segment_blocks(
            [
                aw_event("2026-08-19T10:05:05Z", 300, {"app": "Editor", "title": "two"}),
                aw_event("2026-08-19T10:00:00Z", 300, {"app": "Editor", "title": "one"}),
            ],
            [aw_event("2026-08-19T10:00:00Z", 605, {"status": "not-afk"})],
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["seconds"], 600)
        self.assertEqual(toggl_api._event_datetime("2026-08-19T10:00:00.604728640Z").microsecond, 604728)

    def test_activity_groups_across_apps_within_one_block(self):
        # The point of the block model: switching editor -> terminal -> chat is
        # one piece of work, not three, so they must not become separate rows.
        blocks = toggl_api.segment_blocks(
            [
                aw_event("2026-08-19T10:00:00Z", 400, {"app": "Editor", "title": "spec"}),
                aw_event("2026-08-19T10:07:00Z", 200, {"app": "Terminal", "title": "build"}),
                aw_event("2026-08-19T10:11:00Z", 100, {"app": "Chat", "title": "standup"}),
            ],
            [aw_event("2026-08-19T10:00:00Z", 900, {"status": "not-afk"})],
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["seconds"], 700)
        self.assertEqual(
            blocks[0]["apps"],
            [
                {"name": "Editor", "seconds": 400},
                {"name": "Terminal", "seconds": 200},
                {"name": "Chat", "seconds": 100},
            ],
        )
        self.assertEqual(blocks[0]["label"], "spec")
        self.assertEqual(
            [(topic["name"], topic["seconds"]) for topic in blocks[0]["topics"]],
            [("spec", 400), ("build", 200), ("standup", 100)],
        )

    def test_activity_break_threshold_splits_blocks(self):
        events = [
            aw_event("2026-08-19T10:00:00Z", 300, {"app": "Editor", "title": "a"}),
            aw_event("2026-08-19T10:20:00Z", 300, {"app": "Editor", "title": "b"}),
        ]
        afk = [
            aw_event("2026-08-19T10:00:00Z", 300, {"status": "not-afk"}),
            aw_event("2026-08-19T10:20:00Z", 300, {"status": "not-afk"}),
        ]
        self.assertEqual(len(toggl_api.segment_blocks(events, afk, config={"min_block_minutes": 5})), 2)
        self.assertEqual(len(toggl_api.segment_blocks(events, afk, config={"min_block_minutes": 20})), 1)

    def test_activity_keeps_all_active_time_regardless_of_break(self):
        # Grouping by app used to discard sub-minimum slots, losing half a real
        # day. Blocks must account for every active second at any setting.
        events = [
            aw_event("2026-08-19T10:%02d:00Z" % minute, 30, {"app": "App%d" % minute, "title": "t%d" % minute})
            for minute in range(0, 40, 2)
        ]
        afk = [aw_event("2026-08-19T10:00:00Z", 2400, {"status": "not-afk"})]
        for minutes in (1, 2, 5, 10, 15):
            blocks = toggl_api.segment_blocks(events, afk, config={"min_block_minutes": minutes})
            self.assertEqual(sum(block["seconds"] for block in blocks), 20 * 30, minutes)

    def test_activity_ranks_topics_by_duration_and_labels_with_the_top(self):
        blocks = toggl_api.segment_blocks(
            [
                aw_event("2026-08-19T10:00:00Z", 100, {"app": "Editor", "title": "minor"}),
                aw_event("2026-08-19T10:01:40Z", 300, {"app": "Editor", "title": "major"}),
            ],
            [aw_event("2026-08-19T10:00:00Z", 400, {"status": "not-afk"})],
        )
        self.assertEqual([topic["name"] for topic in blocks[0]["topics"]], ["major", "minor"])
        self.assertEqual(blocks[0]["label"], "major")

    def test_topic_strips_browser_and_document_suffixes_and_unread_counters(self):
        self.assertEqual(toggl_api._topic("zen", "(3) NX8 board - Jira \u2014 Zen Browser"), "NX8 board - Jira")
        self.assertEqual(toggl_api._topic("zen", "Scope of Work - Google Docs \u2014 Zen Browser"), "Scope of Work")
        self.assertEqual(toggl_api._topic("zen", "Inbox - Google Chrome"), "Inbox")
        # A hyphenated title that merely looks like a suffix must survive.
        self.assertEqual(toggl_api._topic("zen", "nx8-server - Bitbucket"), "nx8-server - Bitbucket")
        self.assertEqual(toggl_api._topic("com.mitchellh.ghostty", ""), "com.mitchellh.ghostty")

    def test_activity_excludes_screensaver_and_lock_surfaces(self):
        blocks = toggl_api.segment_blocks(
            [
                aw_event("2026-08-19T10:00:00Z", 300, {"app": "org.omarchy.screensaver", "title": "idle"}),
                aw_event("2026-08-19T10:05:00Z", 300, {"app": "Editor", "title": "work"}),
            ],
            [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})],
        )
        self.assertEqual([block["label"] for block in blocks], ["work"])
        self.assertEqual(blocks[0]["seconds"], 300)

    def test_activity_domain_strips_url_and_excludes_incognito(self):
        blocks = toggl_api.segment_blocks(
            [aw_event("2026-08-19T10:00:00Z", 600, {"app": "Google Chrome", "title": "tabs"})],
            [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})],
            [
                aw_event("2026-08-19T10:00:00Z", 200, {"url": "https://example.test/path?q=1#fragment"}),
                aw_event("2026-08-19T10:03:20Z", 280, {"url": "https://private.test/secret", "incognito": True}),
            ],
        )
        self.assertEqual(blocks[0]["domain"], "example.test")

    def test_browser_app_covers_forks_without_matching_lookalikes(self):
        for app in ("zen", "app.zen_browser.zen", "Google Chrome", "firefox", "org.mozilla.librewolf", "vivaldi-stable"):
            self.assertTrue(toggl_api._browser_app(app), app)
        for app in ("zenity", "com.mitchellh.ghostty", "slack", "md.obsidian.Obsidian", ""):
            self.assertFalse(toggl_api._browser_app(app), app)

    def test_activity_domain_enriches_non_chromium_browser(self):
        blocks = toggl_api.segment_blocks(
            [aw_event("2026-08-19T10:00:00Z", 600, {"app": "zen", "title": "Jira"})],
            [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})],
            [aw_event("2026-08-19T10:00:00Z", 400, {"url": "https://bitbucket.org/team/repo/src"})],
        )
        self.assertEqual(blocks[0]["domain"], "bitbucket.org")

    def test_activity_domain_skipped_when_no_browser_in_block(self):
        blocks = toggl_api.segment_blocks(
            [aw_event("2026-08-19T10:00:00Z", 600, {"app": "com.mitchellh.ghostty", "title": "vim"})],
            [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})],
            [aw_event("2026-08-19T10:00:00Z", 400, {"url": "https://bitbucket.org/team/repo/src"})],
        )
        self.assertEqual(blocks[0]["domain"], "")

    def test_day_activity_marks_overlapping_block_applied(self):
        buckets = [
            {"id": "windows", "type": "currentwindow"},
            {"id": "afk", "type": "afkstatus"},
        ]
        opener = aw_opener(
            buckets,
            {
                "window": [aw_event("2026-08-19T10:00:00Z", 600, {"app": "Editor", "title": "work"})],
                "afk": [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})],
                "web": [],
            },
        )
        client = FakeClient([[{"id": 12, "workspace_id": 4, "start": "2026-08-19T10:05:00Z", "stop": "2026-08-19T10:06:00Z", "description": "existing"}]])
        with patch("toggl_api.urlopen", side_effect=opener):
            result = toggl_api.handle(
                {"action": "day_activity", "date": "2026-08-19", "workspace_id": 4}, client
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["blocks"][0]["applied"])
        self.assertEqual(result["data"]["blocks"][0]["conflict"]["id"], 12)

    def test_day_activity_marks_applied_and_respects_half_open_boundary(self):
        buckets = [{"id": "windows", "type": "currentwindow"}, {"id": "afk", "type": "afkstatus"}]
        responses = [
            Response(buckets),
            Response([aw_event("2026-08-19T10:00:00Z", 600, {"app": "Editor", "title": "work"})]),
            Response([aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})]),
        ]
        def opener(request, timeout):
            return responses.pop(0)
        client = FakeClient([[{"id": 12, "workspace_id": 4, "start": "2026-08-19T09:00:00Z", "stop": "2026-08-19T10:00:00Z", "description": "before"}]])
        api = toggl_api.TogglAPI(client, activitywatch_opener=opener)
        result = api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4})
        self.assertFalse(result["blocks"][0]["applied"])
        self.assertNotIn("conflict", result["blocks"][0])

    def test_day_activity_handles_empty_and_absent_buckets(self):
        responses = [Response([])]
        api = toggl_api.TogglAPI(FakeClient([[]]), activitywatch_opener=lambda request, timeout: responses.pop(0))
        result = api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4})
        self.assertEqual(result["blocks"], [])

    def test_day_activity_aw_unreachable_is_structured(self):
        with patch("toggl_api.urlopen", side_effect=URLError("down")):
            result = toggl_api.handle({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4}, FakeClient([]))
        self.assertFalse(result["ok"])
        self.assertIn("ActivityWatch", result["error"]["message"])

    def test_day_bounds_use_local_dst_transition(self):
        with patch.dict("os.environ", {"TZ": "America/New_York"}, clear=False):
            start, end = toggl_api._day_bounds("2026-11-01")
        self.assertEqual((end - start).total_seconds(), 25 * 3600)
        self.assertEqual(start.isoformat(), "2026-11-01T04:00:00+00:00")

    def test_create_entry_posts_completed_entry_without_stopping_current(self):
        client = FakeClient([[], {"id": 7, "workspace_id": 4, "description": "history"}])
        result = toggl_api.handle(
            {
                "action": "create_entry", "workspace_id": 4, "start": "2026-08-19T10:00:00Z",
                "duration": 300, "description": "history", "project_id": None, "tags": [], "billable": False,
            },
            client,
        )
        self.assertTrue(result["ok"])
        self.assertEqual([call[0] for call in client.calls], ["GET", "POST"])
        body = client.calls[1][3]
        self.assertGreater(body["duration"], 0)
        self.assertEqual(body["created_with"], "omarchy-toggl-track/day")
        self.assertEqual(body["stop"], "2026-08-19T10:05:00Z")

    def test_create_entry_conflict_does_not_post(self):
        client = FakeClient([[{"id": 9, "workspace_id": 4, "start": "2026-08-19T10:01:00Z", "stop": "2026-08-19T10:03:00Z"}]])
        result = toggl_api.handle(
            {"action": "create_entry", "workspace_id": 4, "start": "2026-08-19T10:00:00Z", "duration": 300, "description": "x"}, client
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["status"], 409)
        self.assertEqual(len(client.calls), 1)

    def test_create_entry_mutation_does_not_retry_on_5xx_or_timeout(self):
        error = HTTPError("https://example.test", 500, "error", Message(), BytesIO(b"failure"))
        calls = []
        sleeps = []

        def opener(request, timeout):
            calls.append(request.get_method())
            if request.get_method() == "GET":
                return Response([])
            raise error

        client = toggl_api.TogglClient("token", opener=opener, sleep=sleeps.append)
        with self.assertRaises(toggl_api.ApiError):
            toggl_api.TogglAPI(client).create_entry(
                {"workspace_id": 4, "start": "2026-08-19T10:00:00Z", "duration": 60, "description": "x"}
            )
        self.assertEqual(calls, ["GET", "POST"])
        self.assertEqual(sleeps, [])


class LoggingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _records(self):
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def test_action_is_logged_with_timing_and_ok(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}], {}])
        toggl_api.handle({"action": "bootstrap", "skip_sync": True}, client=client, logger=logger)
        record = [r for r in self._records() if r.get("action") == "bootstrap"][0]
        self.assertTrue(record["ok"])
        self.assertIsInstance(record["ms"], int)

    def test_failure_is_logged_with_status(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([toggl_api.ApiError("nope", 400, False)])
        result = toggl_api.handle({"action": "bootstrap"}, client=client, logger=logger)
        self.assertFalse(result["ok"])
        record = [r for r in self._records() if r.get("action") == "bootstrap"][0]
        self.assertFalse(record["ok"])
        self.assertEqual(record["status"], 400)

    def test_token_never_reaches_the_log(self):
        import toggl_log

        class StubResponse:
            status = 200

            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def read(self):
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            url = request.full_url
            self.assertNotIn(secret, url)
            if "/me/workspaces" in url:
                return StubResponse([{"id": 7, "name": "w"}])
            if "/me/time_entries/current" in url:
                return StubResponse(None)
            return StubResponse({"id": 1, "fullname": "Ada", "default_workspace_id": 7})

        secret = "s3cr3t-token-value"
        logger = toggl_log.Logger(self.tmp.name, "debug")
        client = toggl_api.TogglClient(secret, opener=opener, logger=logger)
        # Drives a real request end to end -- account fetch plus the http
        # logging it triggers -- before asserting the whole log file is clean.
        result = toggl_api.handle(
            {"action": "bootstrap", "skip_sync": True},
            client=client, cache_root=self.tmp.name, logger=logger,
        )
        self.assertTrue(result["ok"])
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        contents = path.read_text()
        self.assertNotIn(secret, contents)
        self.assertNotIn(client.account_key, secret)

    def test_client_log_entries_are_flushed_with_src_qml(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}], {}])
        toggl_api.handle(
            {"action": "bootstrap", "client_log": [{"lvl": "errors", "event": "request_dropped"}]},
            client=client, logger=logger,
        )
        qml = [r for r in self._records() if r.get("src") == "qml"]
        self.assertEqual(len(qml), 1)
        self.assertEqual(qml[0]["event"], "request_dropped")

    def test_client_log_is_capped_at_32_entries(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}], {}])
        toggl_api.handle(
            {"action": "bootstrap", "client_log": [{"lvl": "errors", "event": "e%d" % i} for i in range(80)]},
            client=client, logger=logger,
        )
        self.assertEqual(len([r for r in self._records() if r.get("src") == "qml"]), 32)

    def test_logging_failure_does_not_break_the_request(self):
        class Exploding:
            def enabled(self, level):
                return True

            def write(self, level, **fields):
                raise OSError("disk full")

        client = FakeClient([{"id": 1, "default_workspace_id": 7}, [{"id": 7, "name": "w"}], {}])
        result = toggl_api.handle({"action": "bootstrap", "skip_sync": True}, client=client, logger=Exploding())
        self.assertTrue(result["ok"])

    def test_lazily_constructed_client_receives_the_logger(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        api = toggl_api.TogglAPI(None, logger=logger)
        with patch.object(toggl_api, "_load_token", return_value="tkn"):
            self.assertIs(api.client._logger, logger)

    def test_http_call_is_logged_with_path_not_url(self):
        import toggl_log

        class StubResponse:
            status = 200

            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def read(self):
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            return StubResponse({"id": 1})

        secret = "http-log-token"
        logger = toggl_log.Logger(self.tmp.name, "info")
        client = toggl_api.TogglClient(secret, opener=opener, logger=logger)
        client.request("GET", "/me", params={"since": "2026-01-01"})

        records = [r for r in self._records() if "http" in r]
        self.assertEqual(len(records), 1)
        entry = records[0]["http"][0]
        self.assertEqual(entry["path"], "/me")
        self.assertNotIn("url", entry)
        self.assertEqual(entry["status"], 200)
        self.assertIsInstance(entry["ms"], int)
        self.assertGreater(entry["bytes"], 0)
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        self.assertNotIn(secret, path.read_text())


class BootstrapFoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _api(self, client=None):
        client = client or cache_client()
        return toggl_api.TogglAPI(
            client, cache_root=self.tmp.name, clock=TestClock()), client

    def test_bootstrap_returns_sync_data_in_one_call(self):
        api, _ = self._api()
        data = api.bootstrap({})
        for key in ("user", "workspaces", "projects", "tasks_available", "entries"):
            self.assertIn(key, data)
        self.assertEqual(data["workspace_id"], 4)

    def test_bootstrap_makes_the_project_request_itself(self):
        api, client = self._api()
        api.bootstrap({})
        self.assertIn("/workspaces/4/projects", [call[1] for call in client.calls])

    def test_bootstrap_fetches_current_exactly_once(self):
        api, client = self._api()
        api.bootstrap({})
        current_calls = [call for call in client.calls if call[1] == "/me/time_entries/current"]
        self.assertEqual(len(current_calls), 1)

    def test_bootstrap_with_skip_sync_returns_only_account_data(self):
        api, client = self._api()
        data = api.bootstrap({"skip_sync": True})
        self.assertIn("workspaces", data)
        self.assertNotIn("projects", data)
        self.assertNotIn("/workspaces/4/projects", [call[1] for call in client.calls])

    def test_handle_bootstrap_with_workspace_id_zero_prefers_the_user_default(self):
        # Drives the real entry point with the exact payload a fresh install
        # (or any cleared-workspace state) sends: workspace_id 0. Regression
        # for _id's required=False branch only special-casing None, which
        # made a supplied 0 raise ValidationError and deadlock bootstrap.
        client = cache_client()
        client.respond("/me", {"id": 1, "fullname": "Ada", "default_workspace_id": 9})
        client.respond("/me/workspaces", [{"id": 4, "name": "Work"}, {"id": 9, "name": "Personal"}])
        client.respond("/workspaces/9/projects", [])
        client.respond("/workspaces/9/tasks", {"data": [], "total_count": 0})
        client.respond("/workspaces/9/tags", [])
        client.respond("/workspaces/9/clients", [])
        result = toggl_api.handle(
            {"action": "bootstrap", "workspace_id": 0},
            client=client, cache_root=self.tmp.name, clock=TestClock(),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["workspace_id"], 9)

    def test_handle_bootstrap_with_workspace_id_omitted_does_not_fail(self):
        client = cache_client()
        result = toggl_api.handle(
            {"action": "bootstrap"}, client=client, cache_root=self.tmp.name, clock=TestClock(),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["workspace_id"], 4)

    def test_bootstrap_without_a_choosable_workspace_skips_sync(self):
        client = cache_client()
        client.respond("/me/workspaces", [])
        api, _ = self._api(client=client)
        data = api.bootstrap({})
        self.assertNotIn("projects", data)

    def test_a_failing_sync_still_returns_account_data(self):
        client = cache_client()
        client.respond("/workspaces/4/projects", toggl_api.ApiError("down", 500, True))
        api, _ = self._api(client=client)
        data = api.bootstrap({})
        self.assertIn("workspaces", data)
        self.assertNotIn("projects", data)

    def test_a_failing_sync_marks_sync_failed(self):
        client = cache_client()
        client.respond("/workspaces/4/projects", toggl_api.ApiError("down", 500, True))
        api, _ = self._api(client=client)
        data = api.bootstrap({})
        self.assertTrue(data.get("sync_failed"))

    def test_a_successful_bootstrap_does_not_mark_sync_failed(self):
        api, _ = self._api()
        data = api.bootstrap({})
        self.assertNotIn("sync_failed", data)

    def test_bootstrap_forwards_days_so_the_cache_window_matches_the_request(self):
        api, client = self._api()
        api.bootstrap({"days": 60})
        params = [call[2] for call in client.calls if call[1] == "/me/time_entries"][0]
        floor = (TestClock()().date() - timedelta(days=59)).isoformat()
        self.assertEqual(params["start_date"], floor)

    def test_default_workspace_prefers_the_user_default(self):
        data = {
            "workspaces": [{"id": 4}, {"id": 9}],
            "user": {"default_workspace_id": 9},
            "current": None,
        }
        self.assertEqual(toggl_api.TogglAPI._default_workspace(data), 9)

    def test_default_workspace_falls_back_to_the_first(self):
        data = {"workspaces": [{"id": 4}], "user": {"default_workspace_id": 77}, "current": None}
        self.assertEqual(toggl_api.TogglAPI._default_workspace(data), 4)

    def test_default_workspace_returns_zero_with_no_workspaces(self):
        self.assertEqual(toggl_api.TogglAPI._default_workspace({"workspaces": []}), 0)

    def test_default_workspace_prefers_the_persisted_id_over_the_user_default(self):
        data = {
            "workspaces": [{"id": 4}, {"id": 9}],
            "user": {"default_workspace_id": 9},
            "current": None,
        }
        self.assertEqual(toggl_api.TogglAPI._default_workspace(data, 4), 4)

    def test_default_workspace_falls_through_when_the_persisted_id_is_inaccessible(self):
        data = {
            "workspaces": [{"id": 4}, {"id": 9}],
            "user": {"default_workspace_id": 9},
            "current": None,
        }
        self.assertEqual(toggl_api.TogglAPI._default_workspace(data, 77), 9)


class HistoryDaysTest(unittest.TestCase):
    def test_none_defaults_to_30(self):
        self.assertEqual(toggl_api._history_days(None), 30)

    def test_365_clamps_to_the_safe_window(self):
        self.assertEqual(toggl_api._history_days(365), toggl_api.HISTORY_SAFE_DAYS)

    def test_93_clamps_because_the_api_floor_is_91_days(self):
        self.assertEqual(toggl_api._history_days(93), toggl_api.HISTORY_SAFE_DAYS)

    def test_92_is_the_largest_accepted_window(self):
        self.assertEqual(toggl_api._history_days(92), 92)

    def test_arbitrary_small_values_pass_through(self):
        self.assertEqual(toggl_api._history_days(45), 45)

    def test_zero_and_negative_default_to_30(self):
        self.assertEqual(toggl_api._history_days(0), 30)
        self.assertEqual(toggl_api._history_days(-5), 30)

    def test_non_integer_is_rejected(self):
        with self.assertRaises(toggl_api.ValidationError):
            toggl_api._history_days("30")
        with self.assertRaises(toggl_api.ValidationError):
            toggl_api._history_days(True)


class BlockDetailTest(unittest.TestCase):
    @staticmethod
    def _window(start, seconds, app, title):
        return {"timestamp": start, "duration": seconds, "data": {"app": app, "title": title}}

    def _blocks(self):
        base = "2026-09-03T08:00:00+00:00"

        def at(minutes, seconds, app, title):
            moment = datetime.fromisoformat(base) + timedelta(minutes=minutes)
            return self._window(moment.isoformat(), seconds, app, title)

        windows = [
            at(0, 600, "dev.zed.Zed", "toggl_api.py — plugin"),
            at(12, 300, "zen", "Toggl API reference — Zen"),
            at(20, 600, "dev.zed.Zed", "toggl_api.py — plugin"),
            at(33, 900, "dev.zed.Zed", "Model.js — plugin"),
        ]
        afk = [{"timestamp": base, "duration": 4200, "data": {"status": "not-afk"}}]
        web = [{
            "timestamp": (datetime.fromisoformat(base) + timedelta(minutes=12)).isoformat(),
            "duration": 300,
            "data": {"url": "https://engineering.toggl.com/docs", "title": "Toggl"},
        }]
        return toggl_api.segment_blocks(windows, afk, web, {"min_block_minutes": 5})

    def test_apps_carry_seconds(self):
        block = self._blocks()[0]
        self.assertTrue(all(set(item) == {"name", "seconds"} for item in block["apps"]))
        zed = [item for item in block["apps"] if item["name"] == "dev.zed.Zed"][0]
        self.assertEqual(zed["seconds"], 2100)

    def test_apps_are_ranked_by_seconds(self):
        seconds = [item["seconds"] for item in self._blocks()[0]["apps"]]
        self.assertEqual(seconds, sorted(seconds, reverse=True))

    def test_domains_are_a_ranked_list_not_only_the_max(self):
        block = self._blocks()[0]
        self.assertEqual(block["domains"], [{"name": "engineering.toggl.com", "seconds": 300}])
        self.assertEqual(block["domain"], "engineering.toggl.com")

    def test_fragment_count_and_longest_run(self):
        block = self._blocks()[0]
        self.assertEqual(block["fragments"], 4)
        self.assertEqual(block["longest_fragment_seconds"], 900)

    def test_idle_seconds_is_span_minus_active(self):
        block = self._blocks()[0]
        self.assertEqual(block["idle_seconds"], block["span_seconds"] - block["seconds"])
        self.assertGreaterEqual(block["idle_seconds"], 0)

    def test_timeline_offsets_are_relative_and_ascending(self):
        timeline = self._blocks()[0]["timeline"]
        offsets = [item["offset"] for item in timeline]
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(all(set(item) == {"offset", "seconds", "topic", "idle"} for item in timeline))

    def test_timeline_marks_the_gap_between_fragments(self):
        self.assertTrue(any(item["idle"] for item in self._blocks()[0]["timeline"]))

    def test_timeline_is_capped_at_200_entries(self):
        base = datetime.fromisoformat("2026-09-03T08:00:00+00:00")
        windows = [
            self._window((base + timedelta(seconds=index * 20)).isoformat(), 20,
                         "dev.zed.Zed", "file-%d.py — plugin" % index)
            for index in range(400)
        ]
        afk = [{"timestamp": base.isoformat(), "duration": 8000, "data": {"status": "not-afk"}}]
        blocks = toggl_api.segment_blocks(windows, afk, [], {"min_block_minutes": 5})
        self.assertTrue(all(len(block["timeline"]) <= 200 for block in blocks))


AW_BUCKETS = {
    "aw-watcher-window_host": {"id": "aw-watcher-window_host", "type": "currentwindow"},
    "aw-watcher-afk_host": {"id": "aw-watcher-afk_host", "type": "afkstatus"},
    "aw-watcher-web_host": {"id": "aw-watcher-web_host", "type": "web.tab.current"},
}


class RecordingOpener:
    """Serves ActivityWatch responses indefinitely and records every path."""

    def __init__(self, events):
        self.events = events
        self.paths = []

    def __call__(self, request, timeout):
        path = request.full_url.split("?")[0].replace(toggl_api.ACTIVITYWATCH_URL, "")
        self.paths.append(path)
        if path == "/api/0/buckets/":
            return Response(AW_BUCKETS)
        for kind, bucket_id in (("window", "aw-watcher-window_host"),
                                ("afk", "aw-watcher-afk_host"),
                                ("web", "aw-watcher-web_host")):
            if bucket_id in path:
                return Response(self.events.get(kind, []))
        return Response([])

    def event_paths(self):
        return [path for path in self.paths if path.endswith("/events")]


class ActivityCacheTest(unittest.TestCase):
    DATE = "2026-08-19"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        self.opener = RecordingOpener({
            "window": [
                aw_event(base.isoformat(), 600, {"app": "dev.zed.Zed", "title": "a — plugin"}),
                # Fragment 1 runs 08:00–08:10; this one 08:17–08:27. The 7-minute
                # gap splits under a 5-minute break and merges under a 15-minute one.
                aw_event((base + timedelta(minutes=17)).isoformat(), 600,
                         {"app": "dev.zed.Zed", "title": "b — plugin"}),
            ],
            "afk": [aw_event(base.isoformat(), 4200, {"status": "not-afk"})],
            "web": [],
        })

    def _api(self):
        client = cache_client()
        return toggl_api.TogglAPI(
            client, cache_root=self.tmp.name, clock=TestClock(),
            activitywatch_opener=self.opener,
        ), client

    def _call(self, api, minutes=5, entries=None):
        payload = {"workspace_id": 4, "date": self.DATE, "min_block_minutes": minutes}
        if entries is not None:
            payload["entries"] = entries
        return api.day_activity(payload)

    def test_bucket_ids_are_cached_across_calls(self):
        api, _ = self._api()
        self._call(api)
        second, _ = self._api()
        self._call(second)
        self.assertEqual(self.opener.paths.count("/api/0/buckets/"), 1)

    def test_raw_events_are_cached_across_calls(self):
        api, _ = self._api()
        self._call(api)
        first = len(self.opener.event_paths())
        second, _ = self._api()
        self._call(second)
        self.assertEqual(len(self.opener.event_paths()), first)

    def test_changing_the_break_reuses_cached_events(self):
        api, _ = self._api()
        five = self._call(api, minutes=5)
        before = len(self.opener.event_paths())
        other, _ = self._api()
        fifteen = self._call(other, minutes=15)
        self.assertEqual(len(self.opener.event_paths()), before)
        self.assertEqual(len(five["blocks"]), 2)
        self.assertEqual(len(fifteen["blocks"]), 1)

    def test_day_activity_uses_supplied_entries(self):
        api, client = self._api()
        result = self._call(api, entries=[{"id": 9, "start": "", "stop": ""}])
        self.assertEqual(result["entries"], [{"id": 9, "start": "", "stop": ""}])
        self.assertNotIn("/me/time_entries", [call[1] for call in client.calls])

    def test_day_activity_still_fetches_entries_when_none_supplied(self):
        api, client = self._api()
        self._call(api)
        self.assertIn("/me/time_entries", [call[1] for call in client.calls])

    def test_non_zero_padded_date_normalizes_and_succeeds(self):
        api, _ = self._api()
        result = api.day_activity({"workspace_id": 4, "date": "2026-8-19", "min_block_minutes": 5})
        self.assertEqual(result["date"], "2026-08-19")
        self.assertEqual(len(result["blocks"]), 2)

    def test_junk_date_raises_validation_error(self):
        api, _ = self._api()
        with self.assertRaises(toggl_api.ValidationError):
            api.day_activity({"workspace_id": 4, "date": "not-a-date", "min_block_minutes": 5})

    def test_corrupted_awday_cache_falls_back_to_refetch(self):
        api, _ = self._api()
        store = api._store()
        now = api._now_datetime()
        store.write("awday", {
            "schema": toggl_api.CACHE_SCHEMA, "version": toggl_api.CACHE_VERSION, "kind": "awday",
            "account_key": api.client.account_key, "workspace_id": self.DATE,
            "expires_at": toggl_api._cache_iso(now + toggl_api.AW_DAY_TTL),
            "payload": ["not", "a", "dict"],
        }, self.DATE)
        result = self._call(api)
        self.assertEqual(len(self.opener.event_paths()), 3)
        self.assertEqual(len(result["blocks"]), 2)


class EntryCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _api(self, client=None, clock=None):
        client = client or cache_client()
        return toggl_api.TogglAPI(
            client, cache_root=self.tmp.name, clock=clock or TestClock()), client

    @staticmethod
    def _entry_params(client):
        return [call[2] for call in client.calls if call[1] == "/me/time_entries"]

    def test_sync_requests_meta_true(self):
        api, client = self._api()
        api.sync({"workspace_id": 4, "days": 30})
        self.assertEqual(self._entry_params(client)[0].get("meta"), "true")

    def test_first_sync_sends_a_window(self):
        api, client = self._api()
        api.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[0]
        self.assertIn("start_date", params)
        self.assertNotIn("since", params)

    def test_second_sync_uses_since_not_the_full_window(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        second, _ = self._api(client=client)
        second.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[1]
        self.assertIn("since", params)
        self.assertNotIn("start_date", params)

    def test_since_is_never_earlier_than_the_history_floor(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        late = TestClock()
        late.value = late.value + timedelta(days=200)
        second, _ = self._api(client=client, clock=late)
        second.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[1]
        # The cache has long expired, so this must be a fresh window, never a
        # `since` older than the floor -- which the API rejects with 400.
        self.assertIn("start_date", params)
        self.assertNotIn("since", params)

    def test_start_date_is_never_earlier_than_the_history_floor(self):
        api, client = self._api()
        api.sync({"workspace_id": 4, "days": 92})
        params = self._entry_params(client)[0]
        floor = (TestClock()().date() - timedelta(days=toggl_api.HISTORY_FLOOR_DAYS)).isoformat()
        self.assertGreaterEqual(params["start_date"], floor)

    def test_force_refresh_ignores_the_entry_cache(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        second, _ = self._api(client=client)
        second.sync({"workspace_id": 4, "days": 30, "force_refresh": True})
        params = self._entry_params(client)[1]
        self.assertIn("start_date", params)

    def test_widened_days_forces_a_windowed_fetch_not_since(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        second, _ = self._api(client=client)
        second.sync({"workspace_id": 4, "days": 90})
        params = self._entry_params(client)[1]
        self.assertIn("start_date", params)
        self.assertNotIn("since", params)

    def test_unchanged_days_still_uses_since(self):
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        second, _ = self._api(client=client)
        second.sync({"workspace_id": 4, "days": 30})
        params = self._entry_params(client)[1]
        self.assertIn("since", params)
        self.assertNotIn("start_date", params)

    def test_since_delta_removes_a_deleted_entry(self):
        client = cache_client()
        client.queue(
            "/me/time_entries",
            [{"id": 1, "workspace_id": 4, "start": "2026-08-18T08:00:00Z", "duration": 60}],
            [{"id": 1, "workspace_id": 4, "start": "2026-08-18T08:00:00Z", "duration": 60,
              "server_deleted_at": "2026-08-19T09:00:00Z"}],
        )
        first, _ = self._api(client=client)
        self.assertEqual(len(first.sync({"workspace_id": 4, "days": 30})["entries"]), 1)
        second, _ = self._api(client=client)
        self.assertEqual(second.sync({"workspace_id": 4, "days": 30})["entries"], [])

    def test_warm_merge_ignores_a_non_dict_cached_entry(self):
        # A corrupted or hand-edited cache file can hold an entries list with
        # non-dict items; the warm merge must skip them rather than crash on
        # item.get(). The cold path already filters this way.
        first, client = self._api()
        first.sync({"workspace_id": 4, "days": 30})
        store = first._store()
        cached, _ = store.load("entries", 4)
        corrupted = dict(cached)
        corrupted["entries"] = cached["entries"] + ["not-a-dict"]
        store.write("entries", corrupted, 4)
        second, _ = self._api(client=client)
        result = second.sync({"workspace_id": 4, "days": 30})
        self.assertIsInstance(result["entries"], list)

    def test_project_color_survives_normalisation(self):
        entry = toggl_api._normalized_entry({
            "id": 1, "workspace_id": 7, "project_id": 3, "project_color": "#0b83d9",
            "start": "2026-09-03T08:00:00Z", "duration": 60,
        })
        self.assertEqual(entry["project_color"], "#0b83d9")


class RangeEntriesTest(unittest.TestCase):
    def _api(self, responses, clock=None):
        client = FakeClient(responses)
        return toggl_api.TogglAPI(client, cache_root=None, clock=clock or TestClock()), client

    def test_clamps_start_date_to_the_floor_and_sets_clamped(self):
        api, client = self._api([[]])
        result = api.range_entries({
            "workspace_id": 4, "start_date": "2026-01-01", "end_date": "2026-08-19",
        })
        floor = (TestClock()().date() - timedelta(days=toggl_api.HISTORY_FLOOR_DAYS)).isoformat()
        self.assertEqual(result["start_date"], floor)
        self.assertTrue(result["clamped"])

    def test_does_not_clamp_a_range_already_inside_the_floor(self):
        api, client = self._api([[]])
        result = api.range_entries({
            "workspace_id": 4, "start_date": "2026-08-01", "end_date": "2026-08-19",
        })
        self.assertEqual(result["start_date"], "2026-08-01")
        self.assertFalse(result["clamped"])

    def test_rejects_end_date_entirely_below_the_floor(self):
        api, client = self._api([])
        with self.assertRaises(toggl_api.ValidationError):
            api.range_entries({"workspace_id": 4, "start_date": "2020-01-01", "end_date": "2020-01-07"})

    def test_rejects_end_date_before_start_date(self):
        api, client = self._api([])
        with self.assertRaises(toggl_api.ValidationError):
            api.range_entries({"workspace_id": 4, "start_date": "2026-08-10", "end_date": "2026-08-01"})

    def test_rejects_a_malformed_date(self):
        api, client = self._api([])
        with self.assertRaises(toggl_api.ValidationError):
            api.range_entries({"workspace_id": 4, "start_date": "not-a-date", "end_date": "2026-08-19"})

    def test_caps_the_span_at_92_days_and_sets_clamped(self):
        api, client = self._api([[]])
        floor = TestClock()().date() - timedelta(days=toggl_api.HISTORY_FLOOR_DAYS)
        future_end = TestClock()().date() + timedelta(days=5)
        result = api.range_entries({
            "workspace_id": 4, "start_date": floor.isoformat(), "end_date": future_end.isoformat(),
        })
        self.assertTrue(result["clamped"])
        span = (
            datetime.strptime(result["end_date"], "%Y-%m-%d").date()
            - datetime.strptime(result["start_date"], "%Y-%m-%d").date()
        ).days + 1
        self.assertEqual(span, toggl_api.HISTORY_MAX_DAYS)
        # end_date, what the caller actually asked to see, is never moved.
        self.assertEqual(result["end_date"], future_end.isoformat())

    def test_fetches_with_meta_true_and_filters_by_workspace(self):
        api, client = self._api([[
            {"id": 1, "workspace_id": 4, "project_color": "#0b83d9",
             "start": "2026-08-10T09:00:00Z", "stop": "2026-08-10T10:00:00Z"},
            {"id": 2, "workspace_id": 9,
             "start": "2026-08-10T09:00:00Z", "stop": "2026-08-10T10:00:00Z"},
        ]])
        result = api.range_entries({"workspace_id": 4, "start_date": "2026-08-01", "end_date": "2026-08-19"})
        self.assertEqual([e["id"] for e in result["entries"]], [1])
        self.assertEqual(result["entries"][0]["project_color"], "#0b83d9")
        _, _, params, _, _ = client.calls[0]
        self.assertEqual(params.get("meta"), "true")
        self.assertEqual(params.get("start_date"), "2026-08-01")
        self.assertEqual(params.get("end_date"), "2026-08-19")

    def test_dispatches_from_the_action_string(self):
        api, client = self._api([[]])
        result = api.dispatch({
            "action": "range_entries", "workspace_id": 4,
            "start_date": "2026-08-01", "end_date": "2026-08-19",
        })
        self.assertEqual(result["start_date"], "2026-08-01")


class ClassifyTest(unittest.TestCase):
    def _projects(self):
        return [{"id": 5, "name": "acme", "client": "Acme Ltd"}]

    def _blocks(self):
        return [{
            "index": 0, "label": "vim",
            "topics": [{"name": "vim", "seconds": 600}],
            "apps": ["dev.zed.Zed"], "domains": ["bitbucket.org"], "seconds": 600,
        }]

    def _payload(self):
        return {
            "action": "classify", "workspace_id": 4,
            "blocks": self._blocks(), "projects": self._projects(),
        }

    def test_classify_returns_results_and_model(self):
        content = json.dumps({"description": "Reviewing PRs"})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        # No history store behind a FakeClient, so no project -- but the prose
        # still lands, which is the whole point of the split.
        self.assertEqual(result["results"], [
            {"index": 0, "description": "Reviewing PRs", "project_id": None,
             "confidence": 0.0, "source": "model"},
        ])
        self.assertEqual(result["model"], toggl_api.CLASSIFIER_MODEL)
        self.assertIsInstance(result["elapsed_ms"], int)
        self.assertNotIn("degraded", result)
    def test_classify_degraded_on_connection_refused(self):
        def opener(request, timeout):
            raise URLError(ConnectionRefusedError())

        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        self.assertEqual(result["results"], [])
        self.assertTrue(result["degraded"])
    def test_classify_degraded_on_timeout(self):
        def opener(request, timeout):
            raise TimeoutError("timed out")

        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        self.assertEqual(result["results"], [])
        self.assertTrue(result["degraded"])
    def test_classify_degraded_on_non_200(self):
        error = HTTPError("http://127.0.0.1:8127/v1/chat/completions", 500, "error", Message(), BytesIO(b"failure"))

        def opener(request, timeout):
            raise error

        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        result = api.dispatch(self._payload())
        self.assertEqual(result["results"], [])
        self.assertTrue(result["degraded"])
    def test_classify_takes_the_project_from_history_never_from_the_model(self):
        # The model may say whatever it likes; the project is the store's.
        content = json.dumps({"description": "real work", "project_id": 999})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        with tempfile.TemporaryDirectory() as root:
            store = toggl_api.HistoryStore(root)
            store.learn({"seconds": 600, "topics": [{"name": "vim", "seconds": 600}]},
                        {"id": 1, "description": "past", "project_id": 5})
            store.save()
            api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, data_root=root)
            result = api.dispatch(self._payload())
        row = result["results"][0]
        self.assertEqual(row["description"], "real work")
        self.assertEqual(row["project_id"], 5)
        self.assertEqual(row["source"], "history")
    def test_classify_confidence_is_the_history_score_within_the_unit_interval(self):
        content = json.dumps({"description": "x"})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        with tempfile.TemporaryDirectory() as root:
            store = toggl_api.HistoryStore(root)
            store.learn({"seconds": 600, "topics": [{"name": "vim", "seconds": 600}]},
                        {"id": 1, "description": "past", "project_id": 5})
            store.save()
            api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, data_root=root)
            row = api.dispatch(self._payload())["results"][0]
        self.assertGreaterEqual(row["confidence"], 0.0)
        self.assertLessEqual(row["confidence"], 1.0)
    def test_classify_posts_to_llama_server_with_json_schema_response_format(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return Response({"choices": [{"message": {"content": json.dumps({"description": "x"})}}]})

        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        api.dispatch(self._payload())
        self.assertEqual(captured["url"], "http://127.0.0.1:8127/v1/chat/completions")
        self.assertEqual(captured["method"], "POST")
        self.assertGreater(captured["timeout"], 0)
        self.assertLessEqual(captured["timeout"], 20)
        schema = captured["body"]["response_format"]["json_schema"]["schema"]
        # Ruling R-AO: one block per request, and the model is asked for prose
        # only -- the project never reaches it, so the schema has no project_id.
        self.assertEqual(list(schema["properties"]), ["description"])
        self.assertEqual(schema["properties"]["description"]["maxLength"], 120)
        self.assertEqual(captured["body"]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(captured["body"]["temperature"], 0)
    def test_classify_prompt_takes_names_from_dict_apps_and_domains(self):
        # day_activity blocks carry {name, seconds} for apps and domains; the
        # prompt must show the name, never a Python repr of the dict.
        captured = {}

        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return Response({"choices": [{"message": {"content": json.dumps({"results": []})}}]})

        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        api.classify({
            "workspace_id": 1,
            "blocks": [{
                "index": 0, "seconds": 600, "topics": [],
                "apps": [{"name": "com.mitchellh.ghostty", "seconds": 500}, "zen"],
                "domains": [{"name": "github.com", "seconds": 300}],
            }],
            "projects": [{"id": 7, "name": "P", "client": None}],
        })
        prompt = captured["body"]["messages"][-1]["content"]
        self.assertIn("Apps: com.mitchellh.ghostty (8m), zen", prompt)
        self.assertIn("Sites: github.com (5m)", prompt)
        self.assertNotIn("{'name'", prompt)

    def test_classify_prompt_carries_only_normalised_topics_never_raw_labels(self):
        captured = {}

        def opener(request, timeout):
            captured["prompt"] = json.loads(request.data.decode("utf-8"))["messages"][-1]["content"]
            return Response({"choices": [{"message": {"content": json.dumps({"description": "d"})}}]})

        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener)
        api.classify({
            "workspace_id": 1,
            "blocks": [{"index": 0, "seconds": 600, "label": "a raw window title that must never leak",
                        "topics": [{"name": "vim", "seconds": 600}],
                        "apps": ["dev.zed.Zed"], "domains": ["bitbucket.org"]}],
            "projects": [{"id": 5, "name": "acme", "client": "acme corp"}],
        })
        prompt = captured["prompt"]
        self.assertNotIn("a raw window title that must never leak", prompt)
        self.assertIn("vim", prompt)
        self.assertIn("bitbucket.org", prompt)
        # Ruling R-AO: project names are not shown either, because the model
        # copied the winning candidate straight into the description.
        self.assertNotIn("acme", prompt)
    def test_classify_is_not_reachable_from_create_entry(self):
        def opener(request, timeout):
            raise AssertionError("create_entry must never reach llama-server")
        client = FakeClient([[], {"id": 1, "workspace_id": 4, "description": "history"}])
        api = toggl_api.TogglAPI(client, classify_opener=opener)
        result = api.create_entry({
            "workspace_id": 4, "start": "2026-08-19T10:00:00Z", "duration": 300,
            "description": "history", "project_id": None, "tags": [], "billable": False,
        })
        self.assertEqual(result["entry"]["id"], 1)

    def test_create_entry_source_never_mentions_classify_or_the_llama_port(self):
        import inspect
        source = inspect.getsource(toggl_api.TogglAPI.create_entry)
        self.assertNotIn("classify", source)
        self.assertNotIn("8127", source)


class ClassifyLoggingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _records(self):
        path = Path(self.tmp.name) / "logs" / "toggl.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def _payload(self):
        return {
            "action": "classify", "workspace_id": 4,
            "blocks": [{
                "index": 0,
                "topics": [{"name": "a very identifying topic name", "seconds": 600}],
                "apps": ["dev.zed.Zed"], "domains": [], "seconds": 600,
            }],
            "projects": [{"id": 5, "name": "acme", "client": "Acme Ltd"}],
        }

    def test_classify_prompt_and_response_absent_at_info(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "info")
        def opener(request, timeout):
            raise URLError(ConnectionRefusedError())
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, logger=logger)
        api.classify(self._payload())
        contents = (Path(self.tmp.name) / "logs" / "toggl.jsonl").read_text()
        self.assertNotIn("a very identifying topic name", contents)

    def test_classify_prompt_and_response_present_at_debug(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "debug")
        content = json.dumps({"results": [
            {"index": 0, "description": "Reviewing PRs", "project_id": 5, "confidence": 0.8},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, logger=logger)
        api.classify(self._payload())
        contents = (Path(self.tmp.name) / "logs" / "toggl.jsonl").read_text()
        self.assertIn("a very identifying topic name", contents)

    def test_classify_string_fields_truncate_at_500_characters(self):
        import toggl_log
        logger = toggl_log.Logger(self.tmp.name, "debug")
        content = json.dumps({"results": [
            {"index": 0, "description": "x" * 600, "project_id": 5, "confidence": 0.8},
        ]})
        opener = lambda request, timeout: Response({"choices": [{"message": {"content": content}}]})
        api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, logger=logger)
        api.classify(self._payload())
        record = [r for r in self._records() if r.get("action") == "classify"][0]
        self.assertLessEqual(len(record["prompt"]), 500)


if __name__ == "__main__":
    unittest.main()


class SingleDayFetchTests(unittest.TestCase):
    def test_day_activity_asks_toggl_for_an_exclusive_next_day_end(self):
        buckets = [{"id": "windows", "type": "currentwindow"}, {"id": "afk", "type": "afkstatus"}]
        client = FakeClient([[]])
        api = toggl_api.TogglAPI(client, activitywatch_opener=aw_opener(buckets, {}))
        api.dispatch({"action": "day_activity", "date": "2026-08-31", "workspace_id": 4})
        self.assertEqual(client.calls[0][2], {"start_date": "2026-08-31", "end_date": "2026-09-01"})

    def test_create_entry_overlap_check_covers_the_whole_local_day(self):
        client = FakeClient([[], {"id": 7, "workspace_id": 4, "description": "x"}])
        toggl_api.TogglAPI(client).dispatch({"action": "create_entry", "workspace_id": 4, "start": "2026-08-19T10:00:00Z",
                                             "duration": 300, "description": "x", "project_id": None, "tags": [], "billable": False})
        params = client.calls[0][2]
        self.assertEqual((datetime.strptime(params["end_date"], "%Y-%m-%d") - datetime.strptime(params["start_date"], "%Y-%m-%d")).days, 1)


class HistoryStoreTests(unittest.TestCase):
    BLOCK = {"seconds": 900, "topics": [{"name": "omarchy: toggl", "seconds": 600}, {"name": "Flea", "seconds": 300}],
             "apps": [{"name": "ghostty", "seconds": 900}], "domain": "github.com"}

    def test_learn_suggest_persist_and_dedupe_by_entry_id(self):
        with tempfile.TemporaryDirectory() as root:
            store = toggl_api.HistoryStore(root, clock=TestClock())
            self.assertTrue(store.learn(self.BLOCK, {"id": 1, "description": "panel redesign", "project_id": 7, "task_id": 3}))
            self.assertFalse(store.learn(self.BLOCK, {"id": 1, "description": "panel redesign", "project_id": 7}))
            self.assertTrue(store.learn({"seconds": 60, "topics": [{"name": "Flea", "seconds": 60}]}, {"id": 2, "description": "flea file manager", "project_id": None}))
            reloaded = toggl_api.HistoryStore(root, clock=TestClock())
            hits = reloaded.suggest({"seconds": 100, "topics": [{"name": "omarchy: toggl", "seconds": 80}, {"name": "Flea", "seconds": 20}],
                                     "apps": [{"name": "ghostty", "seconds": 100}], "domain": "github.com"})
            self.assertEqual(hits[0]["description"], "panel redesign")
            self.assertEqual((hits[0]["project_id"], hits[0]["task_id"], hits[0]["seen"]), (7, 3, 1))
            self.assertGreaterEqual(hits[0]["score"], 0.9)
            self.assertEqual(hits[1]["description"], "flea file manager")
            self.assertLess(hits[1]["score"], 0.5)
            self.assertEqual(reloaded.suggest({"seconds": 10, "topics": [{"name": "unrelated", "seconds": 10}]}), [])
            self.assertTrue(os.path.exists(os.path.join(root, "history.json")))

    def test_broken_store_is_renamed_aside_and_started_fresh(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "history.json"), "w", encoding="utf-8") as handle:
                handle.write("{not json")
            store = toggl_api.HistoryStore(root, clock=TestClock())
            self.assertEqual(store.records, [])
            self.assertTrue(any(name.startswith("history.json.broken-") for name in os.listdir(root)))

    def _aw(self, title):
        buckets = [{"id": "windows", "type": "currentwindow"}, {"id": "afk", "type": "afkstatus"}]
        return aw_opener(buckets, {
            "window": [aw_event("2026-08-19T10:00:00Z", 600, {"app": "Editor", "title": title})],
            "afk": [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})], "web": []})

    def test_day_activity_learns_covered_blocks_then_suggests_for_pending_ones(self):
        with tempfile.TemporaryDirectory() as root:
            entry = {"id": 12, "workspace_id": 4, "start": "2026-08-19T10:05:00Z", "stop": "2026-08-19T10:06:00Z",
                     "description": "panel redesign", "project_id": 7}
            api = toggl_api.TogglAPI(FakeClient([]), activitywatch_opener=self._aw("omarchy: toggl"), data_root=root)
            first = api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4, "entries": [entry]})
            self.assertTrue(first["blocks"][0]["applied"])
            self.assertNotIn("history", first["blocks"][0])
            api = toggl_api.TogglAPI(FakeClient([]), activitywatch_opener=self._aw("omarchy: toggl"), data_root=root)
            second = api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4, "entries": []})
            self.assertFalse(second["blocks"][0]["applied"])
            hit = second["blocks"][0]["history"][0]
            self.assertEqual((hit["description"], hit["project_id"]), ("panel redesign", 7))
            self.assertGreaterEqual(hit["score"], toggl_api.HISTORY_GUESS_SCORE)

    def test_fake_client_without_data_root_never_opens_a_store(self):
        api = toggl_api.TogglAPI(FakeClient([]), activitywatch_opener=self._aw("x"))
        self.assertIsNone(api._history())
        result = api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4, "entries": []})
        self.assertNotIn("history", result["blocks"][0])

    def test_create_entry_learns_when_the_block_is_supplied(self):
        with tempfile.TemporaryDirectory() as root:
            client = FakeClient([[], {"id": 77, "workspace_id": 4, "description": "panel redesign", "project_id": 7}])
            api = toggl_api.TogglAPI(client, data_root=root)
            api.dispatch({"action": "create_entry", "workspace_id": 4, "start": "2026-08-19T10:00:00Z", "duration": 300,
                          "description": "panel redesign", "project_id": 7, "tags": [], "billable": False, "block": self.BLOCK})
            records = toggl_api.HistoryStore(root).records
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["topics"], {"omarchy: toggl": 600, "flea": 300})
            self.assertEqual(records[0]["domains"], {"github.com": 900})

    def test_classify_shows_the_model_neither_past_entries_nor_projects(self):
        # Ruling R-AO: quoted past descriptions were copied verbatim (17 of 26
        # outputs) and candidate project names were copied into the description
        # on every block of a live day. The model sees the block and nothing else.
        with tempfile.TemporaryDirectory() as root:
            toggl_api.HistoryStore(root).learn(self.BLOCK, {"id": 1, "description": "panel redesign", "project_id": 7})
            prompts = []

            def opener(request, timeout):
                prompts.append(json.loads(request.data.decode("utf-8"))["messages"][-1]["content"])
                return Response({"choices": [{"message": {"content": json.dumps({"description": "d"})}}]})

            api = toggl_api.TogglAPI(FakeClient([]), classify_opener=opener, data_root=root)
            result = api.classify({"workspace_id": 4, "projects": [{"id": 7, "name": "Panel", "client": None}],
                                   "blocks": [{"index": 0, "seconds": 100, "topics": [{"name": "omarchy: toggl", "seconds": 100}], "apps": [], "domains": []},
                                              {"index": 1, "seconds": 100, "topics": [{"name": "nothing similar", "seconds": 100}], "apps": [], "domains": []}]})
            self.assertEqual(len(prompts), 2)
            for prompt in prompts:
                self.assertNotIn("panel redesign", prompt)
                self.assertNotIn("Panel", prompt)
                self.assertIn("Activity block:", prompt)
            self.assertEqual([r["index"] for r in result["results"]], [0, 1])
    def test_learn_history_replays_days_and_skips_failures(self):
        with tempfile.TemporaryDirectory() as root:
            from datetime import timedelta
            clock = TestClock()
            # Day 0 and day 2 are replayed, day 1 fails; the event sits on day 2
            # so the replay has to reach past the failure to learn anything.
            today = clock.value.astimezone(toggl_api._local_timezone()).date()
            day2_start = toggl_api._day_bounds((today - timedelta(days=2)).isoformat())[0]
            at = lambda hours: toggl_api._iso_datetime(day2_start + timedelta(hours=hours))
            buckets = [{"id": "windows", "type": "currentwindow"}, {"id": "afk", "type": "afkstatus"}]
            responses = []
            for _ in range(2):
                responses += [Response(buckets), Response([aw_event(at(10), 600, {"app": "Editor", "title": "omarchy: toggl"})]),
                              Response([aw_event(at(10), 600, {"status": "not-afk"})]), Response([])]
            entry = {"id": 5, "workspace_id": 4, "start": at(10.05), "stop": at(10.1), "description": "panel redesign", "project_id": 7}
            client = FakeClient([[entry], toggl_api.ApiError("down", 503, True), [entry]])
            api = toggl_api.TogglAPI(client, activitywatch_opener=lambda request, timeout: responses.pop(0), clock=clock, data_root=root)
            result = api.dispatch({"action": "learn_history", "workspace_id": 4, "days": 3})
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["days"], 2)
            self.assertEqual(result["records"], 1)


class LearningHarnessTests(unittest.TestCase):
    BLOCK = {"seconds": 900, "label": "omarchy: toggl",
             "topics": [{"name": "omarchy: toggl", "seconds": 600}, {"name": "Flea", "seconds": 300}],
             "apps": [{"name": "ghostty", "seconds": 900}], "domains": [{"name": "github.com", "seconds": 900}]}

    def test_block_signature_drops_minutes_and_leads_with_the_label(self):
        signature = toggl_api.block_signature(self.BLOCK)
        self.assertTrue(signature.startswith("omarchy: toggl"))
        self.assertIn("Flea", signature)
        self.assertIn("github.com", signature)
        self.assertNotIn("900", signature)

    def test_embed_returns_none_when_the_embedder_is_absent(self):
        def refused(request, timeout):
            raise URLError(ConnectionRefusedError())
        self.assertIsNone(toggl_api._embed(["x"], refused))
        self.assertIsNone(toggl_api._embed([], lambda r, t: None))

    def test_centroids_are_running_means_and_survive_a_reload(self):
        with tempfile.TemporaryDirectory() as root:
            store = toggl_api.HistoryStore(root, clock=TestClock())
            store.observe_vector(7, [0.0, 2.0])
            store.observe_vector(7, [2.0, 0.0])
            store.save()
            reloaded = toggl_api.HistoryStore(root, clock=TestClock())
            centroid = reloaded.load()["centroids"]["7"]
            self.assertEqual(centroid["vector"], [1.0, 1.0])
            self.assertEqual(centroid["count"], 2)

    def test_project_scores_blend_prior_and_similarity_and_respect_active_ids(self):
        with tempfile.TemporaryDirectory() as root:
            store = toggl_api.HistoryStore(root, clock=TestClock())
            for i in range(4):
                store.learn(self.BLOCK, {"id": i, "description": "common work", "project_id": 7})
            store.learn(self.BLOCK, {"id": 99, "description": "rare work", "project_id": 8})
            store.observe_vector(7, [1.0, 0.0])
            store.observe_vector(8, [0.0, 1.0])
            # Prior alone: the four-times project wins.
            self.assertEqual(store.project_scores(self.BLOCK)[0]["project_id"], 7)
            # A vector pointing hard at the rare project's centroid overturns it.
            ranked = store.project_scores(self.BLOCK, [0.0, 1.0])
            self.assertEqual(ranked[0]["project_id"], 8)
            self.assertGreater(ranked[0]["similarity"], ranked[1]["similarity"])
            # Archived projects never surface.
            self.assertEqual([r["project_id"] for r in store.project_scores(self.BLOCK, None, [7])], [7])

    def test_corrections_record_what_was_offered_against_what_was_kept(self):
        with tempfile.TemporaryDirectory() as root:
            store = toggl_api.HistoryStore(root, clock=TestClock())
            store.record_correction(self.BLOCK, {"description": "guessed", "project_id": 7, "source": "model"},
                                    {"description": "typed by hand", "project_id": 8})
            store.record_correction(self.BLOCK, {"description": "kept", "project_id": 7, "source": "history"},
                                    {"description": "kept", "project_id": 7})
            stats = store.correction_stats()
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["by_source"]["model"], {"n": 1, "description_kept": 0, "project_kept": 0})
            self.assertEqual(stats["by_source"]["history"], {"n": 1, "description_kept": 1, "project_kept": 1})
            rows = store.load()["corrections"]
            self.assertTrue(rows[0]["corrected_description"] and rows[0]["corrected_project"])
            self.assertFalse(rows[1]["corrected_description"] or rows[1]["corrected_project"])

    def test_create_entry_records_correction_and_defers_centroid(self):
        with tempfile.TemporaryDirectory() as root:
            client = FakeClient([[], {"id": 77, "workspace_id": 4, "description": "typed", "project_id": 8}])
            api = toggl_api.TogglAPI(client, data_root=root,
                                     embed_opener=lambda request, timeout: Response({"data": [{"embedding": [1.0, 0.0]}]}))
            api.dispatch({"action": "create_entry", "workspace_id": 4, "start": "2026-08-19T10:00:00Z",
                          "duration": 300, "description": "typed", "project_id": 8, "tags": [], "billable": False,
                          "block": self.BLOCK, "suggested": {"description": "guessed", "project_id": 7, "source": "model"}})
            store = toggl_api.HistoryStore(root)
            self.assertEqual(store.load()["centroids"], {})
            self.assertIn("4:77", store.load()["pending_vectors"])
            api.enrich_day({"workspace_id": 4, "blocks": [], "projects": []})
            store = toggl_api.HistoryStore(root)
            self.assertEqual(store.load()["centroids"]["8"]["vector"], [1.0, 0.0])
            self.assertEqual(store.load()["pending_vectors"], {})
            stats = store.correction_stats()
            self.assertEqual(stats["by_source"]["model"]["n"], 1)
            self.assertEqual(stats["by_source"]["model"]["project_kept"], 0)

    def test_day_activity_attaches_ranked_project_candidates_to_pending_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            entry = {"id": 12, "workspace_id": 4, "start": "2026-08-19T10:05:00Z", "stop": "2026-08-19T10:06:00Z",
                     "description": "panel redesign", "project_id": 7}
            buckets = [{"id": "windows", "type": "currentwindow"}, {"id": "afk", "type": "afkstatus"}]
            def aw(title):
                return aw_opener(buckets, {
                    "window": [aw_event("2026-08-19T10:00:00Z", 600, {"app": "Editor", "title": title})],
                    "afk": [aw_event("2026-08-19T10:00:00Z", 600, {"status": "not-afk"})], "web": []})
            embed = lambda request, timeout: Response({"data": [{"embedding": [1.0, 0.0]}]})
            api = toggl_api.TogglAPI(FakeClient([]), activitywatch_opener=aw("omarchy: toggl"), data_root=root, embed_opener=embed)
            api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4, "entries": [entry]})
            api = toggl_api.TogglAPI(FakeClient([]), activitywatch_opener=aw("omarchy: toggl"), data_root=root, embed_opener=embed)
            out = api.dispatch({"action": "day_activity", "date": "2026-08-19", "workspace_id": 4, "entries": []})
            candidates = out["blocks"][0]["projects"]
            self.assertEqual(candidates[0]["project_id"], 7)
            self.assertLessEqual(len(candidates), toggl_api.PROJECT_SHORTLIST)

    def test_evaluate_scores_each_layer_and_reports_zero_samples_cleanly(self):
        with tempfile.TemporaryDirectory() as root:
            buckets = [{"id": "windows", "type": "currentwindow"}, {"id": "afk", "type": "afkstatus"}]
            responses = []
            for _ in range(40):
                responses += [Response(buckets), Response([]), Response([]), Response([])]
            api = toggl_api.TogglAPI(FakeClient([{"data": []}] + [[]] * 40), clock=TestClock(), data_root=root,
                                     activitywatch_opener=lambda request, timeout: responses.pop(0))
            out = api.dispatch({"action": "evaluate", "workspace_id": 4, "days": 2})
            self.assertEqual(out["samples"], 0)
            self.assertIn("note", out)
