"""Browser click-through tests: a real server on copies of the shipped data,
driven through the GM console and the Table like a person would.

Needs ``playwright`` (requirements-dev.txt) and its Chromium
(``python -m playwright install chromium``); skipped otherwise.
"""

import json
import shutil
import socket
import threading
import time

import pytest

from tests.conftest import ROOT

pw = pytest.importorskip("playwright.sync_api")

KNIGHTS = [{"id": "k1", "name": "Sir Bors", "player": "Ann", "active": True},
           {"id": "k2", "name": "Sir Cai", "player": "Ben", "active": True},
           {"id": "k3", "name": "Dame Lynet", "player": "Cat", "active": True}]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def app_url(tmp_path):
    import uvicorn
    from web.app import create_app
    data = tmp_path / "data"
    data.mkdir()
    for f in ("rules.json", "examplecombat.json"):
        shutil.copy(f"{ROOT}/data/{f}", data / f)
    (data / "party.json").write_text(json.dumps(KNIGHTS))
    app = create_app(ROOT, sessions_dir=str(tmp_path / "sessions"), data_dir=str(data))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture(scope="session")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binaries not installed
            pytest.skip(f"Chromium for Playwright isn't installed: {exc}")
        yield b
        b.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        item.failed_call = rep.failed


@pytest.fixture
def page(browser, request, tmp_path_factory, app_url):   # app_url first, so the server outlives the page
    """A GM console page; any uncaught page error fails the test. On a failure
    a full-page screenshot is kept (path printed) to show what the GM saw."""
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.set_default_timeout(5000)
    yield pg
    if getattr(request.node, "failed_call", False):
        path = tmp_path_factory.mktemp("shots") / f"{request.node.name}.png"
        pg.screenshot(path=str(path), full_page=True)
        print(f"\nscreenshot: {path}")
    pg.close()
    assert not errors, f"page errors: {errors}"


@pytest.fixture
def table(browser, app_url):
    pg = browser.new_page(viewport={"width": 1280, "height": 720})
    pg.set_default_timeout(5000)
    yield pg
    pg.close()
