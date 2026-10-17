"""Setting up a battle from a GM library that predates the battle cards: the
app must say what's missing and add it in one click, then show the cards."""

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import old_library


@pytest.fixture
def library():
    return old_library()


def test_missing_battle_cards_banner_adds_them_and_deck_shows_cards(page, app_url):
    page.goto(app_url + "/#/battles")
    banner = page.locator(".examples-banner")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("Opportunities")
    banner.get_by_role("button", name="Add them").click()
    expect(banner).to_be_hidden()
    # the example battles arrived, and a new battle's deck shows every card
    expect(page.locator(".bt-item", has_text="The Battle of Bedegraine")).to_be_visible()
    page.get_by_role("button", name="New").click()
    expect(page.locator(".bt-head")).to_contain_text("Not yet saved")
    deck = page.locator(".day-card").first.locator(".deck-picker")
    expect(deck).to_be_visible()                                   # unfolded by default
    expect(deck.locator(".dp-row", has_text="Knights of Gorre")).to_be_visible()
    deck.get_by_role("tab", name="Opportunities").click()
    for name in ("Clash of Champions", "Rally the Division!", "Rescue Captive Knights"):
        expect(deck.locator(".dp-row", has_text=name)).to_be_visible()


def test_battle_tool_banner_on_launch_panel(page, app_url):
    page.goto(app_url + "/#/battle")
    expect(page.locator(".examples-banner")).to_be_visible()
