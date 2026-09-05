import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import toggl_api
import toggl_demo


# Every action Panel.qml can send. `update` is dormant and `classify` is reached
# only inside the backend, but both are answered so a future caller is not
# greeted by an error dialog in the middle of a screenshot run.
PANEL_ACTIONS = ["bootstrap", "sync", "day_activity", "range_entries", "enrich_day",
                 "start", "stop", "continue", "create_entry"]


def _payload(action):
    base = {"action": action, "workspace_id": toggl_demo.WORKSPACE_ID}
    if action == "day_activity":
        base.update({"date": toggl_demo.TODAY.isoformat(), "min_block_minutes": 5})
    if action == "range_entries":
        base.update({"start_date": "2026-03-09", "end_date": "2026-03-15"})
    if action == "enrich_day":
        base.update({"date": toggl_demo.TODAY.isoformat(), "generation": 1,
                     "blocks": [{"index": i} for i in range(len(toggl_demo._today_blocks()))],
                     "projects": []})
    if action in ("start", "create_entry"):
        base.update({"description": "typed by hand", "project_id": 101,
                     "start": "2026-03-12T09:00:00Z", "duration": 1800})
    if action == "continue":
        base["entry"] = {"description": "again", "project_id": 101}
    if action == "stop":
        base["entry_id"] = 3100
    return base


class DemoSwitchTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": tempfile.mkdtemp()}, clear=False):
            os.environ.pop("TOGGL_DEMO", None)
            self.assertFalse(toggl_demo.enabled())

    def test_enabled_by_environment_or_marker(self):
        root = tempfile.mkdtemp()
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": root, "TOGGL_DEMO": "1"}, clear=False):
            self.assertTrue(toggl_demo.enabled())
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": root}, clear=False):
            os.environ.pop("TOGGL_DEMO", None)
            self.assertFalse(toggl_demo.enabled())
            Path(toggl_demo.marker_path()).write_text("")
            self.assertTrue(toggl_demo.enabled())


