"""Click through every part of a battle in the real GM console (and check the
Table), the way the GM does it at the table — no API shortcuts in the steps
under test. If a button path breaks, these fail."""

import re

from playwright.sync_api import expect

KNIGHT_NAMES = ["Sir Bors", "Sir Cai", "Dame Lynet"]


# ---------------------------------------------------------------- helpers

def current(page):
    """The open stepper step, e.g. "Set Encounter"."""
    step = page.locator(".step.cur").first
    expect(step).to_be_visible()
    return step.locator(".nm").inner_text().strip()


def expect_step(page, name):
    expect(page.locator(".step.cur .nm").first).to_have_text(name, ignore_case=True)


def quick_launch(page, url, size="Clash"):
    page.goto(url + "/#/battle")
    page.locator(".bl-sizes .chip", has_text=size).first.click()
    page.get_by_role("button", name="Launch battle").click()
    expect(page.get_by_text("The conroi", exact=True)).to_be_visible()


def muster(page, morale="21", commander="Sir Bors", roll_intensity=True):
    page.locator(".chips .chip", has_text=commander).first.click()
    page.locator("input.big-num").fill(morale)
    page.locator("input.big-num").press("Tab")
    day_roll = page.get_by_role("button", name=re.compile(r"^Roll for me \("))     # today's Intensity
    if roll_intensity and day_roll.count():
        day_roll.click()
    begin = page.get_by_role("button", name="Begin Turn 1 ▸")
    expect(begin).to_be_enabled()
    begin.click()
    expect_step(page, "Set Encounter")


def set_encounter(page, name):
    page.locator(".step.cur .ct", has=page.locator(".cf-title", has_text=name)).first.click()


def intensity(page, outcome="Success"):
    expect_step(page, "Charge · Intensity")
    half = page.locator(".step.cur .half", has_text="Intensity roll")
    half.get_by_role("button", name=outcome).click()


def morale_loss(page, amount="2"):
    expect_step(page, "Morale")
    box = page.locator(".step.cur .amount-entry input")
    if box.count():
        box.fill(amount)
        box.press("Enter")
    else:
        page.get_by_role("button", name="No Morale Loss").click()


def postures(page, letters=("V", "V", "V")):
    expect_step(page, "Postures")
    rows = page.locator(".step.cur .posture-row")
    for i, letter in enumerate(letters):
        row = rows.nth(i)
        row.locator(".chip", has_text=f"{letter} ·").click()
        if letter in ("R", "P"):
            row.locator("input[type=number]").fill("1")
    page.get_by_role("button", name="Confirm postures").click()


def confirm(page, label):
    page.locator(".modal").get_by_role("button", name=label).click()


# ---------------------------------------------------------------- tests

def test_quick_battle_full_turn_with_a_fight(page, table, app_url):
    quick_launch(page, app_url)
    muster(page)
    # an empty deck means every battle Foe: the cards are there to click
    expect(page.locator(".step.cur .ct")).not_to_have_count(0)
    set_encounter(page, "Pictish Knifemen")
    intensity(page, "Success")
    table.goto(app_url + "/table")
    expect(table.locator(".resbanner")).to_have_text("The Encounter stands", ignore_case=True)
    morale_loss(page, "2")
    postures(page)
    page.get_by_role("button", name="Begin the fight").click()
    # the combat tracker opens, linked to the battle
    expect(page.locator(".cbt-lane")).to_have_count(3)
    expect(page.get_by_role("button", name="◂ Back to battle")).to_be_visible()
    lane = page.locator(".cbt-lane").first
    expect(lane).to_contain_text("Valorous · round 1 of 2")
    page.get_by_role("button", name="End fight").click()
    confirm(page, "End fight")
    expect_step(page, "End turn")
    page.get_by_role("button", name="End turn").click()
    expect(page.locator(".bhead")).to_contain_text("Turn 2 of 5")
    expect_step(page, "Set Encounter")


