"""A long session log keeps only the newest entries on the page."""

from playwright.sync_api import expect


def test_log_is_capped_with_show_earlier(page, app_url):
    assert page.request.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"}).ok
    for i in range(340):
        assert page.request.post(app_url + "/api/combat/note", data={"text": f"note {i}"}).ok
    page.goto(app_url + "/#/combat")
    expect(page.locator("#logList .log-earlier")).to_be_visible()
    assert page.locator("#logList .entry").count() <= 300
    page.request.post(app_url + "/api/combat/note", data={"text": "newest"})
    expect(page.locator("#logList .entry").last).to_contain_text("newest")
    page.locator("#logList .log-earlier").click()
    expect(page.locator("#logList .entry", has_text="note 0").first).to_be_visible()
