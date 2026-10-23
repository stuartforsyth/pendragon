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


def test_foe_that_has_acted_wears_a_green_tick_on_the_table(page, table, app_url):
    r = page.request
    r.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"})
    r.post(app_url + "/api/combat/distribute")
    foes = [c for c in r.get(app_url + "/api/combat").json()["combat"]["combatants"] if c["side"] != "party"]
    table.goto(app_url + "/table")
    expect(table.locator(".tfield .ftok.is-foe").first).to_be_visible()
    expect(table.locator(".tfield .ftok-acted")).to_have_count(0)
    r.post(app_url + f"/api/combat/{foes[0]['id']}/acted", data={"on": True})
    expect(table.locator(f'.tfield .ftok[data-id="{foes[0]["id"]}"] .ftok-acted')).to_have_text("✓")
    expect(table.locator(".tfield .ftok-acted")).to_have_count(1)
    r.post(app_url + "/api/combat/round")                                   # a new round clears every tick
    expect(table.locator(".tfield .ftok-acted")).to_have_count(0)


def test_knight_cards_are_ranked_by_glory_and_the_leader_is_crowned(page, table, app_url):
    r = page.request
    r.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"})
    table.goto(app_url + "/table")
    cards = table.locator(".fv-knights .kcard")
    expect(cards).to_have_count(3)
    expect(table.locator(".kcard.leader")).to_have_count(0)                  # nobody has Glory yet: table order, no crown
    first_before = cards.first.locator(".kc-name").inner_text()
    r.post(app_url + "/api/glory", data={"knight": "k3", "amount": 40, "reason": "A deed"})
    expect(cards.first.locator(".kc-name")).to_have_text("Dame Lynet", ignore_case=True)
    expect(cards.first).to_have_class(__import__("re").compile(r"leader"))
    expect(cards.first.locator(".gl-laurel")).to_have_count(1)
    expect(table.locator(".kcard.leader")).to_have_count(1)
    assert first_before.lower() != "dame lynet"
    r.post(app_url + "/api/glory", data={"knight": "k1", "amount": 40, "reason": "A deed"})      # a tie shares the crown
    expect(table.locator(".kcard.leader")).to_have_count(2)
    r.post(app_url + "/api/glory", data={"knight": "k2", "amount": 70, "reason": "A deed"})
    expect(cards.first.locator(".kc-name")).to_have_text("Sir Cai", ignore_case=True)
    expect(table.locator(".kcard.leader")).to_have_count(1)


def test_a_new_fight_does_not_pin_the_last_fights_roll(page, table, app_url):
    """The Fray's big roll card is the newest roll of THIS fight. An earlier fight's killing blow stayed pinned
    there after the next fight began, as if it had just been rolled (23 Oct)."""
    r = page.request
    r.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"})
    r.post(app_url + "/api/combat/distribute")
    cs = r.get(app_url + "/api/combat").json()["combat"]
    foe = [c for c in cs["combatants"] if c["side"] != "party"][0]
    knight = next(c for c in cs["combatants"] if c["display_name"] == foe["engaged_with"])
    table.goto(app_url + "/table")
    r.post(app_url + "/api/combat/blow", data={"target": foe["id"], "damage": 30, "critical": True,
                                               "attacker_name": knight["display_name"], "weapon": "Sword"})
    expect(table.locator(".fray .latest")).to_have_count(1)
    r.post(app_url + "/api/combat/end")
    r.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"})
    r.post(app_url + "/api/combat/distribute")
    expect(table.locator(".tfield .ftok.is-foe").first).to_be_visible()
    expect(table.locator(".fray .latest")).to_have_count(0)                 # nothing rolled in this fight yet
    r.post(app_url + "/api/roll/check", data={"label": "Sword", "value": 0})
    expect(table.locator(".fray .latest")).to_have_count(1)                 # and a roll in this fight shows


def test_a_long_deck_of_cards_scrolls_on_the_table(page, table, app_url):
    """At 'Choose your fate' the whole library is laid out — more cards than fit. The GM can scroll the Table's
    centre to the rest, and an update doesn't throw them back to the top."""
    r = page.request
    r.post(app_url + "/api/battle/start", data={"quick": {"size": "clash", "days": 1}})
    r.post(app_url + "/api/battle/day", data={"intensity": 12})
    r.post(app_url + "/api/battle/muster", data={"start": 21, "commander": "k1", "knights": ["k1", "k2", "k3"]})
    r.post(app_url + "/api/battle/step", data={"step": "set", "encounter": "Pictish Knifemen"})
    r.post(app_url + "/api/battle/step", data={"step": "intensity", "outcome": "failure"})
    table.goto(app_url + "/table")
    centre = table.locator(".bv-centre")
    expect(table.locator(".bv-centre .pcard").first).to_be_visible()
    assert table.evaluate("() => { const c = document.querySelector('.bv-centre'); return c.scrollHeight > c.clientHeight + 40; }"), "the deck should overflow the Table"
    assert table.evaluate("() => getComputedStyle(document.querySelector('.bv-centre')).overflowY") == "auto"
    table.evaluate("() => { document.querySelector('.bv-centre').scrollTop = 200; }")
    r.post(app_url + "/api/narrate", data={"text": "An update arrives"})                  # the Table redraws
    expect(table.locator(".fray")).to_contain_text("An update arrives")
    assert table.evaluate("() => document.querySelector('.bv-centre').scrollTop") > 150
    last = table.locator(".bv-centre .pcard").last
    last.scroll_into_view_if_needed()
    expect(last).to_be_in_viewport()
