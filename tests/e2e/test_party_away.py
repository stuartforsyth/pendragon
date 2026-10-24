"""The GM marks a knight away for the session on the Party tab; encounters rescale and the row greys out."""

from playwright.sync_api import expect


def test_gm_marks_a_knight_away_tonight(page, app_url):
    for name in ("Sir Kay", "Sir Bors"):
        page.request.post(app_url + "/api/party", data={"name": name})
    page.goto(app_url + "/#/party")
    row = page.locator(".party-row", has_text="Sir Kay")
    row.get_by_role("button", name="Away tonight").click()
    expect(page.locator(".party-row.away", has_text="Sir Kay")).to_be_visible()
    expect(page.locator("main, #view").first).to_contain_text("1 away tonight")
    page.locator(".party-row.away").get_by_role("button", name="Back").click()
    expect(page.locator(".party-row.away")).to_have_count(0)


def test_combat_launcher_counts_only_present_knights(page, app_url):
    for name in ("Sir Gawain", "Sir Ywain", "Sir Ector"):
        page.request.post(app_url + "/api/party", data={"name": name})
    kay = [m for m in page.request.get(app_url + "/api/party").json()["party"] if m["name"] == "Sir Gawain"][0]
    page.request.post(app_url + f"/api/party/{kay['id']}/away", data={"away": True})
    page.goto(app_url + "/#/combat")
    party = page.request.get(app_url + "/api/party").json()["party"]
    present = len([m for m in party if m["active"] and not m["away"]])
    assert present == len(party) - 1
    expect(page.locator("body")).to_contain_text(f"{present} active knights in the Party")
