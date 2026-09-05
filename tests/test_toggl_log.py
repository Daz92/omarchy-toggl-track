import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import toggl_log


def read_lines(directory):
    path = os.path.join(directory, "logs", "toggl.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream.read().splitlines() if line]


class LoggerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_writes_a_record_with_ts_and_lvl(self):
        logger = toggl_log.Logger(self.dir, "info")
        self.assertTrue(logger.write("info", action="sync", ms=412, ok=True))
        records = read_lines(self.dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "sync")
        self.assertEqual(records[0]["lvl"], "info")
        self.assertTrue(records[0]["ts"].endswith("Z"))

    def test_off_creates_no_file(self):
        logger = toggl_log.Logger(self.dir, "off")
        self.assertFalse(logger.write("errors", action="sync"))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "logs")))

    def test_errors_level_drops_info_records(self):
        logger = toggl_log.Logger(self.dir, "errors")
        logger.write("info", action="sync")
        logger.write("errors", action="sync", error="boom")
        records = read_lines(self.dir)
        self.assertEqual([r["lvl"] for r in records], ["errors"])

    def test_info_omits_sensitive_keys(self):
        logger = toggl_log.Logger(self.dir, "info")
        logger.write("info", action="day_activity", label="Refactor day segmentation",
                     description="secret work", counts={"blocks": 6})
        record = read_lines(self.dir)[0]
        self.assertNotIn("label", record)
        self.assertNotIn("description", record)
        self.assertEqual(record["counts"], {"blocks": 6})

    def test_info_omits_sensitive_keys_nested(self):
        logger = toggl_log.Logger(self.dir, "info")
        logger.write("info", action="classify", batch={"label": "x", "n": 3})
        record = read_lines(self.dir)[0]
        self.assertNotIn("label", record["batch"])
        self.assertEqual(record["batch"]["n"], 3)

    def test_debug_keeps_sensitive_keys(self):
        logger = toggl_log.Logger(self.dir, "debug")
        logger.write("debug", action="day_activity", label="Refactor day segmentation")
        self.assertEqual(read_lines(self.dir)[0]["label"], "Refactor day segmentation")

    def test_strings_truncate_at_500(self):
        logger = toggl_log.Logger(self.dir, "debug")
        logger.write("debug", action="x", label="a" * 900)
        self.assertEqual(len(read_lines(self.dir)[0]["label"]), 500)

    def test_unwritable_directory_disables_logging_without_raising(self):
        blocked = os.path.join(self.dir, "blocked")
        os.makedirs(blocked)
        os.chmod(blocked, 0o500)
        self.addCleanup(os.chmod, blocked, 0o700)
        logger = toggl_log.Logger(blocked, "info")
        self.assertFalse(logger.write("info", action="sync"))

    def test_non_serialisable_field_returns_false_without_raising(self):
        logger = toggl_log.Logger(self.dir, "info")
        self.assertFalse(logger.write("info", action="sync", blob={1, 2, 3}))
        self.assertEqual(read_lines(self.dir), [])

    def test_log_directory_is_private(self):
        toggl_log.Logger(self.dir, "info").write("info", action="sync")
        mode = os.stat(os.path.join(self.dir, "logs")).st_mode & 0o777
        self.assertEqual(mode, 0o700)

    def _seed(self, records):
        root = os.path.join(self.dir, "logs")
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, "toggl.jsonl")
        with open(path, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")
        return path

    def test_prune_drops_records_older_than_24h(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        old = toggl_log._stamp(now - timedelta(hours=25))
        new = toggl_log._stamp(now - timedelta(hours=1))
        pad = "x" * 2000
        path = self._seed(
            [{"ts": old, "lvl": "info", "pad": pad}] * 400
            + [{"ts": new, "lvl": "info", "pad": pad}] * 400
        )
        self.assertGreater(os.path.getsize(path), toggl_log.LOG_MAX_BYTES)
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.prune()
        stamps = {record["ts"] for record in read_lines(self.dir)}
        self.assertEqual(stamps, {new})

    def test_prune_is_skipped_below_the_size_bound(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        old = toggl_log._stamp(now - timedelta(hours=48))
        self._seed([{"ts": old, "lvl": "info"}])
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.prune()
        self.assertEqual(len(read_lines(self.dir)), 1)

    def test_prune_drops_oldest_survivors_when_still_over_size(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        pad = "x" * 4000
        records = [
            {"ts": toggl_log._stamp(now - timedelta(minutes=index)), "lvl": "info", "pad": pad}
            for index in range(600, 0, -1)
        ]
        self._seed(records)
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.prune()
        path = os.path.join(self.dir, "logs", "toggl.jsonl")
        self.assertLessEqual(os.path.getsize(path), toggl_log.LOG_MAX_BYTES)
        kept = read_lines(self.dir)
        self.assertGreater(len(kept), 0)
        self.assertEqual(kept[-1]["ts"], records[-1]["ts"])

    def test_prune_drops_malformed_lines_without_aborting(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        good = toggl_log._stamp(now - timedelta(hours=1))
        root = os.path.join(self.dir, "logs")
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, "toggl.jsonl")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("{not json\n")
            for _ in range(500):
                stream.write(json.dumps({"ts": good, "lvl": "info", "pad": "x" * 2500}) + "\n")
        self.assertGreater(os.path.getsize(path), toggl_log.LOG_MAX_BYTES)
        toggl_log.Logger(self.dir, "info", clock=lambda: now).prune()
        records = read_lines(self.dir)
        self.assertTrue(records)
        self.assertTrue(all(record["ts"] == good for record in records))

    def test_prune_runs_once_per_instance(self):
        logger = toggl_log.Logger(self.dir, "info")
        logger.prune()
        self.assertTrue(logger._pruned)
        logger.prune()

    def test_write_prunes_after_appending(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        old = toggl_log._stamp(now - timedelta(hours=30))
        self._seed([{"ts": old, "lvl": "info", "pad": "x" * 3000}] * 400)
        logger = toggl_log.Logger(self.dir, "info", clock=lambda: now)
        logger.write("info", action="sync")
        records = read_lines(self.dir)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "sync")


if __name__ == "__main__":
    unittest.main()
