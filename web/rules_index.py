"""Search over the rules index (``rules_corpus/index.jsonl``).

``rules_corpus`` is a read-only symlink to the ttrpg-parser project's Pendragon
corpus, which owns and builds the index; this module only reads it. That
corpus is written for Obsidian, so on load ``![[table]]`` embeds are replaced
by the table's text and ``[[wikilinks]]`` by their label. Search is a small weighted keyword match — titles and
tags count far more than body text — which is plenty for ~100 entries.
"""

import json
import os
import re

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark").enable("table")
_WORD = re.compile(r"[a-z0-9]+")
_WIKI = re.compile(r"(!?)\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def render_markdown(text):
    return _md.render(text or "")


class RulesIndex:
    def __init__(self, path):
        self.entries = []
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                self.entries = [json.loads(line) for line in fh if line.strip()]
        self._by_id = {e["id"]: e for e in self.entries}
        self._resolve_wikilinks()

    def _resolve_wikilinks(self):
        # Wikilink targets are file stems, ids, or "stem#heading".
        targets = dict(self._by_id)
        for e in self.entries:
            stem = e.get("source", "").rsplit("/", 1)[-1]
            if stem.endswith(".md"):
                targets[stem[:-3]] = e

        def sub(m):
            embed, target, label = m.groups()
            e = targets.get(target.split("#")[0].strip())
            if embed:
                return e["text"] if e else ""
            return label or (e["title"] if e else target.split("#")[0])

        for e in self.entries:
            if "[[" in e["text"]:
                e["text"] = _WIKI.sub(sub, e["text"])

    def _summary(self, e, snippet=""):
        return {"id": e["id"], "title": e["title"], "book": e["book"],
                "chapter": e.get("chapter", ""), "pages": e.get("pages", []),
                "tags": e.get("tags", []), "snippet": snippet}

    def search(self, query, limit=25):
        words = _WORD.findall((query or "").lower())
        if not words:
            return [self._summary(e) for e in self.entries[:limit]]
        scored = []
        for e in self.entries:
            title = e["title"].lower()
            tags = " ".join(e.get("tags", [])).lower()
            body = e["text"].lower()
            score = 0
            for w in words:
                score += 10 * title.count(w) + 6 * tags.count(w) + min(body.count(w), 8)
            if all(w in title + " " + tags + " " + body for w in words) and score:
                scored.append((score, e))
        scored.sort(key=lambda se: -se[0])
        out = []
        for _score, e in scored[:limit]:
            body = e["text"]
            i = body.lower().find(words[0])
            snippet = body[max(0, i - 60): i + 140].replace("\n", " ") if i >= 0 else ""
            out.append(self._summary(e, snippet.strip()))
        return out

    def get(self, rule_id):
        e = self._by_id.get(rule_id)
        if e is None:
            return None
        return {**self._summary(e), "text": e["text"], "html": render_markdown(e["text"])}
