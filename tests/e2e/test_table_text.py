"""The Table is shared over Discord, which compresses video: nothing the players read may be small.
This measures the rendered text of the busiest screens at design size (1rem = 16px on a 1920x1080 window, the
screen scales as one unit) and fails on anything under 16px."""

import pytest
from playwright.sync_api import expect

FLOOR = 16

# every element with visible text of its own, as design px (the root scale divided out)
OFFENDERS = """(floor) => {
  const root = parseFloat(getComputedStyle(document.documentElement).fontSize) / 16, out = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || (!el.offsetParent && cs.position !== 'fixed')) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).map((n) => n.textContent.trim()).join(' ');
    if (!own) continue;
    const px = parseFloat(cs.fontSize) / root;
    if (px < floor) out.push(`${px.toFixed(1)}px  .${el.className || el.tagName}  “${own.slice(0, 30)}”`);
  }
  return out;
}"""


def _post(page, app_url, path, **body):
    return page.request.post(app_url + path, data=body)


def _battle(page, app_url):
    r = page.request
    r.post(app_url + "/api/battle/start", data={"quick": {"size": "clash", "days": 1}})
    r.post(app_url + "/api/battle/day", data={"intensity": 12})
    r.post(app_url + "/api/battle/muster", data={"start": 21, "commander": "k1", "knights": ["k1", "k2", "k3"]})
    return lambda step, **kw: r.post(app_url + "/api/battle/step", data={"step": step, **kw})


def _check(table, where):
    table.wait_for_timeout(1200)
    bad = table.evaluate(OFFENDERS, FLOOR)
    assert not bad, f"{where}: text under {FLOOR}px:\n  " + "\n  ".join(bad[:15])


@pytest.mark.parametrize("size", [(1920, 1080), (1280, 720)])
def test_no_table_text_is_small(page, browser, app_url, size):
    """Mustering, choosing a fate, a fight with nine foes, an Opportunity — and the same at 720p."""
    table = browser.new_page(viewport={"width": size[0], "height": size[1]})
    try:
        step = _battle(page, app_url)
        table.goto(app_url + "/table")
        expect(table.locator(".bv-title")).to_be_visible()
        _check(table, "mustering")
        step("set", encounter="Pictish Knifemen")
        step("intensity", outcome="failure")
        step("pick", knight="k2", encounter="Pictish Javeliniers")
        expect(table.locator(".deck .pcard").first).to_be_visible()
        _check(table, "choose your fate")
        step("select", encounter="Pictish Knifemen", via="commander")
        step("morale", kind="loss", amount=1)
        for k in ("k1", "k2", "k3"):
            step("posture", knight=k, posture="valorous")
        page.request.post(app_url + "/api/battle/fight")
        page.request.post(app_url + "/api/combat/distribute")
        page.request.post(app_url + "/api/roll/check", data={"label": "Dagger", "value": 15})
        expect(table.locator(".tfield .ftok.is-foe").first).to_be_visible()
        _check(table, "a fight with nine foes")
    finally:
        table.close()


def test_opportunity_screen_text_is_not_small(page, browser, app_url):
    table = browser.new_page(viewport={"width": 1920, "height": 1080})
    try:
        step = _battle(page, app_url)
        table.goto(app_url + "/table")
        step("set", encounter="Pictish Knifemen")
        step("intensity", outcome="fumble")
        step("select", encounter="Clash of Champions", via="fumble")
        step("morale", kind="loss", amount=0)
        expect(table.locator(".cf-bandcard")).to_be_visible()
        _check(table, "an Opportunity")
    finally:
        table.close()
