"""The spotlight: a card the GM puts over the Table so everyone reads it together."""

import json

from tests.conftest import ok
from tests.test_web_battle import _running, _step, _tb


def _on_table(client):
    return _tb(client)["spotlight"]


def test_spotlight_puts_the_green_box_on_the_table_and_nothing_else(client):
    _running(client)
    assert _on_table(client) is None
    ok(client.post("/api/spotlight", json={"kind": "card", "name": "Pictish Knifemen"}))
    sp = _on_table(client)
    assert sp["kind"] == "card" and sp["card"]["name"] == "Pictish Knifemen"
    assert sp["card"]["flavour"].startswith("Rushing forward at a half-crouch") and sp["card"]["minimum"] == 5
    assert set(sp["card"]) == {"name", "flavour", "minimum", "opportunity"}
    raw = json.dumps(_tb(client))
    for secret in ("Hit Points", "three Pictish Knifemen for every", "Brawling"):
        assert secret not in raw, secret
    assert ok(client.get("/api/spotlight"))["spotlight"] == {"kind": "card", "name": "Pictish Knifemen"}


def test_spotlight_is_gold_for_an_opportunity(client):
    _running(client)
    ok(client.post("/api/spotlight", json={"kind": "card", "name": "Clash of Champions"}))
    assert _on_table(client)["card"]["opportunity"] is True


def test_spotlight_ends_when_removed_cleared_or_the_battle_moves_on(client):
    _running(client)
    ok(client.post("/api/spotlight", json={"kind": "card", "name": "Pictish Knifemen"}))
    ok(client.post("/api/spotlight/off"))
    assert _on_table(client) is None
    assert client.post("/api/spotlight/off").status_code == 409            # nothing left to remove
    ok(client.post("/api/spotlight", json={"kind": "card", "name": "Pictish Knifemen"}))
    ok(client.post("/api/table/clear"))
    assert _on_table(client) is None
    ok(client.post("/api/spotlight", json={"kind": "card", "name": "Pictish Knifemen"}))
    _step(client, "set", encounter="Pictish Knifemen")                       # the choice has moved on
    assert _on_table(client) is None and ok(client.get("/api/spotlight"))["spotlight"] is None


def test_spotlight_rejects_unknown_things_and_stays_out_of_the_fray(client):
    _running(client)
    assert client.post("/api/spotlight", json={"kind": "card", "name": "No Such Card"}).status_code == 404
    assert client.post("/api/spotlight", json={"kind": "knight", "name": "x"}).status_code == 400
    ok(client.post("/api/spotlight", json={"kind": "card", "name": "Pictish Knifemen"}))
    assert not [c for c in _tb(client)["feed"] if c["type"].startswith("table.")]


def test_table_text_scale_is_set_by_the_gm(client):
    assert _tb(client)["scale"] == 1.0
    ok(client.post("/api/table/scale", json={"scale": 1.3}))
    assert _tb(client)["scale"] == 1.3
    assert client.post("/api/table/scale", json={"scale": 2}).status_code == 400
