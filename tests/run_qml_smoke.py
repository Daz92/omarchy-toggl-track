#!/usr/bin/env python3
"""Hidden panel integration check in a live Quickshell session; no Toggl I/O."""
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    repo = Path(__file__).resolve().parents[1]
    shell = Path('/usr/share/omarchy/shell')
    with tempfile.TemporaryDirectory(prefix='toggl-qml-smoke-') as directory:
        root = Path(directory)
        for source in shell.iterdir():
            if source.is_dir():
                (root / source.name).symlink_to(source, target_is_directory=True)
        (root / 'Plugin').symlink_to(repo, target_is_directory=True)
        shutil.copy(repo / 'tests/qml/shell.qml', root / 'shell.qml')
        try:
            result = subprocess.run(['qs', '-p', str(root)], capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or b'') + (error.stderr or b'')
            raise SystemExit(output.decode(errors='replace') if isinstance(output, bytes) else output)
        output = result.stdout + result.stderr
        if result.returncode or 'TOGGL_SMOKE_OK' not in output or any(
                error in output for error in ('WARN scene:', 'ERROR:', 'TypeError:', 'ReferenceError:', 'binding loop')):
            raise SystemExit(output)
        print('QML smoke passed: lazy scopes, drafts, background isolation, stale results')


if __name__ == '__main__':
    main()