def test_turn_two_charge_then_failed_intensity_picks_and_opportunity(page, app_url):
    quick_launch(page, app_url)
    muster(page)
    # turn 1, quickly
    set_encounter(page, "Pictish Knifemen")
    intensity(page)
    morale_loss(page, "1")
    postures(page)
    page.get_by_role("button", name="End turn").click()
    # turn 2: the charge roll is part of the step now
    set_encounter(page, "Pictish Javeliniers")
    charge = page.locator(".step.cur .half", has_text="Commander's charge roll")
    charge.get_by_role("button", name="Success").click()
    intensity(page, "Fail")
    expect_step(page, "Picks")
    # card-first picks: Sir Bors picks the Knifemen; Sir Cai crits for an Opportunity
    page.locator(".step.cur .gcard", has_text="Pictish Knifemen").click()
    page.locator(".step.cur").get_by_role("button", name="Sir Bors", exact=True).click()
    expect(page.locator(".step.cur .gcard", has_text="Pictish Knifemen").locator(".ptok")).to_have_count(1)
    page.locator(".step.cur .gcard", has_text="Clash of Champions").click()
    page.locator(".step.cur").get_by_role("button", name="Sir Cai · crit").click()
    expect(page.locator(".step.cur .gcard", has_text="Clash of Champions").locator(".ptok.crit")).to_have_count(1)
    page.get_by_role("button", name="Commander chooses ▸").click()
    # an Opportunity was picked, so it is the only candidate and is chosen at once
    expect_step(page, "Morale")
    expect(page.locator(".step.done", has_text="Commander's choice")).to_contain_text("Clash of Champions")


def test_retire_rest_and_return(page, app_url):
    quick_launch(page, app_url)
    muster(page)
    page.get_by_role("button", name="Retire to the Rear instead").click()
    expect_step(page, "Rest at the rear")
    box = page.locator(".step.cur .amount-entry input")
    box.fill("3")
    box.press("Enter")
    page.get_by_role("button", name="End turn").click()
    expect(page.get_by_text("The conroi is at the rear")).to_be_visible()
    page.get_by_role("button", name="Return to the field").click()
    expect_step(page, "Set Encounter")


def test_forced_retire_below_minimum(page, app_url):
    quick_launch(page, app_url)
    muster(page, morale="8")
    set_encounter(page, "Knights of Gorre")             # Minimum 13
    intensity(page)
    expect_step(page, "Morale")
    page.get_by_role("button", name="Not enough Morale — Retire to the Rear").click()
    expect_step(page, "Rest at the rear")


def test_reopen_a_step_and_restore(page, app_url):
    quick_launch(page, app_url)
    muster(page)
    set_encounter(page, "Pictish Knifemen")
    intensity(page)
    expect_step(page, "Morale")
    page.locator(".step.done", has_text="Charge · Intensity").get_by_role("button", name="reopen").click()
    confirm(page, "Undo")
    expect_step(page, "Charge · Intensity")
    page.get_by_role("button", name="Restore").click()
    expect_step(page, "Morale")


