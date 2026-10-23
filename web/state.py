"""Application state shared by every route: game data, the session store, the
live-update hub, and the small JSON libraries (party, cast)."""

import json
import os
import uuid

from core import battle_cards, rules as rules_module
from core.names import find_data_file, parse_names_file
from core.npc import Generator
from web import battle_state, combat_state, table
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
        self.table_scale = 1.0               # the GM's text-size nudge for the Table (readability over a stream)
        self.battle_cards = battle_cards.load(self.data_dir, root)

    @property
    def combat_data(self):
        return self.rules.combat

    def card_faces(self, name):
        """The printed faces and Glory rewards of one Opportunity card."""
        return battle_cards.faces(self.battle_cards, name, self.combat_data.get("encounters", {}).get(name),
                                  self.combat_data.get("adversaries", {}))

    def gm_battle(self):
        """The battle as the GM console reads it."""
        return battle_state.gm_view(self.battle_state(), self.party.items, self.combat_data.get("encounters", {}),
                                    self.card_faces)

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

    def battle_state(self):
        return battle_state.reduce(live_events(self.session.events))

    def end_session(self):
        """End the active session — pausing a running battle first, so it
        can be resumed in a later session (``battle.paused``)."""
        b = self.battle_state()
        if not self.session.scratch and battle_state.is_live(b):
            m = b["morale"]
            self.record("battle.paused", f"Battle paused: {b['definition'].get('name', 'Battle')}",
                        title="Battle paused", visibility="gm",
                        data={"summary": {"name": b["definition"].get("name", "Battle"), "day": b["day"],
                                          "turn": b["turn"], "morale": [m["current"], m["start"]] if m else None},
                              "battle": {"id": b["id"], "day": b["day"], "turn": b["turn"], "step": None}})
        return self.sessions.end()

    def table_payload(self):
        cs = combat_state.serialise(self.combat_state(), "table")
        b = battle_state.table_view(self.battle_state(), self.party.items, self.combat_data.get("encounters", {}),
                                    self.card_faces)
        return table.build(self.session, cs, self.table_mode, battle=b, scale=self.table_scale,
                           card_for=lambda name: battle_state.table_card(self.battle_state(), name, self.combat_data.get("encounters", {}),
                                                                         self.card_faces))
