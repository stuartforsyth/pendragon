"""Click-through: each foe's weapon in hand, switching, Disarmed, and Attack."""

from playwright.sync_api import expect


def _start(page, app_url, encounter):
    assert page.request.post(app_url + "/api/combat/start", data={"encounter": encounter}).ok
    assert page.request.post(app_url + "/api/combat/distribute").ok      # one foe on each knight
    page.goto(app_url + "/#/combat")


def test_foe_row_weapon_switch_disarm_and_attack(page, app_url):
    _start(page, app_url, "Knights of Gorre")
    row = page.locator(".cbt-foe").first
    name = row.locator(".cbt-foe-name").inner_text()
    row = page.locator(".cbt-foe", has_text=name)
    expect(row.locator(".cbt-weapon")).to_contain_text("Spear or Sword")          # card's first weapon
    # the type header switches every Knight of Gorre at once
    page.locator(".cbt-type .cbt-wpick", has_text="Sword").last.click()
    for w in page.locator(".cbt-foe .cbt-weapon").all():
        expect(w).to_contain_text("Sword 17")
    # disarm one: Brawling = STR 15 ÷ 2 → 8, at least 10 for a knight; damage (15+15)÷6 = 5
    row.locator(".cbt-weapon").click()
    page.locator(".menu").get_by_role("button", name="Disarmed — Brawling 10 · 5").click()
    expect(row.locator(".cbt-weapon")).to_contain_text("Brawling")
    expect(row.locator(".cbt-weapon")).to_contain_text("Disarmed")
    # attack: rolls Brawling against the engaged knight, knight chosen with chips
    row.get_by_role("button", name="Attack").click()
    modal = page.locator(".modal")
    expect(modal.locator(".attack-roll")).to_contain_text("Brawling")
    expect(modal.locator(".chip.on")).to_have_count(1)
    modal.get_by_role("button", name="Fail").click()
    expect(page.locator(".log")).to_contain_text("is disarmed")
    # players see it
    t = page.request.get(app_url + "/api/table").json()
    assert any("Disarmed" in f["chips"] for k in t["knights"] for f in k["lane"]["foes"])
    # pick the sword back up
    row.locator(".cbt-weapon").click()
    page.locator(".menu").get_by_role("button", name="Sword 17 · 5D6").click()
    expect(row.locator(".cbt-weapon")).not_to_contain_text("Disarmed")


def test_adversary_editor_brawling_default_and_override(page, app_url):
    page.goto(app_url + "/#/adversaries")
    page.locator(".adv-list .list-item", has_text="Knights of Gorre").first.click()
    row = page.locator(".brawl-row")
    expect(row).to_contain_text("Default 10 (STR ÷ 2, at least 10 for a knight)")
    expect(row).to_contain_text("Brawling Damage 5")
    row.locator("input").fill("12")
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(300)
    adv = page.request.get(app_url + "/api/adversaries/Knights of Gorre").json()["adversary"]
    assert adv["brawling"] == 12