def test_build_bedegraine_in_the_editor_and_play_it(page, app_url):
    page.goto(app_url + "/#/battles")
    expect(page.locator(".bt-item").first).to_be_visible()
    page.get_by_role("button", name="New").click()
    expect(page.locator(".bt-head")).to_contain_text("Not yet saved")
    page.wait_for_timeout(300)
    page.get_by_placeholder("e.g. Bedegraine", exact=True).fill("Bedegraine by hand")
    page.locator(".bt-sizes button", has_text="Huge Battle").click()
    page.get_by_placeholder("e.g. Bedegraine forest").fill("Bedegraine, on the River Trent")
    expect(page.get_by_text("Conroi commander")).to_have_count(0)      # chosen at launch, not in the template
    page.get_by_placeholder("e.g. King Arthur").fill("King Arthur")
    page.get_by_placeholder("e.g. King Lot").fill("King Lot")
    day1 = page.locator(".day-card").nth(0)
    day1.get_by_role("button", name="Fixed").click()
    day1.locator("input[type=number]").first.fill("14")
    day1.locator("input[type=number]").nth(1).fill("5")
    expect(day1.locator(".deck-picker")).to_be_visible()             # the deck is unfolded while editing
    for name in ("Pictish Knifemen", "Pictish Javeliniers", "Pictish Pikemen"):
        day1.locator(".dp-row", has_text=name).locator("input").click()
    page.get_by_role("button", name="Add day").click()
    day2 = page.locator(".day-card").nth(1)
    day2.get_by_role("button", name="Fixed").click()
    day2.locator("input[type=number]").first.fill("18")
    expect(day2.get_by_text("Conroi starts on foot")).to_have_count(0)   # set at Mustering, not in the template
    day2.get_by_text("No charge this day").click()
    page.get_by_role("button", name="Save").click()
    expect(page.locator(".bt-item", has_text="Bedegraine by hand")).to_contain_text("Huge Battle · 2 days")
    page.get_by_role("button", name="Launch", exact=True).click()
    # Mustering: the commander is chosen here; Intensity fixed at 14, army commanders named
    expect(page.locator(".bhead")).to_contain_text("Mustering · Day 1 of 2")
    expect(page.locator(".bl .chips .chip.on")).to_have_count(0)
    page.locator(".bl .chips .chip", has_text="Sir Cai").click()
    expect(page.get_by_text("King Arthur (friendly)")).to_be_visible()
    page.locator(".army-row", has_text="King Arthur").get_by_role("button", name="Success").click()
    page.locator(".army-row", has_text="King Lot").get_by_role("button", name="Success").click()
    expect(page.locator(".mstrip")).to_have_count(0)
    page.locator("input.big-num").fill("21")
    page.locator("input.big-num").press("Tab")
    page.get_by_role("button", name="Begin Turn 1 ▸").click()
    expect_step(page, "Set Encounter")
    # only today's deck is offered, and the Force token is there to arm
    expect(page.locator(".step.cur .ct")).to_have_count(3)
    expect(page.get_by_text("⚑ Force this Encounter")).to_be_visible()
    set_encounter(page, "Pictish Knifemen")
    intensity(page)


def test_aftermath_finale_and_end(page, table, app_url):
    quick_launch(page, app_url, "Fight")                      # a Fight lasts one turn
    muster(page)
    set_encounter(page, "Pictish Knifemen")
    intensity(page)
    morale_loss(page, "1")
    postures(page)
    page.get_by_role("button", name="End the last day").click()
    expect(page.get_by_text("Aftermath ·")).to_be_visible()
    expect(page.locator(".panel h3", has_text="Outcome")).to_be_visible()
    page.get_by_role("button", name="Post to Table ▸").click()
    table.goto(app_url + "/table")
    expect(table.locator(".finale")).to_be_visible()
    page.get_by_role("button", name="End battle").click()
    confirm(page, "End battle")
    expect(page.get_by_role("button", name="Launch battle")).to_be_visible()


def test_change_commander_after_typing_morale(page, app_url):
    """Typing the Morale and then clicking a commander must switch the commander."""
    quick_launch(page, app_url)
    page.locator(".chips .chip", has_text="Sir Bors").first.click()
    page.locator("input.big-num").fill("20")
    page.locator(".chips .chip", has_text="Dame Lynet").first.click()
    expect(page.locator(".chips .chip.on", has_text="Dame Lynet")).to_have_count(1)
    page.locator(".chips .chip", has_text="GM (NPC)").click()
    expect(page.locator(".chips .chip.on", has_text="GM (NPC)")).to_have_count(1)
    page.get_by_role("button", name=re.compile(r"^Roll for me \(")).click()
    page.get_by_role("button", name="Begin Turn 1 ▸").click()
    expect(page.locator(".mstrip .who")).to_contain_text("Commander: GM")
    # and once running, the commander can be changed from the Morale strip
    page.locator(".mstrip .who").click()
    page.locator(".menu").get_by_role("button", name="Sir Cai").click()
    expect(page.locator(".mstrip .who")).to_contain_text("Commander: Sir Cai")


def test_battle_settings_edit_everything_mid_turn(page, app_url):
    quick_launch(page, app_url)
    muster(page)
    set_encounter(page, "Pictish Knifemen")
    page.get_by_role("button", name="Battle settings").click()
    modal = page.locator(".modal")
    modal.locator(".field", has_text="Name").locator("input").fill("The Ford at Bedegraine")
    modal.locator(".panel", has_text="The conroi").get_by_text("Dame Lynet").click()        # take her out
    modal.locator(".field", has_text="Passion").locator("input").fill("Loyalty (King)")
    modal.locator(".panel", has_text="Today").locator(".field", has_text="Intensity").locator("input").fill("16")
    modal.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(".bl-title")).to_have_text("The Ford at Bedegraine")
    expect(page.locator(".bhead")).to_contain_text("Intensity 16")
    expect(page.locator(".kchip")).to_have_count(2)
    expect_step(page, "Charge · Intensity")                   # still mid-turn


