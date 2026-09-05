# Performance validation — 2026-09-05

Measured on the installed b10816 Vulkan runtime, Granite 4.0 H 1B Q4_K_M
and BGE-small-en-v1.5 Q8_0. The model files, description prompt and ranking
formula were retained.

## Runtime memory

| Process | Original resident RAM | Optimized resident RAM after inference and 65 seconds idle |
|---|---:|---:|
| Description server | 2,586,712 KiB | 403,484 KiB |
| Embedding server | 268,164 KiB | 147,728 KiB |
| Combined | 2,854,876 KiB | 551,212 KiB |

Combined RSS decreased **80.7%**, from 2.72 GiB to 538 MiB. The description
server alone decreased **84.4%**. Both reported `is_sleeping: true` after idle.
The optimized combined PSS was 343,482 KiB (335 MiB); the original PSS was
not captured, so no PSS percentage reduction is claimed. RSS counts shared
library pages in both processes. Systemd's service memory also includes
charged file cache and is not interchangeable with RSS or PSS.

Changes: one inference slot per server, `--cache-ram 0`, native
`--sleep-idle-seconds 60`, explicit CPU placement for the embedder, and
service-local allocator defaults (`MALLOC_ARENA_MAX=2`,
`MALLOC_TRIM_THRESHOLD_=131072`, `MALLOC_MMAP_THRESHOLD_=131072`). The
allocator comparison used separate temporary server processes: sleeping
classifier PSS was 261,327 KiB without these defaults and 209,687 KiB with
them. Those isolated runs used a different synthetic prompt; they are not
the final end-to-end measurements above.

Native sleep retains the server executable, libraries and some allocator/driver
state. It does not reduce process memory to zero. Model pages in the filesystem
cache may remain reclaimable. No post-change GPU-memory percentage is claimed.

References: [pinned llama.cpp sleep behavior](https://github.com/ggml-org/llama.cpp/blob/b10816/tools/server/README.md#sleeping-on-idle),
[glibc allocator parameters](https://sourceware.org/glibc/manual/latest/html_node/Malloc-Tunable-Parameters.html).

## Responsiveness and output checks

- Three synthetic blocks, starting with both models asleep: **3.087 seconds**
  for embedding and all three valid descriptions; no degradation. A repeat
  through a fresh Python API instance and the same inference cache: **2 ms**.
  An earlier run measured 2.854 seconds and 1 ms. These are smoke measurements,
  not latency percentiles or a comprehensive language-quality evaluation.
- Complete segmentation output matched the previous implementation on the
  eight largest cached ActivityWatch days: **66 blocks**, including a day with
  **5,608 window events**. One pass on that largest day measured 74.25 ms before
  and 53.37 ms after; smaller-day timings were mixed. Treat correctness as the
  demonstrated result, not those single-pass timings as a universal speedup.
- History suggestions and project scores matched the previous implementation
  on those 66 blocks, with five vector cases per block (including no vector).
- Python regressions cover cache expiry, identity/partition separation,
  global size bounds, deduplicated embeddings, input/output ordering, partial
  deadline results, deferred learning, concurrent writers, idempotent vector
  updates, and equivalence to Cartesian interval intersection.
- JavaScript regressions cover stale edits and changed activity. The hidden
  Quickshell smoke test exercises lazy scope loading, draft retention, foreground
  request isolation and rejection of a different workspace's results.

The foreground `day_activity` response still contains blocks and local history
candidates. The panel sends `defer_enrichment: true`, then uses the separate
`enrich_day` action with workspace, date, generation and block signatures.
External callers that omit the new flag retain synchronous enrichment.
`create_entry` acknowledges the Toggl write after local learning is persisted;
pending embeddings are stored in `history.json` and drained idempotently by
background enrichment. History locks are never held during model HTTP calls.

## Reproduction and installation

Run the Python/JavaScript checks listed in the README. On a live Omarchy desktop,
`python3 tests/run_qml_smoke.py` launches a temporary hidden shell with Toggl
request methods disabled; it fails on QML runtime warnings as well as assertions.

`./setup --update-runtime` updates existing service definitions while retaining
model paths, runtime paths, existing environment overrides and enablement. It
keeps the first backup at `<unit>.before-memory-update` and restarts active
services only. The tested installation uses a development symlink to this repo;
`omarchy-restart-shell` was run to load the QML changes.

The release gate's code, syntax and packaging checks pass. Its final clean-tree
requirement intentionally fails while these implementation changes are uncommitted;
no release artifact or tag was produced.
