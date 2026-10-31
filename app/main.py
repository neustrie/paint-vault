import asyncio, csv, io, os, re, sqlite3, uuid, shutil
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import RedirectResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
from urllib.parse import quote

BASE = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", "/data"))
PHOTOS = DATA / "photos"
EXPORTS = DATA / "exports"
DB = DATA / "paintvault.db"

STATUTS = {"en_stock": "En stock", "vide": "Pot vide", "a_commander": "À commander", "commande": "Commandé"}
TECHNIQUES = ["Base", "Lavis", "Ombrage", "Brossage à sec", "Éclaircissement", "Glacis", "Autre"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS paints(
  id INTEGER PRIMARY KEY, brand TEXT NOT NULL, range TEXT DEFAULT '', code TEXT DEFAULT '',
  av_ref TEXT DEFAULT '', name TEXT NOT NULL, type TEXT DEFAULT 'Peinture acrylique',
  status TEXT NOT NULL DEFAULT 'en_stock', usage TEXT DEFAULT '', updated TEXT, hex TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, game TEXT DEFAULT '', scale TEXT DEFAULT '',
  faction TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS sections(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL, technique TEXT DEFAULT 'Base', note TEXT DEFAULT '', pos INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS section_paints(
  id INTEGER PRIMARY KEY, section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  paint_id INTEGER NOT NULL REFERENCES paints(id), parts INTEGER, technique TEXT DEFAULT 'Base');
CREATE TABLE IF NOT EXISTS photos(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT NOT NULL);
"""

def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init():
    DATA.mkdir(parents=True, exist_ok=True); PHOTOS.mkdir(exist_ok=True); EXPORTS.mkdir(exist_ok=True)
    with closing(db()) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        if "technique" not in [r[1] for r in c.execute("PRAGMA table_info(section_paints)")]:
            c.execute("ALTER TABLE section_paints ADD COLUMN technique TEXT DEFAULT 'Base'")
            c.execute("UPDATE section_paints SET technique=(SELECT technique FROM sections WHERE sections.id=section_paints.section_id)")
        if "hex" not in [r[1] for r in c.execute("PRAGMA table_info(paints)")]:
            c.execute("ALTER TABLE paints ADD COLUMN hex TEXT DEFAULT ''")
        if c.execute("SELECT COUNT(*) FROM paints").fetchone()[0] == 0:
            seed = json.loads((BASE / "seed.json").read_text(encoding="utf-8"))
            now = datetime.now().isoformat(timespec="seconds")
            c.executemany(
                "INSERT INTO paints(brand,range,code,av_ref,name,type,status,usage,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                [(p["brand"], p["range"], p["code"], p.get("av_ref", ""), p["name"], p["type"], p["status"], p.get("usage", ""), now) for p in seed])
        # couleurs approximatives (seed) : ne remplit que les peintures sans couleur
        seed = json.loads((BASE / "seed.json").read_text(encoding="utf-8"))
        for p in seed:
            if p.get("hex"):
                c.execute("UPDATE paints SET hex=? WHERE (hex IS NULL OR hex='') AND brand=? AND code=? AND name=?", (p["hex"], p["brand"], p["code"], p["name"]))
        c.commit()

def export_csv_text():
    with closing(db()) as c:
        rows = c.execute("SELECT brand,range,code,av_ref,name,type,hex,status,usage FROM paints ORDER BY brand,range,code,name").fetchall()
    buf = io.StringIO(); w = csv.writer(buf, delimiter=";")
    w.writerow(["Marque", "Gamme", "Code", "Réf. AV", "Nom", "Type", "Couleur", "Statut", "Usage"])
    for r in rows: w.writerow([*list(r)[:7], STATUTS.get(r["status"], r["status"]), r["usage"]])
    return buf.getvalue()

def write_export():
    (EXPORTS / "inventaire.csv").write_text(export_csv_text(), encoding="utf-8-sig")

async def daily_export():
    while True:
        try: write_export()
        except Exception as e: print("export error", e)
        await asyncio.sleep(86400)

@asynccontextmanager
async def lifespan(app):
    init()
    t = asyncio.create_task(daily_export())
    yield
    t.cancel()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals.update(STATUTS=STATUTS, TECHNIQUES=TECHNIQUES)
PHOTOS_MOUNT_DIR = os.environ.get("DATA_DIR", "/data") + "/photos"
os.makedirs(PHOTOS_MOUNT_DIR, exist_ok=True)
app.mount("/photos", StaticFiles(directory=PHOTOS_MOUNT_DIR), name="photos")

def back(url): return RedirectResponse(url, status_code=303)

# ---------- Inventaire ----------
@app.get("/")
def inventory(request: Request, q: str = "", brand: str = "", type: str = "", status: str = ""):
    sql, args = "SELECT * FROM paints WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR code LIKE ? OR av_ref LIKE ? OR usage LIKE ?)"; args += [f"%{q}%"] * 4
    if brand: sql += " AND brand=?"; args.append(brand)
    if type: sql += " AND type=?"; args.append(type)
    if status: sql += " AND status=?"; args.append(status)
    sql += " ORDER BY brand, range, code, name"
    with closing(db()) as c:
        paints = c.execute(sql, args).fetchall()
        brands = [r[0] for r in c.execute("SELECT DISTINCT brand FROM paints ORDER BY 1")]
        types = [r[0] for r in c.execute("SELECT DISTINCT type FROM paints ORDER BY 1")]
        counts = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM paints GROUP BY status")}
    return templates.TemplateResponse(request, "inventory.html", dict(
        paints=paints, brands=brands, types=types, counts=counts, q=q, brand=brand, type=type, status=status, page="inv"))

@app.post("/paints")
def add_paint(brand: str = Form(...), range: str = Form(""), code: str = Form(""), av_ref: str = Form(""),
              name: str = Form(...), type: str = Form("Peinture acrylique"), usage: str = Form(""), hex: str = Form("")):
    with closing(db()) as c:
        c.execute("INSERT INTO paints(brand,range,code,av_ref,name,type,usage,hex,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                  (brand.strip(), range.strip(), code.strip(), av_ref.strip(), name.strip(), type.strip(), usage.strip(), hex if re.fullmatch(r"#[0-9a-fA-F]{6}", hex or "") else "", datetime.now().isoformat(timespec="seconds")))
        c.commit()
    return back("/")

@app.post("/paints/{pid}/status")
def set_status(pid: int, status: str = Form(...), next: str = Form("/")):
    if status in STATUTS:
        with closing(db()) as c:
            c.execute("UPDATE paints SET status=?, updated=? WHERE id=?", (status, datetime.now().isoformat(timespec="seconds"), pid)); c.commit()
    return back(next if next.startswith("/") else "/")

@app.get("/paints/{pid}")
def edit_paint_form(request: Request, pid: int):
    with closing(db()) as c:
        p = c.execute("SELECT * FROM paints WHERE id=?", (pid,)).fetchone()
        used = c.execute("""SELECT pr.id, pr.name FROM section_paints sp JOIN sections s ON s.id=sp.section_id
                            JOIN projects pr ON pr.id=s.project_id WHERE sp.paint_id=? GROUP BY pr.id""", (pid,)).fetchall()
    if not p: return back("/")
    return templates.TemplateResponse(request, "paint_edit.html", dict(p=p, used=used, page="inv"))

@app.post("/paints/{pid}/edit")
def edit_paint(pid: int, brand: str = Form(...), range: str = Form(""), code: str = Form(""), av_ref: str = Form(""),
               name: str = Form(...), type: str = Form(""), status: str = Form("en_stock"), usage: str = Form(""), hex: str = Form("")):
    with closing(db()) as c:
        c.execute("UPDATE paints SET brand=?,range=?,code=?,av_ref=?,name=?,type=?,status=?,usage=?,hex=?,updated=? WHERE id=?",
                  (brand, range, code, av_ref, name, type, status if status in STATUTS else "en_stock", usage, hex if re.fullmatch(r"#[0-9a-fA-F]{6}", hex or "") else "", datetime.now().isoformat(timespec="seconds"), pid))
        c.commit()
    return back("/")

@app.post("/paints/{pid}/delete")
def delete_paint(pid: int):
    with closing(db()) as c:
        if c.execute("SELECT COUNT(*) FROM section_paints WHERE paint_id=?", (pid,)).fetchone()[0] == 0:
            c.execute("DELETE FROM paints WHERE id=?", (pid,)); c.commit()
    return back("/")

@app.get("/courses")
def shopping(request: Request):
    with closing(db()) as c:
        paints = c.execute("SELECT * FROM paints WHERE status IN ('vide','a_commander','commande') ORDER BY status, brand, code").fetchall()
    return templates.TemplateResponse(request, "courses.html", dict(paints=paints, page="courses"))

@app.get("/export.csv")
def export_csv():
    return Response(("﻿" + export_csv_text()), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="inventaire_peintures.csv"'})

# ---------- Projets ----------
@app.get("/projets")
def projects(request: Request):
    with closing(db()) as c:
        projs = c.execute("""SELECT p.*, (SELECT filename FROM photos WHERE project_id=p.id ORDER BY id LIMIT 1) AS cover,
                             (SELECT COUNT(*) FROM sections WHERE project_id=p.id) AS nsec FROM projects p ORDER BY p.id DESC""").fetchall()
    return templates.TemplateResponse(request, "projects.html", dict(projs=projs, page="proj"))

@app.post("/projets")
def create_project(name: str = Form(...), game: str = Form(""), scale: str = Form(""), faction: str = Form(""), notes: str = Form("")):
    with closing(db()) as c:
        cur = c.execute("INSERT INTO projects(name,game,scale,faction,notes) VALUES(?,?,?,?,?)", (name, game, scale, faction, notes)); c.commit()
        return back(f"/projets/{cur.lastrowid}")

def load_project(c, pid):
    p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p: return None, [], []
    secs = []
    for s in c.execute("SELECT * FROM sections WHERE project_id=? ORDER BY pos, id", (pid,)):
        sp = c.execute("""SELECT sp.id, sp.parts, sp.technique, pa.id AS paint_id, pa.hex, pa.brand, pa.code, pa.name, pa.status FROM section_paints sp
                          JOIN paints pa ON pa.id=sp.paint_id WHERE sp.section_id=? ORDER BY sp.id""", (s["id"],)).fetchall()
        secs.append(dict(s=s, paints=sp))
    photos = c.execute("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    return p, secs, photos

@app.get("/projets/{pid}")
def project(request: Request, pid: int):
    with closing(db()) as c:
        p, secs, photos = load_project(c, pid)
        allp = c.execute("SELECT id, brand, code, name FROM paints ORDER BY code, name").fetchall()
    if not p: return back("/projets")
    labels = list(dict.fromkeys(paint_label(a) for a in allp))
    return templates.TemplateResponse(request, "project.html", dict(p=p, secs=secs, photos=photos, labels=labels, err=request.query_params.get("err", ""), page="proj"))

@app.post("/projets/{pid}/edit")
def edit_project(pid: int, name: str = Form(...), game: str = Form(""), scale: str = Form(""), faction: str = Form(""), notes: str = Form("")):
    with closing(db()) as c:
        c.execute("UPDATE projects SET name=?,game=?,scale=?,faction=?,notes=? WHERE id=?", (name, game, scale, faction, notes, pid)); c.commit()
    return back(f"/projets/{pid}")

@app.post("/projets/{pid}/delete")
def delete_project(pid: int):
    with closing(db()) as c:
        files = [r[0] for r in c.execute("SELECT filename FROM photos WHERE project_id=?", (pid,))]
        c.execute("DELETE FROM projects WHERE id=?", (pid,)); c.commit()
    for f in files: (PHOTOS / f).unlink(missing_ok=True)
    return back("/projets")

@app.post("/projets/{pid}/sections")
def add_section(pid: int, name: str = Form(...), technique: str = Form("Base"), note: str = Form("")):
    with closing(db()) as c:
        pos = c.execute("SELECT COALESCE(MAX(pos),0)+1 FROM sections WHERE project_id=?", (pid,)).fetchone()[0]
        c.execute("INSERT INTO sections(project_id,name,technique,note,pos) VALUES(?,?,?,?,?)", (pid, name, technique, note, pos)); c.commit()
    return back(f"/projets/{pid}")

@app.post("/sections/{sid}/delete")
def delete_section(sid: int):
    with closing(db()) as c:
        r = c.execute("SELECT project_id FROM sections WHERE id=?", (sid,)).fetchone()
        c.execute("DELETE FROM sections WHERE id=?", (sid,)); c.commit()
    return back(f"/projets/{r[0]}" if r else "/projets")

def paint_label(p):
    return f"{p['code']} — {p['name']} ({p['brand']})" if p["code"] else f"{p['name']} ({p['brand']})"

@app.post("/sections/{sid}/paints")
def add_section_paint(sid: int, q: str = Form(""), parts: str = Form(""), technique: str = Form("Base")):
    q = q.strip()
    with closing(db()) as c:
        r = c.execute("SELECT project_id FROM sections WHERE id=?", (sid,)).fetchone()
        if not r: return back("/projets")
        paints = c.execute("SELECT id, brand, code, name FROM paints").fetchall()
        exact = [p for p in paints if paint_label(p).lower() == q.lower()]
        found = exact or [p for p in paints if q and q.lower() in paint_label(p).lower()]
        ids = {p["id"] for p in found} if len({paint_label(p) for p in found}) > 1 else set(p["id"] for p in found[:1])
        if len(ids) != 1:
            msg = "Aucune peinture ne correspond à" if not found else "Plusieurs peintures correspondent à"
            return back(f"/projets/{r[0]}?err=" + quote(f"{msg} « {q} » : choisis une proposition de la liste."))
        c.execute("INSERT INTO section_paints(section_id,paint_id,parts,technique) VALUES(?,?,?,?)", (sid, ids.pop(), int(parts) if parts.strip().isdigit() else None, technique if technique in TECHNIQUES else "Autre")); c.commit()
    return back(f"/projets/{r[0]}")

@app.post("/section_paints/{spid}/delete")
def delete_section_paint(spid: int):
    with closing(db()) as c:
        r = c.execute("SELECT s.project_id FROM section_paints sp JOIN sections s ON s.id=sp.section_id WHERE sp.id=?", (spid,)).fetchone()
        c.execute("DELETE FROM section_paints WHERE id=?", (spid,)); c.commit()
    return back(f"/projets/{r[0]}" if r else "/projets")

@app.post("/projets/{pid}/photos")
async def add_photo(pid: int, files: list[UploadFile] = File(...)):
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"): continue
        name = f"{pid}_{uuid.uuid4().hex[:10]}{ext}"
        with open(PHOTOS / name, "wb") as out: shutil.copyfileobj(f.file, out)
        with closing(db()) as c:
            c.execute("INSERT INTO photos(project_id,filename) VALUES(?,?)", (pid, name)); c.commit()
    return back(f"/projets/{pid}")

@app.post("/photos/{phid}/delete")
def delete_photo(phid: int):
    with closing(db()) as c:
        r = c.execute("SELECT project_id, filename FROM photos WHERE id=?", (phid,)).fetchone()
        c.execute("DELETE FROM photos WHERE id=?", (phid,)); c.commit()
    if r: (PHOTOS / r["filename"]).unlink(missing_ok=True); return back(f"/projets/{r['project_id']}")
    return back("/projets")

@app.get("/projets/{pid}/pdf")
def project_pdf(pid: int):
    from pdf import render_project_pdf
    with closing(db()) as c:
        p, secs, photos = load_project(c, pid)
    if not p: return back("/projets")
    data = render_project_pdf(p, secs, STATUTS)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="fiche_projet_{pid}.pdf"'})