def test_all_on_foot_at_mustering(page, app_url):
    quick_launch(page, app_url)
    pills = page.locator(".bl .kchk .pill-mounted")
    expect(pills.first).to_have_text("Mounted")
    page.get_by_role("button", name="All on foot").click()
    for p in pills.all():
        expect(p).to_have_text("On foot")
    pills.first.click()                                         # one knight kept his horse
    expect(pills.first).to_have_text("Mounted")
    expect(page.get_by_role("button", name="All on foot")).to_be_visible()


def test_knight_position_menu_and_restore_offer_clears_next_turn(page, app_url):
    """The position chip on a knight's row is a menu (rear / alone / left / back
    with the conroi); the "Undone … Restore" offer belongs to its turn only."""
    quick_launch(page, app_url)
    muster(page)
    chip = page.locator(".kchip", has_text="Sir Cai").locator(".kpos")
    expect(chip).to_contain_text("with the conroi")
    chip.click()
    page.locator(".menu button", has_text="at the rear").click()
    expect(page.locator(".kchip", has_text="Sir Cai").locator(".kpos")).to_contain_text("at the rear")
    # only the two knights still with the conroi take postures
    set_encounter(page, "Pictish Knifemen")
    intensity(page)
    morale_loss(page, "1")
    expect(page.locator(".step.cur .posture-row")).to_have_count(2)
    postures(page, ("V", "V"))
    expect_step(page, "Fight")
    # back with the conroi from the same menu: Postures reopens for him alone
    page.locator(".kchip", has_text="Sir Cai").locator(".kpos").click()
    page.locator(".menu button", has_text="with the conroi").click()
    expect(page.locator(".kchip", has_text="Sir Cai").locator(".kpos")).to_contain_text("with the conroi")
    expect(page.locator(".step.cur .posture-row")).to_have_count(1)
    postures(page, ("V",))
    expect_step(page, "Fight")
    # reopen postures: the Restore offer shows now, and is gone after End turn
    page.locator(".step.done", has_text="Postures").get_by_role("button", name="reopen").click()
    confirm(page, "Undo")
    expect(page.locator(".bl-undone")).to_be_visible()
    postures(page, ("V", "V", "V"))
    page.get_by_role("button", name="End turn").click()
    expect(page.locator(".bhead")).to_contain_text("Turn 2 of 5")
    expect(page.locator(".bl-undone")).to_have_count(0)


def test_launch_from_the_editor_offers_to_close_the_running_battle(page, app_url):
    quick_launch(page, app_url)                      # a Clash sits at Mustering
    page.goto(app_url + "/#/battles")
    page.get_by_role("button", name="New", exact=True).click()
    expect(page.locator(".bt-head")).to_contain_text("Not yet saved")
    page.wait_for_timeout(300)
    page.get_by_placeholder("e.g. Bedegraine", exact=True).fill("Second battle")
    # the editor's Launch saves, then runs into the running battle and offers to close it
    page.get_by_role("button", name="Launch", exact=True).click()
    expect(page.locator(".modal", has_text="Save and launch?")).to_be_visible()
    confirm(page, "Save & launch")
    expect(page.locator(".modal", has_text="A battle is already running")).to_be_visible()
    confirm(page, "Close current battle & launch")
    expect(page.locator(".panel h3", has_text="The conroi")).to_be_visible()
    expect(page.locator(".bhead")).to_contain_text("Mustering")


