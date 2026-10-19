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


def test_rule_on_the_table_is_an_overlay_until_removed(page, table, app_url):
    """Show on Table lays the whole rule over the Table as a parchment; nothing
    lands in the Fray; Remove from Table (in the tool or the top-bar Rules menu)
    takes it off. Pinned rules sit in that menu."""
    import re
    from playwright.sync_api import expect
    table.goto(app_url + "/table")
    page.goto(app_url + "/#/rules")
    page.locator(".rules-q").fill("major wound")
    expect(page.locator(".rule-item").first).to_be_visible()
    page.locator(".rule-item").first.click()
    expect(page.locator(".rule-h")).to_be_visible()
    title = page.locator(".rule-h").inner_text()
    page.get_by_role("button", name="Pin", exact=True).click()
    expect(page.locator(".pin-item")).to_have_count(1)
    page.get_by_role("button", name="Show on Table").first.click()
    expect(table.locator(".rule-overlay .rs-title")).to_have_text(title, ignore_case=True)
    expect(table.locator(".rs-body")).not_to_be_empty()
    assert table.locator(".card.mini", has_text=re.compile(re.escape(title), re.I)).count() == 0          # not in the Fray
    expect(page.locator(".rule-ontable")).to_contain_text(title, ignore_case=True)
    page.get_by_role("button", name="Remove from Table").first.click()
    expect(table.locator(".rule-overlay")).to_have_count(0)
    # from anywhere: the top-bar Rules menu shows a pinned rule, and removes it again
    page.goto(app_url + "/#/combat")
    page.locator("#pinnedRules").click()
    page.locator(".menu button", has_text=re.compile(re.escape(title), re.I)).click()
    expect(table.locator(".rule-overlay .rs-title")).to_have_text(title, ignore_case=True)
    page.locator("#pinnedRules").click()
    page.locator(".menu button", has_text=re.compile("^Remove")).click()
    expect(table.locator(".rule-overlay")).to_have_count(0)
