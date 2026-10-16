"""NPC Generator: generate, reroll a field, present to the Table, export."""

import os
import random
import tempfile
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import Response

from core import pdf_export
from core.adversary import draft_from_npc
from core.npc import (build_description, build_image_prompt, format_statblock,
                      format_statblock_markdown, subtitle_str)
from web.routes.common import bad, st

router = APIRouter()

CULTURE_ORDER = ["Cymri", "Pict", "Saxon", "Irish", "Roman", "Frankish", "Aquitanian"]


def decorate(npc):
    """Add the derived presentation fields every view uses."""
    npc.setdefault("uid", uuid.uuid4().hex[:10])
    npc["subtitle"] = subtitle_str(npc)
    npc["description"] = build_description(npc)
    return npc


def formats(npc):
    return {"statblock": format_statblock(npc),
            "markdown": format_statblock_markdown(npc),
            "image_prompt": build_image_prompt(npc)}


def _public(npc):
    """The NPC as stored in an event: everything except private GM notes."""
    return {k: v for k, v in npc.items() if k != "notes"}


@router.get("/api/npc/options")
def options(request: Request):
    g = st(request).generator
    names = g.culture_names()
    cultures = [c for c in CULTURE_ORDER if c in names] + [c for c in names if c not in CULTURE_ORDER]
    rules = g.rules
    return {"cultures": cultures, "classes": rules.class_names(),
            "religions": list(rules.religions), "reroll_fields": g.reroll_fields(),
            "pdf_available": pdf_export.PDF_AVAILABLE and os.path.isfile(
                pdf_export.sheet_template_path(st(request).root))}


@router.post("/api/npc/generate")
async def generate(request: Request, body: dict):
    state = st(request)
    g = state.generator
    culture = body.get("culture") or "Random"
    if culture == "Random":
        culture = random.choice(g.culture_names())
    if culture not in g.cultures:
        bad(f"Unknown culture {culture}")
    gender = body.get("gender") or "Random"
    if gender == "Random":
        gender = random.choice(("Male", "Female"))
    social_class = body.get("social_class") or "Random"
    if social_class == "Random" and body.get("randomise_class"):
        social_class = g.rules.roll_class(gender)
    religion = body.get("religion") or "Random"
    try:
        npc = g.generate(culture, gender, social_class,
                         None if religion == "Random" else religion,
                         include_negative_appearance=bool(body.get("include_negative", True)))
    except ValueError as exc:
        bad(str(exc))
    decorate(npc)
    ev = state.record("npc.generated", f"NPC: {npc['full']} — {npc['subtitle']}",
                      title=npc["full"], data={"npc": _public(npc)})
    return {"npc": npc, "formats": formats(npc), "event": ev}


@router.post("/api/npc/reroll")
async def reroll(request: Request, body: dict):
    state = st(request)
    npc, field = body.get("npc"), body.get("field")
    if not npc or field not in state.generator.reroll_fields():
        bad("Send an npc and a valid field")
    try:
        state.generator.reroll_field(npc, field)
    except ValueError as exc:
        bad(str(exc))
    decorate(npc)
    ev = state.record("npc.updated", f"Rerolled {field} — {npc['full']}",
                      title=npc["full"], data={"npc": _public(npc), "field": field})
    return {"npc": npc, "formats": formats(npc), "event": ev}


@router.post("/api/npc/present")
async def present(request: Request, body: dict):
    npc = body.get("npc")
    if not npc:
        bad("No NPC to present")
    decorate(npc)
    ev = st(request).record("npc.presented", f"Presented to the table: {npc['full']}",
                            title=npc["full"], data={"npc": _public(npc)})
    return {"event": ev}


@router.post("/api/npc/formats")
def npc_formats(body: dict):
    npc = body.get("npc")
    if not npc:
        bad("No NPC")
    return formats(decorate(npc))


@router.post("/api/npc/adversary-draft")
def adversary_draft(request: Request, body: dict):
    npc = body.get("npc")
    if not npc:
        bad("No NPC")
    return {"draft": draft_from_npc(npc, st(request).combat_data)}


@router.post("/api/npc/pdf")
def npc_pdf(request: Request, body: dict):
    npc = body.get("npc") or {}
    if not npc.get("full_knight"):
        bad("Only a full Cymric knight has a character sheet")
    if not pdf_export.PDF_AVAILABLE:
        bad("PDF export needs the pypdf package")
    template = pdf_export.sheet_template_path(st(request).root)
    if not os.path.isfile(template):
        bad(f"Sheet template missing: {template}", 404)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "sheet.pdf")
        pdf_export.export_sheet(npc, template, out)
        with open(out, "rb") as fh:
            data = fh.read()
    name = pdf_export.safe_filename(npc.get("full"))
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