def test_opportunity_is_played_at_the_table_then_glory_awarded(page, table, app_url):
    quick_launch(page, app_url)
    muster(page)
    table.goto(app_url + "/table")
    set_encounter(page, "Pictish Knifemen")
    intensity(page, "Fumble")
    expect_step(page, "Commander's choice")
    page.locator(".step.cur .gcard", has_text="Clash of Champions").click()
    morale_loss(page, "0")
    # the GM plays it offline: the whole card on the console, only the green title box on the Table
    expect_step(page, "Play the Opportunity")
    expect(page.locator(".step.done", has_text="Postures")).to_have_count(0)
    expect(page.locator(".step.cur .cf-gm .cf.front")).to_have_count(1)
    expect(page.locator(".step.cur .cf-gm .cf.back")).to_contain_text("Champion")
    expect(page.locator(".step.cur .cf-gm")).to_contain_text("conroi commander may choose anyone")
    expect(table.locator(".cf-bandcard")).to_contain_text("Clash of Champions")
    expect(table.locator("body")).not_to_contain_text("conroi commander may choose anyone")
    expect(table.locator("body")).not_to_contain_text("Hit Points")
    # Glory printed on the card: +50 to one knight, then +10 to everyone with the conroi
    page.get_by_role("button", name=re.compile(r"^\+50 Champion defeated")).click()
    page.locator(".opp-glory .chip", has_text="Sir Cai").click()
    page.get_by_role("button", name="Award Glory").click()
    expect(page.locator(".opp-awards")).to_contain_text("+50 Glory · Sir Cai — Champion defeated")
    page.locator(".opp-glory input[type=number]").fill("10")
    page.locator(".opp-glory input:not([type=number])").fill("Taking part")
    page.locator(".opp-glory .chip", has_text="All with the conroi").click()
    page.get_by_role("button", name="Award Glory").click()
    expect(page.locator(".opp-awards li")).to_have_count(4)
    page.get_by_role("button", name="Done — back to the turn's end").click()
    expect_step(page, "End turn")
    page.get_by_role("button", name="End turn").click()
    expect_step(page, "Set Encounter")


def test_encounter_cards_flip_to_their_stat_block(page, app_url):
    quick_launch(page, app_url)
    muster(page)
    tile = page.locator(".step.cur .ct", has=page.locator(".cf-title", has_text="Pictish Knifemen")).first
    expect(tile.locator(".cf.front")).to_contain_text("three Pictish Knifemen for every Player-knight")
    expect(tile.locator(".cf.front .cf-foot")).to_contain_text("Morale Minimum5")
    expect(tile).not_to_have_class(re.compile(r"flipped"))
    tile.locator(".ct-flip").click()                               # the corner toggle: flipping doesn't pick the card
    expect(tile).to_have_class(re.compile(r"flipped"))
    expect(tile.locator(".cf.back")).to_contain_text("Hit Points")
    expect(tile.locator(".cf.back")).to_contain_text("Brawling")
    expect_step(page, "Set Encounter")
    tile.locator(".ct-flip").click()
    expect(tile).not_to_have_class(re.compile(r"flipped"))
    tile.click()
    expect(page.locator(".step.done", has_text="Set Encounter")).to_contain_text("Pictish Knifemen")


def test_duplicate_and_delete_a_paused_battle(page, app_url):
    r = page.request
    r.post(app_url + "/api/session/start", data={"title": "Night one"})
    r.post(app_url + "/api/battle/start", data={"quick": {"size": "clash", "days": 1, "name": "Ford"}})
    r.post(app_url + "/api/battle/day", data={"intensity": 12})
    r.post(app_url + "/api/battle/muster", data={"start": 21, "commander": "k1", "knights": ["k1", "k2", "k3"]})
    r.post(app_url + "/api/session/end")
    r.post(app_url + "/api/session/start", data={"title": "Night two"})
    page.goto(app_url + "/#/battle")
    rows = page.locator(".bl-row")
    expect(rows).to_have_count(1)
    rows.first.get_by_role("button", name="Duplicate").click()                       # a copy to test on
    expect(rows).to_have_count(2)
    copy = page.locator(".bl-row", has_text="Copy of Night one")
    expect(copy).to_have_count(1)
    copy.get_by_role("button", name="Delete").click()                                # …and bin it again
    confirm(page, "Delete it")
    expect(rows).to_have_count(1)
    expect(page.locator(".bl-row", has_text="Night one")).to_have_count(1)           # the original is still there
