"""Assemble Nano Banana prompts for a session comic from panel scripts.

The ``/comic`` skill has Opus write the panel scripts (JSON); this file puts
them together with the shared style and character sheet from ``comics/`` into
one copy-paste Markdown file, ``sessions/<session-id>.comic.md``, which the GM
edits and refines. Style and characters are plain files reused every session.

Panel JSON: {"title": str, "strips": [{"panes": [{"label": str, "who": [names],
"scene": str, "caption": str}, x3]}]}

    .venv/bin/python -m core.comic_prompt panes.json sessions/<id>.comic.md
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name):
    return (ROOT / "comics" / name).read_text(encoding="utf-8").strip()


def _looks(characters, who):
    """The character-sheet lines for the knights named in a panel."""
    lines = [ln[2:] for ln in characters.splitlines() if ln.startswith("- ")]
    return [ln for ln in lines if any(ln.startswith(name + ":") for name in who)]


def build(spec):
    style, characters = _read("style.md"), _read("characters.md")
    out = [f"# Comic prompts: {spec['title']}", "",
           "Paste each **Strip prompt** into Nano Banana as one request. If the three-panel layout comes out wrong, use the "
           "three **Single-panel prompts** under it instead, and set the strips together yourself. Captions are separate: "
           "add them in an editor. Edit anything below; to reuse the look in another session, keep `comics/style.md` and "
           "`comics/characters.md`.", "",
           "## Style (from comics/style.md)", "", style, "", "## Characters (from comics/characters.md)", "", characters, ""]
    for n, strip in enumerate(spec["strips"], 1):
        panes = strip["panes"]
        if len(panes) != 3:
            raise ValueError(f"Strip {n} has {len(panes)} panels; each strip needs exactly 3")
        who = list(dict.fromkeys(w for p in panes for w in p.get("who", [])))
        looks = _looks(characters, who)
        out += [f"## Strip {n}", "", "### Strip prompt (one image, three panels)", "", "```",
                style, "",
                "A horizontal comic strip of exactly three equal panels side by side, separated by thin ink gutters. "
                "Same characters and style in every panel."]
        out += ["Characters: " + " ".join(looks)] if looks else []
        out += [f"Panel {i}: {p['scene']}" for i, p in enumerate(panes, 1)]
        out += ["```", "", "### Captions", ""]
        out += [f"{i}. {p['caption']}" for i, p in enumerate(panes, 1)]
        out += ["", "### Single-panel prompts (fallback)", ""]
        for i, p in enumerate(panes, 1):
            lk = _looks(characters, p.get("who", []))
            body = "\n".join([style, "", "A single comic panel."] + (["Characters: " + " ".join(lk)] if lk else []) + [p["scene"]])
            out += [f"**Panel {i}** — {p['label']}", "", "```", body, "```", ""]
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(sys.argv[2]).write_text(build(spec), encoding="utf-8")
    print(sys.argv[2], f"({sum(len(s['panes']) for s in spec['strips'])} panels)")
