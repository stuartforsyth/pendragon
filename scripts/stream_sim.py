"""Render the Table the way a compressed Discord share shows it: each state at 960x540 (half of 1080p,
the screen scales as one unit) saved as a low-quality JPEG, so you can look at the images and see whether
every word the players need is still legible. A running server on copies of your data is needed:

    PENDRAGON_DATA_DIR=... PENDRAGON_SESSIONS_DIR=... .venv/bin/python -m web --port 8021 &
    .venv/bin/python scripts/stream_sim.py http://127.0.0.1:8021 OUT_DIR [scenario ...]

Scenarios: mustering, choose, fight, opportunity, spotlight (default: all of them, in order, on one battle).
It needs a party of at least three knights in the data copy (the shipped Bedegraine party works)."""

import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1], sys.argv[2]
WANT = sys.argv[3:] or ["mustering", "choose", "fight", "opportunity", "spotlight"]


def call(path, body=None, method="POST"):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def shot(pg, name, quality=35):
    pg.wait_for_timeout(1500)
    pg.screenshot(path=f"{OUT}/{name}.jpg", type="jpeg", quality=quality)
    print("wrote", f"{OUT}/{name}.jpg")


def main():
    knights = [k["id"] for k in call("/api/party", method="GET")["party"]][:3]
    call("/api/session/start", {"title": "Stream check"})
    call("/api/battle/start", {"key": "The Battle of Bedegraine"})
    st = lambda s, **k: call("/api/battle/step", {"step": s, **k})
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": 960, "height": 540})
        pg.goto(BASE + "/table")
        if "mustering" in WANT:
            shot(pg, "1_mustering")
        call("/api/battle/day", {"intensity": 14})
        call("/api/battle/muster", {"start": 22, "commander": knights[0], "knights": knights})
        if "opportunity" in WANT:                      # a fumble, the commander's Opportunity, Morale paid: the card fills the board
            st("set", encounter="Pictish Knifemen"); st("intensity", outcome="fumble")
            st("select", encounter="Clash of Champions", via="fumble"); st("morale", kind="loss", amount=0)
            shot(pg, "4_opportunity")
            br.close()
            return
        if "choose" in WANT:
            st("set", encounter="Pictish Knifemen"); st("intensity", outcome="failure")
            st("pick", knight=knights[1], encounter="Pictish Pikemen")
            shot(pg, "2_choose_fate")
            st("select", encounter="Pictish Pikemen", via="commander")
        else:
            st("set", encounter="Pictish Knifemen"); st("intensity", outcome="success")
        st("morale", kind="loss", amount=3)
        for k in knights:
            st("posture", knight=k, posture="valorous")
        if "fight" in WANT:
            call("/api/battle/fight"); call("/api/combat/distribute")
            cs = call("/api/combat", method="GET")["combat"]
            foe = [c for c in cs["combatants"] if c["side"] != "party"][0]
            call(f"/api/combat/{foe['id']}/acted", {"on": True})
            call("/api/roll/check", {"label": "Dagger", "value": 15})
            shot(pg, "3_fight")
            call("/api/combat/end")
        if "spotlight" in WANT:
            call("/api/spotlight", {"kind": "card", "name": "Pictish Knifemen"})
            shot(pg, "5_spotlight")
            call("/api/spotlight/off")
        br.close()


main()
