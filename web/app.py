"""FastAPI application: the GM console (/), the Table screen (/table), and the
JSON API both of them drive. Launch with ./launch.sh (or ``python -m web``)."""

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.routes import cast, combat, library, npc, party, rolls, rules, session
from web.state import AppState

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def create_app(root=ROOT, sessions_dir=None, data_dir=None):
    # Env overrides let a throwaway instance run against copies of the data.
    sessions_dir = sessions_dir or os.environ.get("PENDRAGON_SESSIONS_DIR")
    data_dir = data_dir or os.environ.get("PENDRAGON_DATA_DIR")
    app = FastAPI(title="Pendragon GM", docs_url="/api/docs", redoc_url=None)
    app.state.pd = AppState(root, sessions_dir=sessions_dir, data_dir=data_dir)
    templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))
    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")

    for module in (session, rolls, npc, cast, party, combat, library, rules):
        app.include_router(module.router)

    @app.get("/", response_class=HTMLResponse)
    def gm(request: Request):
        return templates.TemplateResponse(request, "gm.html", {})

    @app.get("/table", response_class=HTMLResponse)
    def table_screen(request: Request):
        return templates.TemplateResponse(request, "table.html", {})

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
