import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import toggl_doctor


def statuses(report, section=None):
    return {row["name"]: row["status"] for row in report.rows
            if section is None or row["section"] == section}


def detail(report, name):
    for row in report.rows:
        if row["name"] == name:
            return row["detail"]
    raise AssertionError("no row named %s" % name)


class Result(object):
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RuntimeTests(unittest.TestCase):
    def test_a_missing_secret_tool_fails_and_a_missing_notify_send_only_warns(self):
        report = toggl_doctor.Report()
        with patch.object(toggl_doctor.shutil, "which",
                          side_effect=lambda tool: None if tool in ("secret-tool", "notify-send") else "/usr/bin/" + tool):
            toggl_doctor.check_runtime(report)
        found = statuses(report)
        self.assertEqual(found["secret-tool"], toggl_doctor.FAIL)
        self.assertEqual(found["notify-send"], toggl_doctor.WARN)
        self.assertEqual(found["systemctl"], toggl_doctor.OK)

    def test_the_python_floor_is_checked_against_what_zoneinfo_needs(self):
        report = toggl_doctor.Report()
        with patch.object(toggl_doctor.shutil, "which", return_value="/usr/bin/x"), \
             patch.object(toggl_doctor.sys, "version_info", (3, 8, 0)):
            toggl_doctor.check_runtime(report)
        self.assertEqual(statuses(report)["python3"], toggl_doctor.FAIL)


class SecretTests(unittest.TestCase):
    def _check(self, mode="default", running=True, ready=("/c", None), token="tok"):
        report = toggl_doctor.Report()
        import toggl_secret
        with patch.object(toggl_doctor.shutil, "which", return_value="/usr/bin/secret-tool"), \
             patch.object(toggl_secret, "service_running", return_value=running), \
             patch.object(toggl_secret, "mode", return_value=mode), \
             patch.object(toggl_secret, "secure_ready", return_value=ready), \
             patch.object(toggl_doctor, "_run",
                          return_value=Result(0 if token else 1, token or "")):
            toggl_doctor.check_secrets(report, offline=True)
        return report

    def test_a_dead_keyring_daemon_is_a_failure_not_a_missing_token(self):
        report = self._check(running=False)
        self.assertEqual(statuses(report)["secret service"], toggl_doctor.FAIL)
        self.assertIn("gnome-keyring", detail(report, "secret service"))

    def test_the_default_keyring_warns_that_the_token_is_unencrypted(self):
        # Omarchy's login keyring has no password, so it is not encrypted. A
        # health check that called that 'ok' would be lying to the user.
        report = self._check(mode="default")
        self.assertEqual(statuses(report)["keyring"], toggl_doctor.WARN)
        self.assertIn("unencrypted", detail(report, "keyring"))

    def test_a_protected_unlocked_keyring_is_ok(self):
        report = self._check(mode="secure")
        self.assertEqual(statuses(report)["keyring"], toggl_doctor.OK)
        self.assertIn("encrypted at rest", detail(report, "keyring"))

    def test_a_locked_keyring_fails_before_any_lookup_is_attempted(self):
        report = self._check(mode="secure", ready=(None, "the keyring is locked; setup --unlock"))
        self.assertEqual(statuses(report)["keyring"], toggl_doctor.FAIL)
        self.assertNotIn("stored token", statuses(report))

    def test_no_stored_token_says_run_setup(self):
        report = self._check(token="")
        self.assertEqual(statuses(report)["stored token"], toggl_doctor.FAIL)
        self.assertIn("run setup", detail(report, "stored token"))

    def test_offline_skips_the_one_check_that_leaves_the_machine(self):
        report = self._check()
        self.assertEqual(statuses(report)["accepted by Toggl"], toggl_doctor.WARN)


