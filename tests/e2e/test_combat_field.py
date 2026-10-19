"""Click-through: the combat tracker's Field — tokens, red engagement lines,
drag either way to engage, Waiting to free a foe, click for controls."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.field


def _cs(page, app_url):
    return page.request.get(app_url + "/api/combat").json()["combat"]


def _start(page, app_url):
    assert page.request.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"}).ok
    page.goto(app_url + "/#/combat")
    expect(page.locator(".cbt-field")).to_be_visible()


def test_field_drag_both_ways_and_waiting(page, app_url):
    _start(page, app_url)
    foes = [c for c in _cs(page, app_url)["combatants"] if c["side"] != "party"]
    expect(page.locator(".cbt-field .ftok.is-knight")).to_have_count(3)
    expect(page.locator(".cbt-wait .ftok")).to_have_count(len(foes))      # everyone waits at first
    # a foe dragged onto a knight
    page.locator(f'.ftok[data-id="{foes[0]["id"]}"]').drag_to(page.locator(".ftok.is-knight", has_text="Sir Bors"))
    expect(page.locator(".cbt-link")).to_have_count(1)
    page.wait_for_timeout(300)
    # a knight dragged onto a waiting foe
    page.locator(".ftok.is-knight", has_text="Sir Cai").drag_to(page.locator(f'.ftok[data-id="{foes[1]["id"]}"]'))
    expect(page.locator(".cbt-link")).to_have_count(2)
    page.wait_for_timeout(300)
    # a foe dropped on an engaged foe joins its knight
    page.locator(f'.ftok[data-id="{foes[2]["id"]}"]').drag_to(page.locator(f'.cbt-field .ftok[data-id="{foes[0]["id"]}"]'))
    expect(page.locator(".cbt-link")).to_have_count(3)
    cs = {c["id"]: c for c in _cs(page, app_url)["combatants"]}
    assert cs[foes[0]["id"]]["engaged_with"] == "Sir Bors" and cs[foes[2]["id"]]["engaged_with"] == "Sir Bors"
    assert cs[foes[1]["id"]]["engaged_with"] == "Sir Cai"
    # back to Waiting
    page.locator(f'.cbt-field .ftok[data-id="{foes[0]["id"]}"]').drag_to(page.locator(".cbt-wait"))
    expect(page.locator(".cbt-link")).to_have_count(2)
    assert {c["id"]: c for c in _cs(page, app_url)["combatants"]}[foes[0]["id"]]["engaged_with"] == ""


def test_field_click_token_opens_controls(page, app_url):
    _start(page, app_url)
    page.request.post(app_url + "/api/combat/distribute")
    tok = page.locator(".cbt-field .ftok.is-foe").first
    tok.click()
    drawer = page.locator(".cbt-drawer")
    expect(drawer.get_by_role("button", name="Attack")).to_be_visible()
    expect(drawer.get_by_role("button", name="Hit")).to_be_visible()
    drawer.get_by_title("Close").click()
    expect(drawer).to_have_count(0)
    page.locator(".cbt-field .ftok.is-knight").first.click()
    expect(page.locator(".cbt-drawer .cbt-knight")).to_be_visible()
    # the List view is one click away
    page.locator(".seg").get_by_role("button", name="List").click()
    expect(page.locator(".cbt-lanes")).to_be_visible()


def test_three_knights_on_one_foe(page, app_url):
    _start(page, app_url)
    foe = [c for c in _cs(page, app_url)["combatants"] if c["side"] != "party"][0]
    target = lambda: page.locator(f'.ftok[data-id="{foe["id"]}"]')
    for n, name in enumerate(("Sir Bors", "Sir Cai", "Dame Lynet"), 1):
        page.locator(".ftok.is-knight", has_text=name).drag_to(target())
        expect(page.locator(".cbt-link")).to_have_count(n)          # wait for the redraw before the next drag
    target().click()
    expect(page.locator(".cbt-drawer .out-tag")).to_have_text("−10 outnumbered")
    page.locator(".cbt-drawer").get_by_title("Close").click()
    expect(page.locator(".cbt-drawer")).to_have_count(0)
    page.wait_for_timeout(300)                                      # the Field re-lays itself out once the drawer is gone
    # a knight dragged onto open ground breaks off
    field = page.locator(".cbt-field").bounding_box()
    page.locator(".ftok.is-knight", has_text="Sir Bors").drag_to(page.locator(".cbt-field"), target_position={"x": 8, "y": field["height"] - 8})
    expect(page.locator(".cbt-link")).to_have_count(2)
    row = {c["id"]: c for c in _cs(page, app_url)["combatants"]}[foe["id"]]
    assert row["linked"] == ["Sir Cai", "Dame Lynet"] and row["outnumbered"] == -5
