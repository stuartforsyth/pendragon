"""The players' board tells a roll from damage, and makes criticals stand out."""

from playwright.sync_api import expect


def test_roll_damage_and_critical_look_different(page, table, app_url):
    r = page.request
    r.post(app_url + "/api/combat/start", data={"encounter": "Knights of Gorre"})
    r.post(app_url + "/api/combat/distribute")
    cs = r.get(app_url + "/api/combat").json()["combat"]
    foe = [c for c in cs["combatants"] if c["side"] != "party"][0]
    knight = next(c for c in cs["combatants"] if c["display_name"] == foe["engaged_with"])
    table.goto(app_url + "/table")
    latest = table.locator(".fray .latest")

    r.post(app_url + "/api/roll/check", data={"label": "Sword", "value": 0})        # never a critical
    expect(latest.locator(".badge.die")).to_be_visible()
    expect(latest.locator(".kw")).to_have_text("Roll")
    expect(latest.locator(".critbanner")).to_have_count(0)

    r.post(app_url + "/api/combat/blow", data={"attacker": foe["id"], "attack": 2, "target": knight["id"]})
    expect(latest.locator(".badge.seal")).to_be_visible()
    expect(latest.locator(".kw")).to_have_text("Damage")
    expect(latest).to_contain_text("Subtract your armour")

    r.post(app_url + "/api/combat/blow", data={"target": foe["id"], "damage": 30, "critical": True,
                                               "attacker_name": knight["display_name"], "weapon": "Sword"})
    expect(latest.locator(".critbanner")).to_have_text("★ Critical hit! ★")
    expect(latest.locator(".kw")).to_have_text("Wound")
    expect(latest).to_contain_text("armour =")

    r.post(app_url + "/api/roll/check", data={"label": "Sword", "value": 40})       # always a critical
    expect(latest.locator(".critbanner")).to_have_text("★ Critical! ★")
    expect(table.locator(".mini.crit").first).to_contain_text("★ Critical")