class ActivityWatchTests(unittest.TestCase):
    BUCKETS = {
        "aw-watcher-window_host": {"type": "currentwindow"},
        "aw-watcher-afk_host": {"type": "afkstatus"},
    }

    def _check(self, responses):
        report = toggl_doctor.Report()

        def fake_get(url, timeout=4):
            for fragment, answer in responses:
                if fragment in url:
                    if isinstance(answer, Exception):
                        raise answer
                    return answer
            raise AssertionError("unexpected request: %s" % url)

        with patch.object(toggl_doctor, "_get", side_effect=fake_get):
            toggl_doctor.check_activitywatch(report)
        return report

    def test_a_server_that_is_not_running_names_what_to_install(self):
        report = self._check([("/api/0/info", OSError("connection refused"))])
        self.assertEqual(statuses(report)["server"], toggl_doctor.FAIL)
        self.assertIn("aw-server-rust", detail(report, "server"))

    def test_a_missing_required_bucket_fails_and_a_missing_optional_one_warns(self):
        report = self._check([
            ("/api/0/info", {}),
            ("/events", [{"timestamp": "2026-09-05T10:00:00Z"}]),
            ("/api/0/buckets/", dict(self.BUCKETS)),
        ])
        found = statuses(report)
        self.assertEqual(found["currentwindow"], toggl_doctor.OK)
        self.assertEqual(found["web.tab.current"], toggl_doctor.WARN)

    def test_a_bucket_that_exists_but_records_nothing_is_not_called_healthy(self):
        # This is the failure the Day scope actually hits: the server answers,
        # the bucket is listed, and no events have arrived for days.
        report = self._check([
            ("/api/0/info", {}),
            ("/events", []),
            ("/api/0/buckets/", dict(self.BUCKETS)),
        ])
        self.assertEqual(statuses(report)["currentwindow"], toggl_doctor.WARN)
        self.assertIn("recorded nothing", detail(report, "currentwindow"))

    def test_an_absent_window_bucket_is_a_failure(self):
        report = self._check([
            ("/api/0/info", {}),
            ("/events", [{"timestamp": "x"}]),
            ("/api/0/buckets/", {"aw-watcher-afk_host": {"type": "afkstatus"}}),
        ])
        self.assertEqual(statuses(report)["currentwindow"], toggl_doctor.FAIL)
        self.assertIn("aw-awatcher", detail(report, "currentwindow"))


class PluginTests(unittest.TestCase):
    def test_a_registered_plugin_is_reported_with_where_it_lives(self):
        report = toggl_doctor.Report()
        listing = json.dumps([{"id": toggl_doctor.PLUGIN_ID, "sourceDir": "/home/x/plugins/tt",
                               "enabled": True}])
        with patch.object(toggl_doctor, "_run", return_value=Result(0, listing)):
            toggl_doctor.check_plugin(report)
        self.assertEqual(statuses(report)["installed"], toggl_doctor.OK)
        self.assertIn("/home/x/plugins/tt", detail(report, "installed"))

    def test_an_unregistered_plugin_warns_with_the_command_to_add_it(self):
        report = toggl_doctor.Report()
        with patch.object(toggl_doctor, "_run", return_value=Result(0, "[]")):
            toggl_doctor.check_plugin(report)
        self.assertEqual(statuses(report)["installed"], toggl_doctor.WARN)
        self.assertIn("omarchy plugin add", detail(report, "installed"))

    def test_installed_but_not_enabled_is_the_quiet_failure_and_is_reported(self):
        # Everything else can be healthy while no widget ever appears.
        report = toggl_doctor.Report()
        listing = json.dumps([{"id": toggl_doctor.PLUGIN_ID, "enabled": False}])
        with patch.object(toggl_doctor, "_run", return_value=Result(0, listing)):
            toggl_doctor.check_plugin(report)
        self.assertEqual(statuses(report)["installed"], toggl_doctor.WARN)
        self.assertIn("omarchy plugin enable", detail(report, "installed"))

    def test_a_shell_that_does_not_answer_is_a_warning_not_a_crash(self):
        report = toggl_doctor.Report()
        with patch.object(toggl_doctor, "_run", return_value=None):
            toggl_doctor.check_plugin(report)
        self.assertEqual(statuses(report)["installed"], toggl_doctor.WARN)


class OutputTests(unittest.TestCase):
    def test_exit_status_is_one_when_anything_failed_and_zero_for_warnings(self):
        report = toggl_doctor.Report()
        report.add("A", "warned", toggl_doctor.WARN, "optional")
        self.assertEqual(toggl_doctor.render(report, io.StringIO()), 0)
        report.add("A", "broken", toggl_doctor.FAIL, "required")
        self.assertEqual(toggl_doctor.render(report, io.StringIO()), 1)

    def test_render_prints_every_row_under_its_section(self):
        report = toggl_doctor.Report()
        report.add("Runtime", "python3", toggl_doctor.OK, "3.13.0")
        report.add("Token", "keyring", toggl_doctor.WARN, "unencrypted")
        stream = io.StringIO()
        toggl_doctor.render(report, stream)
        text = stream.getvalue()
        for expected in ("Runtime", "python3", "3.13.0", "Token", "keyring", "1 warning"):
            self.assertIn(expected, text)

    def test_json_output_is_machine_readable_and_carries_the_verdict(self):
        report = toggl_doctor.Report()
        report.add("A", "broken", toggl_doctor.FAIL, "required")
        stream = io.StringIO()
        with patch.object(toggl_doctor, "run", return_value=report), \
             patch.object(toggl_doctor.sys, "stdout", stream):
            code = toggl_doctor.main(["--json"])
        payload = json.loads(stream.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["rows"][0]["name"], "broken")

    def test_an_unknown_flag_is_refused(self):
        with patch.object(toggl_doctor.sys, "stderr", io.StringIO()):
            self.assertEqual(toggl_doctor.main(["--wat"]), 2)


if __name__ == "__main__":
    unittest.main()
