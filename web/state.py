"""Application state shared by every route: game data, the session store, the
live-update hub, and the small JSON libraries (party, cast)."""

import json
import os
import uuid

from core import rules as rules_module
from core.names import find_data_file, parse_names_file
from core.npc import Generator
from web import combat_state, table
from web.hub import Hub
from web.rules_index import RulesIndex
from web.sessions import SessionStore, live_events


class JsonListStore:
    """A list of dicts with string ``id`` keys, persisted to one JSON file."""

    def __init__(self, path):
        self.path = path
        self.items = []
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                self.items = json.load(fh)

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.items, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, item_id):
        return next((x for x in self.items if x.get("id") == item_id), None)

    def add(self, item):
        item = dict(item)
        item.setdefault("id", uuid.uuid4().hex[:10])
        self.items.append(item)
        self.save()
        return item

    def update(self, item_id, fields):
        item = self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        item.update({k: v for k, v in fields.items() if k != "id"})
        self.save()
        return item

    def remove(self, item_id):
        item = self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        self.items.remove(item)
        self.save()
        return item


class AppState:
    def __init__(self, root, sessions_dir=None, data_dir=None):
        self.root = root
        self.data_dir = data_dir or os.path.join(root, "data")
        self.rules = rules_module.load_rules(self.data_dir)
        if self.rules is None:
            raise RuntimeError(f"rules.json not found in {self.data_dir}")
        if not getattr(self.rules, "combat", None):
            self.rules.combat = {"adversaries": {}, "encounters": {}}
            rules_module._unify_combat(self.rules.combat)
        names_path = find_data_file(root)
        cultures = parse_names_file(names_path) if names_path else {}
        self.generator = Generator(cultures, self.rules)
        self.sessions = SessionStore(sessions_dir or os.path.join(root, "sessions"))
        self.party = JsonListStore(os.path.join(self.data_dir, "party.json"))
        self.cast = JsonListStore(os.path.join(self.data_dir, "cast.json"))
        self.rules_index = RulesIndex(os.path.join(root, "rules_corpus", "index.jsonl"))
        self.hub = Hub()
        self.table_mode = "auto"

    @property
    def combat_data(self):
        return self.rules.combat

    def save_combat_data(self):
        return rules_module.save_combat(self.rules.combat, self.data_dir)

    # -- the event log -------------------------------------------------------

    @property
    def session(self):
        return self.sessions.active

    def record(self, etype, text, **kw):
        """Append an event to the active session and notify every client."""
        ev = self.session.append(etype, text, **kw)
        self.notify("event", seq=ev["id"], type=etype)
        return ev

    def notify(self, reason, **extra):
        self.hub.publish({"reason": reason, "session": self.session.id, **extra})

    def combat_state(self):
        return combat_state.reduce(live_events(self.session.events),
                                   self.rules.combat.get("promotion", {}))

    def table_payload(self):
        cs = combat_state.serialise(self.combat_state(), "table")
        return table.build(self.session, cs, self.table_mode)
