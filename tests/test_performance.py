"""Regression coverage for bounded inference and foreground/background isolation."""
import concurrent.futures
import json
import os
from pathlib import Path
import random
import tempfile
import time
import unittest
from unittest.mock import patch

import toggl_api as api
import toggl_perf as perf
import test_toggl_api as fixtures
from test_toggl_api import CacheClient, FakeClient, Response, aw_event

BLOCK = {"index": 0, "label": "panel", "start": "2026-08-19T10:00:00Z", "seconds": 600,
         "topics": [{"name": "panel", "seconds": 600}], "apps": [], "domains": []}
PAYLOAD = {"workspace_id": 4, "blocks": [BLOCK], "projects": [{"id": 7, "name": "Project"}]}


class CacheTests(unittest.TestCase):
    def test_partition_fingerprint_expiry_corruption_and_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            now = [time.time()]
            cache = perf.InferenceCache(root, ["account", 4], lambda: now[0])
            key = cache.key("embedding", "model-a", "private title")
            cache.put(key, [1.0])
            self.assertEqual(cache.get(key), [1.0])
            self.assertIsNone(cache.get(cache.key("embedding", "model-b", "private title")))
            other = perf.InferenceCache(root, ["account", 5])
            self.assertIsNone(other.get(other.key("embedding", "model-a", "private title")))
            self.assertEqual((cache.root / (key + ".json")).stat().st_mode & 0o777, 0o600)
            self.assertNotIn("private title", (cache.root / (key + ".json")).read_text())
            now[0] += perf.CACHE_TTL
            self.assertIsNone(cache.get(key))
            (cache.root / (key + ".json")).write_text("broken")
            self.assertIsNone(cache.get(key))
            self.assertIsNone(cache.key("embedding", None, "unknown model"))

    def test_global_size_limit_across_partitions(self):
        with tempfile.TemporaryDirectory() as root, patch.object(perf, "CACHE_BYTES", 1024):
            for i in range(20):
                cache = perf.InferenceCache(root, ["account", i])
                cache.put(cache.key("description", "m", i), "x" * 200)
            self.assertLessEqual(sum(p.stat().st_size for p in (Path(root) / "inference").glob("*.json")), 1024)

    def test_embeddings_deduplicate_and_cache_across_process_instances(self):
        calls = []
        def embed(request, timeout):
            inputs = json.loads(request.data)["input"]
            calls.append(inputs)
            return Response({"data": [{"index": i, "embedding": [float(i + 1), 0.0]} for i in reversed(range(len(inputs)))]})
        with tempfile.TemporaryDirectory() as root, patch.object(api, "model_fingerprint", return_value="model"):
            first = api.TogglAPI(CacheClient(), cache_root=root, embed_opener=embed)
            self.assertEqual(first._vectors(["a", "a", "b"], 4), [[1.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
            second = api.TogglAPI(CacheClient(), cache_root=root, embed_opener=embed)
            self.assertEqual(second._vectors(["b", "a"], 4), [[2.0, 0.0], [1.0, 0.0]])
            self.assertEqual(calls, [["a", "b"]])

    def test_description_cache_and_invalid_output_not_cached(self):
        calls = []
        def classify(request, timeout):
            calls.append(1)
            return Response({"choices": [{"message": {"content": json.dumps({"description": "Improve panel layout"})}}]})
        with tempfile.TemporaryDirectory() as root, patch.object(api, "model_fingerprint", return_value="model"):
            for _ in range(2):
                result = api.TogglAPI(CacheClient(), cache_root=root, classify_opener=classify).classify(PAYLOAD)
                self.assertEqual(result["results"][0]["description"], "Improve panel layout")
            self.assertEqual(len(calls), 1)
            changed = dict(PAYLOAD, blocks=[dict(BLOCK, topics=[{"name": "different", "seconds": 600}])])
            bad = lambda request, timeout: Response({"choices": [{"message": {"content": '{"description": 42}'}}]})
            broken = api.TogglAPI(CacheClient(), cache_root=root, classify_opener=bad).classify(changed)
            self.assertTrue(broken["degraded"])
            api.TogglAPI(CacheClient(), cache_root=root, classify_opener=classify).classify(changed)
            self.assertEqual(len(calls), 2)


class BackgroundTests(unittest.TestCase):
    def test_global_deadline_includes_embedding_and_returns_partial_results(self):
        clock = [0.0]
        timeouts = []
        def embed(request, timeout):
            clock[0] += 5
            return Response({"data": [{"embedding": [1.0]}]})
        def classify(request, timeout):
            timeouts.append(timeout)
            clock[0] += 16
            return Response({"choices": [{"message": {"content": '{"description":"Work on panel"}'}}]})
        service = api.TogglAPI(FakeClient([]), embed_opener=embed, classify_opener=classify)
        payload = dict(PAYLOAD, blocks=[BLOCK, dict(BLOCK, index=1)])
        with patch.object(api.time, "monotonic", side_effect=lambda: clock[0]):
            result = service.classify(payload)
        self.assertEqual(timeouts, [15])
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["elapsed_ms"], 21000)

    def test_foreground_apply_does_no_inference_and_draining_is_idempotent(self):
        calls = []
        def embed(request, timeout):
            calls.append(1)
            return Response({"data": [{"embedding": [1.0, 0.0]}]})
        with tempfile.TemporaryDirectory() as root:
            service = api.TogglAPI(FakeClient([[], {"id": 77, "workspace_id": 4, "project_id": 7, "description": "Work"}]),
                                   data_root=root, embed_opener=embed)
            service.create_entry({"workspace_id": 4, "start": BLOCK["start"], "duration": 600,
                                  "description": "Work", "project_id": 7, "block": BLOCK})
            self.assertEqual(calls, [])
            for _ in range(2):
                service.enrich_day({"workspace_id": 4, "blocks": [], "projects": []})
            self.assertEqual(calls, [1])
            self.assertEqual(api.HistoryStore(root).load()["centroids"]["7"]["count"], 1)

    def test_deferred_day_never_calls_embedder(self):
        with tempfile.TemporaryDirectory() as root:
            service = api.TogglAPI(FakeClient([]), data_root=root,
                activitywatch_opener=fixtures.HistoryStoreTests()._aw("panel"),
                embed_opener=lambda *a, **k: self.fail("foreground inference"))
            result = service.day_activity({"workspace_id": 4, "date": "2026-08-19", "entries": [], "defer_enrichment": True})
            self.assertTrue(result["blocks"])
            self.assertIn("history", result["blocks"][0])

    def test_concurrent_history_writers_keep_every_entry_and_skip_unchanged_saves(self):
        with tempfile.TemporaryDirectory() as root:
            def learn(i):
                store = api.HistoryStore(root)
                with store.transaction():
                    store.learn(BLOCK, {"id": i, "description": "Work", "project_id": 7})
                    store.record_correction(BLOCK, {}, {"description": "Work", "project_id": 7})
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(learn, range(30)))
            store = api.HistoryStore(root)
            self.assertEqual(store.records[0]["seen"], 30)
            self.assertEqual(store.correction_stats()["total"], 30)
            with patch.object(store, "save", wraps=store.save) as save:
                with store.transaction():
                    store.learn(BLOCK, {"id": 0, "description": "Work", "project_id": 7})
                save.assert_not_called()

    def test_inference_does_not_hold_history_lock(self):
        with tempfile.TemporaryDirectory() as root:
            history = api.HistoryStore(root)
            with history.transaction():
                history.queue_vector(BLOCK, {"id": 1, "project_id": 7}, 4)
            def embed(request, timeout):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(api.HistoryStore(root).learn, BLOCK,
                                {"id": 2, "project_id": 7, "description": "Concurrent"}).result(timeout=2)
                return Response({"data": [{"embedding": [1.0]}]})
            service = api.TogglAPI(FakeClient([]), data_root=root, embed_opener=embed)
            service.enrich_day({"workspace_id": 4, "blocks": []})
            self.assertEqual(api.HistoryStore(root).records[0]["description"], "Concurrent")
            self.assertFalse(api.HistoryStore(root).load()["pending_vectors"])


class RuntimeTests(unittest.TestCase):
    def test_migration_preserves_paths_workarounds_and_is_idempotent(self):
        original = '[Service]\nEnvironment=GGML_VK_DISABLE_COOPMAT=1\nExecStart="/custom path/llama-server" --model "/custom path/model.gguf" --parallel 4 --cache-ram=8192 --ctx-size 4096 --device Vulkan0 --n-gpu-layers 99\nRestart=on-failure\n'
        first, binary, _ = perf.optimized_unit(original)
        self.assertEqual(binary, "/custom path/llama-server")
        self.assertIn('"Vulkan0"', first)
        self.assertIn('GGML_VK_DISABLE_COOPMAT=1', first)
        self.assertEqual(first, perf.optimized_unit(first)[0])
        embed, _, _ = perf.optimized_unit(original, True)
        self.assertNotIn("Vulkan0", embed)
        self.assertIn('"--device" "none"', embed)
        self.assertIn('"--sleep-idle-seconds" "60"', embed)


class SegmentationTests(unittest.TestCase):
    def test_sorted_intersection_matches_cartesian_reference(self):
        # Compare the complete segmentation result with the original algorithm,
        # including overlapping windows and unsorted ActivityWatch events.
        import inspect
        source = inspect.getsource(api.segment_blocks)
        start = source.index('    active_index = 0')
        end = source.index('            start = max(window["start"], active_start)', start)
        reference_source = source[:start] + '    for window_order, window in enumerate(window_spans):\n        for active_start, active_end in active_intervals:\n' + source[end:]
        namespace = dict(vars(api))
        exec(reference_source, namespace)
        reference = namespace['segment_blocks']
        rng = random.Random(17)
        origin = api._event_datetime('2026-08-19T00:00:00Z')
        def event(offset, duration, data):
            return aw_event(api._iso_datetime(origin + api.timedelta(seconds=offset)), duration, data)
        windows = [event(rng.randrange(8000), rng.randrange(1, 800), {"app": "Editor", "title": str(i % 9)}) for i in range(250)]
        afk = [event(i, 100, {"status": "not-afk"}) for i in range(0, 9000, 200)]
        rng.shuffle(afk)
        for intervals in (afk, [], None):
            self.assertEqual(api.segment_blocks(windows, intervals), reference(windows, intervals))


if __name__ == '__main__':
    unittest.main()
