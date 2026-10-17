# Archive

Old code kept for reference. It's not part of the current app.

- `legacy-tk/` holds the original Tkinter desktop app (`pendragon.py`, with tabs in `encounter.py`, `adversary.py` and `encounter_creator.py`) and its `run.sh` / `run.bat`. It was replaced by the web app (`./launch.sh`). It still imports the shared `core/` and reads `data/` from the repository root, so `archive/legacy-tk/run.sh` should still start it. It is no longer maintained or tested.
