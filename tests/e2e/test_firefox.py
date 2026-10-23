"""Bugs only Firefox shows."""

from playwright.sync_api import expect

# Count every ResizeObserver callback so a feedback loop shows up as a number — and stop calling them
# after 300, so a loop that comes back fails this test instead of eating the machine's memory.
COUNT_RO = """
window.__ro = 0;
const Orig = window.ResizeObserver;
window.ResizeObserver = class extends Orig { constructor(cb) { super((e, o) => { if (++window.__ro > 300) return; return cb(e, o); }); } };
"""


def test_leaving_the_combat_tool_does_not_start_a_redraw_loop(firefox, app_url):
    """The combat tool's Field redrew itself whenever its width changed — and a Field in a tool the GM
    had left (hidden, 0 wide) redrew another hidden Field, for ever: the tab grew by gigabytes
    and took the machine down (24 GB, 23 Oct). Ending a fight in a battle leaves the tool at once."""
    pg = firefox.new_page(viewport={"width": 1440, "height": 900})
    try:
        pg.add_init_script(COUNT_RO)
        pg.request.post(app_url + "/api/combat/start", data={"encounter": "Pictish Knifemen"})
        pg.goto(app_url + "/#/combat")
        expect(pg.locator(".cbt-field")).to_be_visible()
        pg.wait_for_timeout(500)
        before = pg.evaluate("window.__ro")
        pg.evaluate("location.hash = '#/party'")             # leave the tool: it is hidden, the Field measures 0
        pg.wait_for_timeout(2500)
        assert pg.evaluate("window.__ro") - before < 40, "a ResizeObserver feedback loop is running"
    finally:
        pg.close()