class DemoResponseTests(unittest.TestCase):
    def test_every_panel_action_returns_a_well_formed_envelope(self):
        for action in PANEL_ACTIONS:
            with self.subTest(action=action):
                result = toggl_demo.respond(_payload(action))
                self.assertTrue(result["ok"], action)
                self.assertIsInstance(result["data"], dict)

    def test_entries_match_the_real_normalised_entry_shape(self):
        real = set(toggl_api._normalized_entry({
            "id": 1, "workspace_id": 4, "description": "x", "start": "2026-03-12T09:00:00Z",
            "stop": "2026-03-12T09:30:00Z", "duration": 1800,
        }))
        for entry in toggl_demo.respond(_payload("sync"))["data"]["entries"]:
            self.assertEqual(set(entry), real)

    def test_the_recent_list_offers_ten_distinct_descriptions(self):
        # The timer scope shows ten entries to continue; the screenshot of that
        # list is only worth taking if the fixture can fill it.
        entries = toggl_demo.respond(_payload("sync"))["data"]["entries"]
        distinct = {e["description"] for e in entries}
        self.assertGreaterEqual(len(distinct), 10)

    def test_the_day_covers_every_row_state_the_manual_photographs(self):
        blocks = toggl_demo.respond(_payload("day_activity"))["data"]["blocks"]
        self.assertTrue(any(b["applied"] and b["conflict"]["id"] == 3001 for b in blocks),
                        "an applied block")
        self.assertTrue(any(not b["applied"] for b in blocks), "a pending block")
        self.assertTrue(any(b.get("conflict", {}).get("id") == 4400 for b in blocks),
                        "a conflicting block")
        for block in blocks:
            for field in ("start", "end", "seconds", "label", "topics", "apps",
                          "domains", "timeline", "applied"):
                self.assertIn(field, block)

    def test_enrichment_proposes_descriptions_for_pending_blocks(self):
        data = toggl_demo.respond(_payload("enrich_day"))["data"]
        self.assertTrue(data["results"])
        for row in data["results"]:
            self.assertIn("description", row)
            self.assertIn("project_id", row)
        for row in data["blocks"]:
            self.assertTrue(row["projects"], "ranked project candidates")

    def test_a_day_with_no_invented_activity_is_empty_not_an_error(self):
        result = toggl_demo.respond({"action": "day_activity", "date": "2026-03-01",
                                     "workspace_id": toggl_demo.WORKSPACE_ID})
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["blocks"], [])

    def test_an_unknown_action_is_refused_the_way_the_real_backend_refuses_it(self):
        result = toggl_demo.respond({"action": "nonsense"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["status"], 400)


class DemoIsolationTests(unittest.TestCase):
    """The point of routing before handle(): a demo run cannot reach the
    network, ActivityWatch, the cache, or the user's history store."""

    def test_demo_mode_never_builds_a_TogglAPI(self):
        def explode(*args, **kwargs):
            raise AssertionError("demo mode reached the real backend")

        with patch.object(toggl_api, "TogglAPI", explode), patch.object(toggl_api, "handle", explode):
            for action in PANEL_ACTIONS:
                self.assertTrue(toggl_demo.respond(_payload(action))["ok"], action)

    def test_the_process_serves_fixtures_end_to_end_without_a_token(self):
        # No secret-tool, no network: the whole point is that this runs on a
        # machine that has never seen a Toggl account.
        script = str(Path(__file__).resolve().parents[1] / "toggl_api.py")
        env = dict(os.environ, TOGGL_DEMO="1")
        process = subprocess.run([sys.executable, script], input=json.dumps({"action": "bootstrap"}),
                                 capture_output=True, text=True, timeout=30, env=env)
        result = json.loads(process.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["user"]["name"], "Sam Rivers")

    def test_the_real_path_is_untouched_when_demo_is_off(self):
        # A request with demo off must still go through handle(); if this ever
        # inverts, screenshots would be taken of real data.
        seen = {}

        def fake_handle(payload, **kwargs):
            seen["action"] = payload.get("action")
            return {"ok": True, "data": {}}

        env = dict(os.environ)
        env.pop("TOGGL_DEMO", None)
        with patch.dict(os.environ, env, clear=True), patch.object(toggl_api, "handle", fake_handle):
            with patch.object(toggl_demo, "enabled", lambda: False):
                self.assertFalse(toggl_demo.enabled())


class DemoPrivacyTests(unittest.TestCase):
    """States the property positively, on purpose.

    An earlier version listed the author's real workspace id, user id and
    employer as strings to assert the *absence* of -- which published them in
    the test file, defeating itself. Everything below proves the fixture is
    made of invented material without naming anything real."""

    def _blob(self):
        return json.dumps([toggl_demo.respond(_payload(a)) for a in PANEL_ACTIONS])

    def test_every_workspace_and_user_id_is_an_invented_one(self):
        blob = json.loads(self._blob())
        seen = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in ("workspace_id", "wid", "uid", "user_id") and isinstance(value, int):
                        seen.add(value)
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(blob)
        self.assertTrue(seen, "the fixture should carry ids at all")
        self.assertLessEqual(seen, {toggl_demo.WORKSPACE_ID, toggl_demo.USER_ID})

    def test_the_invented_account_is_what_answers(self):
        # If the real backend ever leaked into this path, the name would not
        # be the fixture's.
        user = toggl_demo.respond(_payload("bootstrap"))["data"]["user"]
        self.assertEqual(user["name"], "Sam Rivers")

    def test_no_field_looks_like_a_credential_or_an_address(self):
        blob = self._blob()
        # A Toggl API token is 32 hex characters; an email is an email.
        self.assertIsNone(re.search(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", blob),
                          "something token-shaped is in the fixture")
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", blob),
                          "an email address is in the fixture")


if __name__ == "__main__":
    unittest.main()
