#!/usr/bin/env python3
"""Draws numbered callouts onto the captured screenshots.

    python3 docs/annotate.py

Reads `docs/images/raw-*.png` and writes `docs/images/<name>.png`. Callout
positions are fractions of the image, not pixels, so a recapture at a different
panel height keeps its markers roughly where they belong.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGES = Path(__file__).resolve().parents[1] / "docs" / "images"

MONO = "/usr/share/fonts/TTF/CaskaydiaMonoNerdFontMono-Regular.ttf"
MONO_BOLD = "/usr/share/fonts/TTF/CaskaydiaMonoNerdFontMono-Bold.ttf"
SANS = "/usr/share/fonts/noto/NotoSans-Regular.ttf"
SANS_BOLD = "/usr/share/fonts/noto/NotoSans-Bold.ttf"

# Catppuccin Mocha, the palette docs/design-guide.html is written in.
INK = (30, 30, 46)
BADGE = (137, 180, 250)
BADGE_INK = (17, 17, 27)
CAPTION = (205, 214, 244)
MUTED = (137, 143, 163)
RULE = (69, 71, 90)

# name -> (caption, [(x fraction, y fraction, text), ...])
# The fractions were read off the captures; a marker sits just left of what it
# points at, so the leader line runs rightwards into the panel.
CALLOUTS = {
    "timer-recent": ("The timer scope, with an empty command line", [
        (0.03, 0.10, "Type here to search or start; the chips show which scope you are in"),
        (0.03, 0.28, "Your ten most recent entries, ready to continue with Enter"),
        (0.68, 0.28, "Project and task, then how long that entry ran"),
        (0.03, 0.93, "The keys that work right now"),
    ]),
    "timer-typing": ("Typing a description", [
        (0.05, 0.30, "What you type becomes the entry description"),
        (0.05, 0.72, "Enter starts a timer with exactly this text"),
    ]),
    "timer-project": ("Attaching a project", [
        (0.05, 0.30, "@ filters your projects as you type"),
        (0.05, 0.72, "Enter picks one; the @token disappears and the project sticks"),
    ]),
    "timer-running": ("While a timer runs", [
        (0.04, 0.13, "The running entry, its elapsed time and where it is filed"),
        (0.03, 0.95, "^s stops it"),
    ]),
    "day-blocks": ("The day scope: what you actually did, block by block", [
        (0.03, 0.11, "Move between days with h and l; t returns to today"),
        (0.52, 0.11, "How many blocks are ready, unassigned, or clash with an entry"),
        (0.03, 0.42, "Each row is a block of activity, with the time and duration"),
        (0.80, 0.50, "~ marks a suggestion; confirm it before it counts as ready"),
        (0.60, 0.72, "A conflict: an entry already covers this time"),
        (0.03, 0.95, "Space inspects, e edits, Enter applies this one, Shift+Enter applies every ready one"),
    ]),
    "day-inspect": ("Inspecting a block", [
        (0.04, 0.16, "What the block is made of: how long, how fragmented, how much idle"),
        (0.04, 0.40, "When you were active inside the block"),
        (0.04, 0.62, "The window titles, apps and sites that made it up"),
    ]),
    "day-edit": ("Editing before you apply", [
        (0.04, 0.30, "The description that will be written to Toggl"),
        (0.04, 0.52, "@project and /task, the same syntax as the timer scope"),
        (0.04, 0.80, "Apply writes the entry; your correction also teaches the suggestions"),
    ]),
    "calendar-week": ("The calendar, one week at a time", [
        (0.30, 0.20, "W, 2W and M switch between week, fortnight and month"),
        (0.03, 0.44, "Entries in their real time positions, coloured by project"),
        (0.03, 0.66, "A dashed outline is activity you have not written up yet"),
        (0.03, 0.86, "Daily totals"),
    ]),
    "calendar-month": ("A month at a glance", [
        (0.03, 0.28, "Each day carries a stack of its projects"),
        (0.80, 0.28, "The week's total"),
        (0.03, 0.92, "Enter opens the day under the cursor in the Day scope"),
    ]),
    "help-timer": ("Press ? for the keys that work here", [
        (0.04, 0.22, "The keys for the scope you are in"),
        (0.52, 0.22, "The keys that work everywhere"),
    ]),
    "timer-settings": ("Settings, with ^,", [
        (0.04, 0.30, "Which workspace, and how much history to load"),
        (0.04, 0.74, "Turn the local classifier on; nothing it reads leaves the machine"),
    ]),
}


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def annotate(name, caption, markers):
    source = IMAGES / ("raw-%s.png" % name)
    if not source.exists():
        print("  ! missing %s" % source.name)
        return None
    shot = trimmed(source)
    width, height = shot.size

    scale = max(1.0, width / 1144.0)
    badge_r = int(17 * scale)
    gap = int(14 * scale)
    caption_h = int(52 * scale)
    text_size = int(19 * scale)
    caption_size = int(21 * scale)

    # A gutter on the left for the markers, and a caption strip underneath.
    gutter = int(width * 0.52)
    canvas = Image.new("RGB", (width + gutter, height + caption_h), INK)
    canvas.paste(shot, (gutter, 0))
    draw = ImageDraw.Draw(canvas)

    label_font = font(SANS, text_size)
    caption_font = font(SANS_BOLD, caption_size)
    number_font = font(MONO_BOLD, int(19 * scale))

    # Caption strip.
    draw.line([(0, height + 1), (canvas.width, height + 1)], fill=RULE, width=max(1, int(scale)))
    draw.text((int(18 * scale), height + int(caption_h * 0.28)), caption,
              font=caption_font, fill=CAPTION)

    # Two markers pointing at the same row would stack their badges and their
    # labels on top of each other, so badges are nudged apart vertically while
    # the leader line still lands on the real target.
    min_gap = int(58 * scale)
    badge_ys, last = [], None
    for _, fy, _text in markers:
        wanted = int(fy * height)
        if last is not None and wanted - last < min_gap:
            wanted = last + min_gap
        badge_ys.append(wanted)
        last = wanted
    overflow = (badge_ys[-1] if badge_ys else 0) - (height - int(10 * scale))
    if overflow > 0:
        badge_ys = [y - overflow for y in badge_ys]

    for index, ((fx, fy, text), badge_y) in enumerate(zip(markers, badge_ys), start=1):
        target_x = gutter + int(fx * width)
        target_y = int(fy * height)
        badge_x = gutter - int(26 * scale)

        draw.line([(badge_x + badge_r, badge_y), (target_x, target_y)],
                  fill=BADGE, width=max(2, int(2 * scale)))
        draw.ellipse([(target_x - int(4 * scale), target_y - int(4 * scale)),
                      (target_x + int(4 * scale), target_y + int(4 * scale))], fill=BADGE)
        draw.ellipse([(badge_x - badge_r, badge_y - badge_r),
                      (badge_x + badge_r, badge_y + badge_r)], fill=BADGE)
        number = str(index)
        box = draw.textbbox((0, 0), number, font=number_font)
        draw.text((badge_x - (box[2] - box[0]) / 2, badge_y - (box[3] - box[1]) / 2 - box[1]),
                  number, font=number_font, fill=BADGE_INK)

        # The label is right-aligned against the badge, wrapped to the gutter.
        words, lines, line = text.split(), [], ""
        limit = gutter - int(70 * scale)
        for word in words:
            probe = (line + " " + word).strip()
            if draw.textlength(probe, font=label_font) > limit and line:
                lines.append(line)
                line = word
            else:
                line = probe
        if line:
            lines.append(line)
        line_h = int(text_size * 1.4)
        start_y = badge_y - (len(lines) - 1) * line_h / 2
        for offset, row in enumerate(lines):
            row_w = draw.textlength(row, font=label_font)
            draw.text((badge_x - badge_r - gap - row_w, start_y + offset * line_h - text_size * 0.62),
                      row, font=label_font, fill=CAPTION if offset == 0 else MUTED)

    target = IMAGES / ("%s.png" % name)
    canvas.save(target)
    print("  wrote %s (%dx%d)" % (target.name, canvas.width, canvas.height))
    return target


TRIM = 11


def trimmed(source):
    """The capture pads its crop so the panel border is never clipped; that pad
    is a fringe of wallpaper. This takes it back to the border."""
    shot = Image.open(source).convert("RGB")
    if shot.width > TRIM * 4 and shot.height > TRIM * 4:
        shot = shot.crop((TRIM, TRIM, shot.width - TRIM, shot.height - TRIM))
    return shot


def write_plain():
    """Un-annotated panels, for the overview slide and for any step in the
    manual that reads better without callouts."""
    for source in sorted(IMAGES.glob("raw-*.png")):
        target = IMAGES / source.name.replace("raw-", "plain-", 1)
        trimmed(source).save(target)
    print("  wrote %d plain panels" % len(list(IMAGES.glob("plain-*.png"))))


def main():
    if not IMAGES.exists():
        raise SystemExit("no docs/images -- run docs/capture.py first")
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if not only:
        write_plain()
    for name, (caption, markers) in CALLOUTS.items():
        if only and only != name:
            continue
        annotate(name, caption, markers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
