"""Disposable inference caching and installed runtime migration (stdlib only)."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

CACHE_BYTES = 16 * 1024 * 1024
CACHE_TTL = 24 * 60 * 60
UNITS = ("omarchy-toggl-track-llama-server.service", "omarchy-toggl-track-embedder.service")


def unit_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd/user"


def model_fingerprint(kind):
    """Invalidate on runtime/config/model replacement without waking a model."""
    try:
        content = (unit_dir() / UNITS[kind == "embedding"]).read_text()
        command = next(line[10:] for line in content.splitlines() if line.startswith("ExecStart="))
        args = shlex.split(command)
        model = args[args.index("--model") + 1]
        stamps = [(p, os.stat(p).st_size, os.stat(p).st_mtime_ns) for p in (args[0], model)]
        return hashlib.sha256(json.dumps([content, stamps]).encode()).hexdigest()
    except (OSError, ValueError, StopIteration):
        return None  # Unknown model identity: never reuse potentially stale output.


class InferenceCache:
    def __init__(self, root, partition, clock=time.time):
        self.root = Path(root) / "inference"
        self.partition = partition
        self.clock = clock

    def key(self, kind, fingerprint, value):
        if not fingerprint:
            return None
        raw = json.dumps([1, self.partition, kind, fingerprint, value], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key):
        if key is None:
            return None
        try:
            path = self.root / (key + ".json")
            if path.stat().st_size > CACHE_BYTES:
                return None
            value = json.loads(path.read_text())
            if 0 <= self.clock() - value["at"] < CACHE_TTL:
                return value["value"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def put(self, key, value):
        if key is None:
            return
        temporary = None
        try:
            payload = json.dumps({"at": self.clock(), "value": value}, separators=(",", ":"), allow_nan=False).encode()
            if len(payload) > CACHE_BYTES:
                return
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.root, 0o700)
            with os.fdopen(os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR, 0o600), "r+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as stream:
                    temporary = stream.name
                    stream.write(payload)
                os.replace(temporary, self.root / (key + ".json"))
                temporary = None
                files = sorted(((p.stat().st_mtime, p.stat().st_size, p) for p in self.root.glob("*.json")), reverse=True)
                used = 0
                for stamp, size, path in files:
                    if used + size > CACHE_BYTES or self.clock() - stamp >= CACHE_TTL:
                        path.unlink(missing_ok=True)
                    else:
                        used += size
        except (OSError, ValueError, TypeError):
            pass
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


def optimized_unit(content, embedder=False):
    """Preserve custom paths, environment and service policy; replace only tuning."""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("ExecStart="):
            continue
        args = shlex.split(line[10:])
        options = {"--sleep-idle-seconds": "60", "--parallel": "1", "--cache-ram": "0"}
        aliases = {"-np": "--parallel", "-cram": "--cache-ram"}
        if embedder:
            options.update({"--device": "none", "--n-gpu-layers": "0"})
            aliases.update({"-dev": "--device", "-ngl": "--n-gpu-layers", "--gpu-layers": "--n-gpu-layers"})
        out, offset = [], 0
        while offset < len(args):
            name = args[offset].split("=", 1)[0]
            if aliases.get(name, name) in options:
                offset += 1 if "=" in args[offset] else 2
            else:
                out.append(args[offset])
                offset += 1
        for name, value in options.items():
            out.extend((name, value))
        # systemd supports double-quoted arguments, not shell operators.
        lines[index] = "ExecStart=" + " ".join(json.dumps(arg, ensure_ascii=False) for arg in out)
        # Bound allocator retention after model unload. Respect explicit user
        # overrides; these defaults apply only to these two service processes.
        allocator = {"MALLOC_ARENA_MAX": "2", "MALLOC_TRIM_THRESHOLD_": "131072",
                     "MALLOC_MMAP_THRESHOLD_": "131072"}
        lines[index:index] = ["Environment=%s=%s" % (name, value) for name, value in allocator.items()
                              if name + "=" not in content]
        return "\n".join(lines) + "\n", args[0], options
    raise ValueError("service has no ExecStart")


def validate_runtime(binary, embedder=False):
    run = subprocess.run([binary, "--help"], capture_output=True, text=True, check=True)
    help_text = run.stdout + run.stderr
    required = ["--sleep-idle-seconds", "--parallel", "--cache-ram"]
    if embedder:
        required += ["--device", "--n-gpu-layers"]
    if any(option not in help_text for option in required):
        raise ValueError("installed llama-server lacks required memory options; upgrade its runtime first")


def update_runtime():
    prepared = []
    for unit in UNITS:
        path = unit_dir() / unit
        original = path.read_text()
        content, binary, options = optimized_unit(original, unit == UNITS[1])
        validate_runtime(binary, unit == UNITS[1])
        prepared.append((path, original, content))
    for path, original, content in prepared:
        backup = path.with_name(path.name + ".before-memory-update")
        if not backup.exists():
            backup.write_text(original)
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            stream.write(content)
        os.replace(stream.name, path)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "try-restart", *UNITS], check=True)
    print("Updated both runtimes; active services restarted. Models and credentials retained.")


if __name__ == "__main__":
    import sys
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "--check-runtime":
            validate_runtime(sys.argv[2], sys.argv[3] == "embedding")
        elif len(sys.argv) == 1:
            update_runtime()
        else:
            raise ValueError("usage: toggl_perf.py [--check-runtime BINARY description|embedding]")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
