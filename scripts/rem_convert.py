"""One-off: convert the Table's pixel sizes to rem (px / 16) so the whole screen scales as one unit with the
window (table.js sets the root font-size from the window against a 1920x1080 design). Hairlines of 2px or
less stay px, and media-query conditions are left alone. Run on web/static/css/table.css and board.css."""

import re
import sys

PX = re.compile(r"(?<![\w.#-])(-?\d*\.?\d+)px\b")


def rem(match):
    v = float(match.group(1))
    if abs(v) <= 2:
        return match.group(0)
    return f"{round(v / 16, 4):g}rem"


def convert(text):
    out = []
    for line in text.splitlines():
        # keep a media query's own condition in px, convert what is inside its block
        m = re.match(r"(\s*@media[^{]*\{)(.*)$", line)
        out.append(m.group(1) + PX.sub(rem, m.group(2)) if m else PX.sub(rem, line))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    for path in sys.argv[1:]:
        src = open(path, encoding="utf-8").read()
        open(path, "w", encoding="utf-8").write(convert(src))
        print("converted", path)
