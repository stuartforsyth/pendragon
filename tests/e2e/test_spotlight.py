"""The GM clicks a card's 'show on the Table' button and it is blown up over the Table."""

import re

from playwright.sync_api import expect

from tests.e2e.test_battle_clickthrough import muster, quick_launch


def test_gm_spotlights_a_card_and_takes_it_off(page, table, app_url):
    quick_launch(page, app_url)
    muster(page)
    table.goto(app_url + "/table")
    tile = page.locator(".step.cur .ct", has=page.locator(".cf-title", has_text="Pictish Knifemen")).first
    tile.locator(".ct-show").click()                                       # not the card itself: this must not set the Encounter
    overlay = table.locator("#spotOverlay")
    expect(overlay).to_be_visible()
    expect(overlay.locator(".cf-title")).to_have_text("Pictish Knifemen")
    expect(overlay.locator(".cf-flav")).to_contain_text("Rushing forward at a half-crouch")
    expect(overlay).not_to_contain_text("Hit Points")
    assert table.evaluate("() => document.querySelector('#spotOverlay .pcard').getBoundingClientRect().height") > 500, "the card should be big"
    expect(page.locator(".step.cur .nm").first).to_have_text("Set Encounter", ignore_case=True)       # still choosing
    expect(page.locator("#spotChip")).to_contain_text("On the Table: Pictish Knifemen")
    page.locator("#spotChip").click()                                      # take it off from the bar
    expect(overlay).to_have_count(0)
    expect(page.locator("#spotChip")).to_be_hidden()
    # click again on the card button, then choose the card: the choice moves on, so the overlay clears by itself
    tile.locator(".ct-show").click()
    expect(overlay).to_be_visible()
    tile.click()
    expect(overlay).to_have_count(0)


def test_text_size_buttons_scale_the_table(page, table, app_url):
    table.goto(app_url + "/table")
    page.goto(app_url + "/")
    before = table.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)")
    page.locator("#scaleUp").click()
    page.wait_for_timeout(400)
    after = table.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)")
    assert after > before * 1.1, (before, after)
    page.locator("#scaleDown").click()
    page.wait_for_timeout(400)
    assert abs(table.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)") - before) < 0.5
