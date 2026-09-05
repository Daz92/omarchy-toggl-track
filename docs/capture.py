#!/usr/bin/env python3
"""Photographs the running panel against demo data.

Run it with the Omarchy shell already running:

    python3 docs/capture.py

It turns demo mode on, moves to an empty workspace for a clean backdrop, drives
the panel with real keystrokes, captures each state, and turns demo mode off
again in a `finally` -- so even an interrupted run leaves the panel showing the
user's own data rather than fixtures.

Locating the panel: it is drawn inside a full-screen layer surface, so
`hyprctl layers -j` reports only the screen-sized parent, and hunting for its
accent border by colour also finds focused window borders, which share the
theme accent. Diffing each frame against one taken with the panel closed has
neither problem and adapts to a panel whose height changes with its content.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMAGES = REPO / "docs" / "images"
SHELL = "/usr/share/omarchy/shell"
PLUGIN = "daz.toggl-track"

sys.path.insert(0, str(REPO))
import toggl_demo  # noqa: E402  -- needs REPO on sys.path first

BASELINE = None


def run(*args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=30, **kwargs)


def ipc(*call):
    return run("qs", "-p", SHELL, "ipc", "call", PLUGIN, *call)


def key(*args, settle=0.45):
    """One keystroke through wtype. Every capture follows a settle pause;
    without one the screenshot races the render."""
    run("wtype", *args)
    time.sleep(settle)


def type_text(text, settle=0.6):
    run("wtype", text)
    time.sleep(settle)


def ctrl(letter, settle=0.6):
    key("-M", "ctrl", "-k", letter, "-m", "ctrl", settle=settle)


def backspace(count):
    for _ in range(count):
        key("-k", "BackSpace", settle=0.02)
    time.sleep(0.4)


# --- workspace and baseline -------------------------------------------------

def current_workspace():
    try:
        return json.loads(run("hyprctl", "activeworkspace", "-j").stdout).get("id")
    except Exception:
        return None


def goto_empty_workspace():
    """A screenshot taken over a terminal shows that terminal around the panel.
    An empty workspace gives a clean wallpaper backdrop and makes the panel
    trivially separable from it."""
    try:
        used = {w.get("id") for w in json.loads(run("hyprctl", "workspaces", "-j").stdout)}
    except Exception:
        used = set()
    for candidate in range(1, 40):
        if candidate not in used:
            # This Hyprland runs a Lua config, where `dispatch workspace N`
            # is a syntax error; the dispatcher form is what its own
            # bindings.lua uses.
            run("hyprctl", "dispatch", 'hl.dsp.focus({workspace="%d"})' % candidate)
            time.sleep(1.2)
            return candidate
    return None


def capture_baseline():
    global BASELINE
    ipc("close")
    time.sleep(1.2)
    IMAGES.mkdir(parents=True, exist_ok=True)
    BASELINE = IMAGES / "baseline.png"
    subprocess.run(["grim", str(BASELINE)], capture_output=True, timeout=30)
    print("baseline captured")


def bar_height():
    """Native pixels of the Omarchy bar, so the diff can ignore it."""
    try:
        layers = json.loads(run("hyprctl", "layers", "-j").stdout)
        scale = monitor_scale()
        for monitor in layers.values():
            for group in (monitor.get("levels") or {}).values():
                for layer in group:
                    if (layer.get("namespace") or "") == "omarchy-bar":
                        return int(layer["h"] * scale) + 8
    except Exception:
        pass
    return 64


def monitor_scale():
    try:
        return float(json.loads(run("hyprctl", "monitors", "-j").stdout)[0].get("scale") or 1)
    except Exception:
        return 2.0


def diff_bbox(baseline, shot, pad=12):
    from PIL import Image, ImageChops

    before = Image.open(baseline).convert("RGB")
    after = Image.open(shot).convert("RGB")
    mask = ImageChops.difference(before, after).convert("L").point(lambda v: 255 if v > 24 else 0)
    # The bar's clock ticks between the two frames, and the bar spans the whole
    # screen -- left in, it stretches every crop to full width.
    top = bar_height()
    mask.paste(0, (0, 0, mask.width, min(top, mask.height)))
    box = mask.getbbox()
    if not box:
        return None
    x0, y0, x1, y1 = box
    if (x1 - x0) < 200 or (y1 - y0) < 120:
        return None
    return (max(0, x0 - pad), max(0, y0 - pad),
            min(after.width, x1 + pad), min(after.height, y1 + pad))


def capture_panel(name):
    """Full frame, then crop to whatever the panel changed."""
    from PIL import Image

    IMAGES.mkdir(parents=True, exist_ok=True)
    full = IMAGES / ("full-%s.png" % name)
    result = subprocess.run(["grim", str(full)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise SystemExit("grim failed for %s: %s" % (name, result.stderr.strip()))
    target = IMAGES / ("raw-%s.png" % name)
    box = diff_bbox(BASELINE, full) if BASELINE else None
    if box:
        Image.open(full).convert("RGB").crop(box).save(target)
        full.unlink()
    else:
        # Better a wrong frame than a missing one: the mistake is then visible
        # rather than silently shipped.
        print("  ! could not locate the panel for %s; keeping the full frame" % name)
        full.replace(target)
    print("  captured %s" % target.name)
    return target


# --- demo mode --------------------------------------------------------------

def demo_on(running=False):
    marker = Path(toggl_demo.marker_path())
    marker.write_text("screenshots\n")
    runmarker = Path(toggl_demo.marker_path() + "-running")
    if running:
        runmarker.write_text("running\n")
    elif runmarker.exists():
        runmarker.unlink()
    return marker


def demo_off():
    for path in (Path(toggl_demo.marker_path()), Path(toggl_demo.marker_path() + "-running")):
        if path.exists():
            path.unlink()


def reload_panel(settle=2.4):
    """The shell ran bootstrap() at startup, so the panel holds real data in
    memory when the marker appears. This is what replaces it."""
    ctrl("r", settle=settle)


# --- the shot list ----------------------------------------------------------

def shots():
    print("timer scope")
    ipc("open")
    time.sleep(2.0)
    reload_panel()
    capture_panel("timer-recent")

    print("typing a description")
    type_text("tide model calibration")
    capture_panel("timer-typing")

    print("binding a project")
    type_text(" @harbour")
    capture_panel("timer-project")
    backspace(len("tide model calibration @harbour") + 4)

    print("help overlay, timer")
    type_text("?", settle=1.1)
    capture_panel("help-timer")
    key("-k", "Escape", settle=0.7)

    print("running timer")
    demo_on(running=True)
    reload_panel()
    capture_panel("timer-running")
    demo_on(running=False)
    reload_panel()

    print("day scope")
    ctrl("d", settle=3.0)
    reload_panel(settle=3.4)
    capture_panel("day-blocks")

    print("inspect drawer")
    key("-k", "space", settle=1.2)
    capture_panel("day-inspect")
    key("-k", "space", settle=0.7)

    print("edit drawer")
    type_text("e", settle=1.2)
    capture_panel("day-edit")
    key("-k", "Escape", settle=0.9)

    print("help overlay, day")
    type_text("?", settle=1.1)
    capture_panel("help-day")
    key("-k", "Escape", settle=0.7)

    print("calendar scope")
    ctrl("l", settle=3.4)
    capture_panel("calendar-week")
    type_text("w", settle=2.2)
    capture_panel("calendar-fortnight")
    type_text("w", settle=2.2)
    capture_panel("calendar-month")
    type_text("w", settle=2.0)

    print("settings")
    ctrl("t", settle=1.6)
    ctrl(",", settle=1.4)
    capture_panel("timer-settings")
    ctrl(",", settle=0.9)


def main():
    if not run("qs", "-p", SHELL, "ipc", "show").stdout:
        raise SystemExit("the Omarchy shell is not running, or its IPC is unreachable")
    workspace = current_workspace()
    marker = demo_on()
    print("demo mode on (%s)" % marker)
    try:
        goto_empty_workspace()
        # Restart the shell with the marker already in place. Without this the
        # panel keeps whatever it loaded before demo mode -- and a scope switch
        # only fetches when its scope has never been loaded, so the day scope
        # would photograph the user's real window titles from memory.
        print("restarting the shell so nothing real is left in memory")
        run("omarchy-restart-shell")
        time.sleep(9)
        capture_baseline()
        shots()
    finally:
        demo_off()
        print("demo mode off; restarting the shell back onto real data")
        ipc("close")
        run("omarchy-restart-shell")
        time.sleep(8)
        if workspace is not None:
            run("hyprctl", "dispatch", 'hl.dsp.focus({workspace="%s"})' % workspace)
    raw = sorted(IMAGES.glob("raw-*.png"))
    print("\nwrote %d images to %s" % (len(raw), IMAGES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
