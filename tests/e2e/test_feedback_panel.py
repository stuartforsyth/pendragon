"""Click-through: the Feedback tab slides out a panel; a report is queued with
where it came from and shows under 'Your recent reports'."""

from playwright.sync_api import expect


def test_feedback_tab_send_and_list(page, app_url):
    page.goto(app_url + "/#/combat")
    expect(page.locator("#fb-panel")).not_to_have_class("open")
    page.locator("#fb-tab").click()
    panel = page.locator("#fb-panel.open")
    expect(panel).to_be_visible()
    expect(panel.locator(".fb-captured")).to_contain_text("Combat")
    panel.get_by_role("radio", name="Change").click()
    panel.locator("textarea").fill("Make the tokens bigger")
    panel.get_by_role("button", name="Send").click()
    expect(panel.locator(".fb-status")).to_contain_text("queued as #1")
    expect(panel.locator(".fb-list")).to_contain_text("Make the tokens bigger")
    item = page.request.get(app_url + "/api/feedback").json()["items"][0]
    assert item["kind"] == "change" and item["page"]["route"] == "#/combat" and item["page"]["tool"] == "Combat"
    page.keyboard.press("Escape")
    expect(page.locator("#fb-panel.open")).to_have_count(0)
