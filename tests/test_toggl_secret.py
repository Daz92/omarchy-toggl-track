import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import toggl_secret


class FakeResult(object):
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class Runner(object):
    """Stands in for subprocess.run so no test touches a real keyring."""

    def __init__(self, result=None, explode=None):
        self.result = result or FakeResult()
        self.explode = explode
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.explode:
            raise self.explode
        return self.result


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        patcher = patch.dict(os.environ, {"XDG_DATA_HOME": self.root}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mode_defaults_to_the_login_keyring(self):
        self.assertEqual(toggl_secret.mode(), toggl_secret.MODE_DEFAULT)

    def test_set_mode_round_trips_and_the_marker_is_private(self):
        toggl_secret.set_mode(toggl_secret.MODE_SECURE)
        self.assertEqual(toggl_secret.mode(), toggl_secret.MODE_SECURE)
        self.assertEqual(os.stat(toggl_secret.mode_path()).st_mode & 0o777, 0o600)
        toggl_secret.set_mode(toggl_secret.MODE_DEFAULT)
        self.assertEqual(toggl_secret.mode(), toggl_secret.MODE_DEFAULT)

    def test_an_unreadable_or_nonsense_marker_falls_back_to_default(self):
        # The plugin has to keep working when $XDG_DATA_HOME is gone or the
        # marker was hand-edited; guessing 'secure' there would strand the user
        # behind a keyring that does not exist.
        toggl_secret.set_mode(toggl_secret.MODE_SECURE)
        with open(toggl_secret.mode_path(), "w", encoding="utf-8") as handle:
            handle.write("banana\n")
        self.assertEqual(toggl_secret.mode(), toggl_secret.MODE_DEFAULT)

    def test_set_mode_refuses_an_unknown_value(self):
        with self.assertRaises(toggl_secret.SecretError):
            toggl_secret.set_mode("elsewhere")


class StoreTests(unittest.TestCase):
    def test_the_token_travels_on_stdin_and_never_in_argv(self):
        # argv is world-readable in /proc and lands in shell history; this is
        # the single most important property of the whole module.
        runner = Runner()
        toggl_secret.store("s3cret-token", runner=runner)
        command, kwargs = runner.calls[0]
        self.assertNotIn("s3cret-token", " ".join(command))
        self.assertEqual(kwargs["input"], "s3cret-token")

    def test_a_collection_is_targeted_when_one_is_given(self):
        runner = Runner()
        toggl_secret.store("t", collection="/org/freedesktop/secrets/collection/x",
                           runner=runner)
        self.assertIn("--collection=/org/freedesktop/secrets/collection/x",
                      runner.calls[0][0])

    def test_a_refusal_is_reported_with_what_the_service_said(self):
        runner = Runner(FakeResult(returncode=1, stderr="Cannot create an item in a locked collection\n"))
        with self.assertRaises(toggl_secret.SecretError) as caught:
            toggl_secret.store("t", runner=runner)
        self.assertIn("locked collection", str(caught.exception))

    def test_a_missing_secret_tool_names_the_package(self):
        runner = Runner(explode=FileNotFoundError())
        with self.assertRaises(toggl_secret.SecretError) as caught:
            toggl_secret.store("t", runner=runner)
        self.assertIn("libsecret", str(caught.exception))

    def test_a_hung_secret_service_is_an_error_not_a_wait(self):
        runner = Runner(explode=subprocess.TimeoutExpired("secret-tool", 30))
        with self.assertRaises(toggl_secret.SecretError):
            toggl_secret.store("t", runner=runner)


class DiagnosisTests(unittest.TestCase):
    """`secret-tool lookup` exits 1 with no output whether the item is absent,
    the daemon is dead, or there is no bus. Each needs its own answer."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        patcher = patch.dict(os.environ, {"XDG_DATA_HOME": self.root}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_secret_tool(self):
        message = toggl_secret.describe_failure(has_secret_tool=False)
        self.assertIn("libsecret", message)

    def test_without_pygobject_the_plain_answer_stands(self):
        # The default keyring path never needs PyGObject. Naming it here would
        # send someone installing an optional package to fix a missing token.
        with patch.object(toggl_secret, "_gi",
                          side_effect=toggl_secret.SecretError("python-gobject is required")):
            message = toggl_secret.describe_failure()
        self.assertIn("run setup", message)
        self.assertNotIn("python-gobject", message)

    def test_no_session_bus(self):
        with patch.object(toggl_secret, "_gi", return_value=(None, None)), \
             patch.object(toggl_secret, "_bus",
                          side_effect=toggl_secret.SecretError("no D-Bus session bus")):
            self.assertIn("D-Bus", toggl_secret.describe_failure())

    def test_no_secret_service_running(self):
        with patch.object(toggl_secret, "_gi", return_value=(None, None)), \
             patch.object(toggl_secret, "_bus", return_value=(None, None, None)), \
             patch.object(toggl_secret, "service_running", return_value=False):
            message = toggl_secret.describe_failure()
        self.assertIn("no secret service is running", message)
        self.assertNotIn("token not found", message)

    def test_a_locked_protected_keyring_says_so_and_names_the_fix(self):
        toggl_secret.set_mode(toggl_secret.MODE_SECURE)
        with patch.object(toggl_secret, "_gi", return_value=(None, None)), \
             patch.object(toggl_secret, "_bus", return_value=(None, None, None)), \
             patch.object(toggl_secret, "service_running", return_value=True), \
             patch.object(toggl_secret, "find_collection", return_value="/c"), \
             patch.object(toggl_secret, "is_locked", return_value=True):
            message = toggl_secret.describe_failure()
        self.assertIn("locked", message)
        self.assertIn("setup --unlock", message)

    def test_everything_healthy_falls_back_to_the_plain_answer(self):
        with patch.object(toggl_secret, "_gi", return_value=(None, None)), \
             patch.object(toggl_secret, "_bus", return_value=(None, None, None)), \
             patch.object(toggl_secret, "service_running", return_value=True):
            self.assertIn("run setup", toggl_secret.describe_failure())


class SecureReadyTests(unittest.TestCase):
    def test_a_missing_collection_is_a_problem_not_a_crash(self):
        with patch.object(toggl_secret, "find_collection", return_value=None):
            path, problem = toggl_secret.secure_ready()
        self.assertIsNone(path)
        self.assertIn("--secure-keyring", problem)

    def test_a_locked_collection_never_reaches_a_lookup(self):
        with patch.object(toggl_secret, "find_collection", return_value="/c"), \
             patch.object(toggl_secret, "is_locked", return_value=True):
            path, problem = toggl_secret.secure_ready()
        self.assertIsNone(path)
        self.assertIn("locked", problem)

    def test_an_unlocked_collection_is_cleared_for_use(self):
        with patch.object(toggl_secret, "find_collection", return_value="/c"), \
             patch.object(toggl_secret, "is_locked", return_value=False):
            path, problem = toggl_secret.secure_ready()
        self.assertEqual(path, "/c")
        self.assertIsNone(problem)

    def test_a_dbus_failure_becomes_a_sentence(self):
        with patch.object(toggl_secret, "find_collection",
                          side_effect=toggl_secret.SecretError("bus is gone")):
            path, problem = toggl_secret.secure_ready()
        self.assertIsNone(path)
        self.assertEqual(problem, "bus is gone")


class UnlockTests(unittest.TestCase):
    def test_an_already_open_keyring_is_not_re_unlocked(self):
        # gnome-keyring accepts any password for an unlocked collection, so a
        # blind unlock would confirm the wrong password as correct.
        with patch.object(toggl_secret, "_bus", return_value=(None, None, None)), \
             patch.object(toggl_secret, "is_locked", return_value=False), \
             patch.object(toggl_secret, "_call") as call:
            self.assertEqual(toggl_secret.unlock("anything", "/c"), "/c")
        call.assert_not_called()

    def test_no_collection_names_the_command_that_makes_one(self):
        with patch.object(toggl_secret, "_bus", return_value=(None, None, None)), \
             patch.object(toggl_secret, "find_collection", return_value=None):
            with self.assertRaises(toggl_secret.SecretError) as caught:
                toggl_secret.unlock("pw")
        self.assertIn("--secure-keyring", str(caught.exception))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        patcher = patch.dict(os.environ, {"XDG_DATA_HOME": self.root}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mode_and_set_mode(self):
        self.assertEqual(toggl_secret.main(["set-mode", "secure"]), 0)
        self.assertEqual(toggl_secret.mode(), toggl_secret.MODE_SECURE)

    def test_an_unknown_command_is_refused(self):
        with patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(toggl_secret.main(["frobnicate"]), 2)
            self.assertEqual(toggl_secret.main([]), 2)

    def test_a_secret_error_becomes_exit_one(self):
        with patch.object(toggl_secret, "find_collection",
                          side_effect=toggl_secret.SecretError("nope")), \
             patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(toggl_secret.main(["path"]), 1)


if __name__ == "__main__":
    unittest.main()
