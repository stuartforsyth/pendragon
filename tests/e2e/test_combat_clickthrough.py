"""Click-through: the combat tracker's lanes."""

from playwright.sync_api import expect


def test_distribute_foes_equally(page, app_url):
    # 3 knights against Pictish Knifemen; one foe already down to Sir Bors
    r = page.request.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"})
    assert r.ok
    cs = page.request.get(app_url + "/api/combat").json()["combat"]
    foes = [c for c in cs["combatants"] if c["side"] != "party"]
    fallen = foes[0]["id"]
    page.request.post(app_url + f"/api/combat/{fallen}/engage", data={"with": "Sir Bors"})
    page.request.post(app_url + f"/api/combat/{fallen}/status", data={"out": "unconscious"})

    page.goto(app_url + "/#/combat")
    expect(page.locator(".cbt-pool")).to_be_visible()
    page.get_by_role("button", name="Distribute foes equally").click()
    expect(page.locator(".cbt-pool")).to_have_count(0)
    up = len(foes) - 1
    lanes = page.locator(".cbt-lanes .cbt-lane")
    expect(lanes).to_have_count(3)
    counts = [lanes.nth(i).locator(".cbt-foe").count() for i in range(3)]
    assert sum(counts) == up and max(counts) - min(counts) <= 1, counts
    # the fallen foe stays credited to Sir Bors
    after = page.request.get(app_url + "/api/combat").json()["combat"]
    assert next(c for c in after["combatants"] if c["id"] == fallen)["engaged_with"] == "Sir Bors"
    expect(page.locator(".log")).to_contain_text("The foes spread out")
