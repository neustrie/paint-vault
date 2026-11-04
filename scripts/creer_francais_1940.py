#!/usr/bin/env python3
"""Crée la fiche projet « Français 1940 » directement dans la base SQLite de Paint Vault.
Usage (sur spirou, depuis le dossier du dépôt) :
    python3 scripts/creer_francais_1940.py ./data/paintvault.db
Idempotent : ne fait rien si le projet existe déjà. Les peintures introuvables dans
l'inventaire sont listées en fin d'exécution (à acheter / à ajouter)."""
import sqlite3, sys
from datetime import datetime

DB = sys.argv[1] if len(sys.argv) > 1 else "./data/paintvault.db"

# (section, technique de section, note, [(code Vallejo ou nom, technique, détail)])
PLAN = [
 ("Uniforme (capote/vareuse kaki)", "Base", "Drap kaki-moutarde modèle 1938/40", [
   ("70.988", "Base", "Khaki - base uniforme"),
   ("70.914", "Éclaircissement", "Green Ochre - éclaircissement"),
   ("70.843", "Ombrage", "Cork Brown - ombres"),
   ("Brown Tone", "Lavis", "(optionnel) lavis de profondeur")]),
 ("Casque Adrian", "Base", "Casque modèle 26 : bleu horizon ou kaki selon l'unité", [
   ("70.888", "Base", "Olive Grey - casque kaki/gris-vert"),
   ("Blue Tone", "Lavis", "Lavis bleuté pour effet bleu horizon"),
   ("70.867", "Éclaircissement", "Basalt Grey - éclaircissement")]),
 ("Cuir et équipement", "Base", "Cartouchières, ceinturon, bretelles, musette", [
   ("70.984", "Base", "Flat Brown - cuir"),
   ("70.846", "Ombrage", "Mahogany Brown - cuir sombre"),
   ("70.917", "Base", "Beige - musette/toile"),
   ("70.837", "Éclaircissement", "Pale Sand - toile claire")]),
 ("Armes (Lebel/MAS 36, FM 24/29)", "Base", "", [
   ("70.846", "Base", "Mahogany Brown - bois"),
   ("70.995", "Base", "German Grey - métal"),
   ("70.980", "Brossage à sec", "Black Green - bords métal")]),
 ("Peau", "Base", "", [
   ("70.815", "Base", "Basic Skintone"),
   ("70.928", "Éclaircissement", "Light Flesh"),
   ("70.927", "Ombrage", "Dark Flesh")]),
 ("Guêtres / bandes molletières", "Base", "", [
   ("70.889", "Base", "Olive Brown"),
   ("70.984", "Ombrage", "Flat Brown")]),
 ("Blindés (Renault R35, Somua S35, Char B1)", "Base", "Livrée kaki + camouflage 1940 (à valider selon véhicule)", [
   ("70.887", "Base", "US Olive Drab - base kaki"),
   ("70.857", "Base", "Golden Olive - camouflage clair"),
   ("70.984", "Base", "Flat Brown - camouflage brun"),
   ("Tamiya TS-28", "Base", "Olive Drab 2 spray - sous-couche")]),
 ("Socles", "Base", "", [
   ("70.916", "Base", "Sand Yellow - terre/sable"),
   ("70.837", "Brossage à sec", "Pale Sand")]),
]

c = sqlite3.connect(DB, timeout=10)
c.execute("PRAGMA foreign_keys=ON")
if c.execute("SELECT 1 FROM projects WHERE name='Français 1940'").fetchone():
    sys.exit("Le projet « Français 1940 » existe déjà : rien fait.")

def find(key):
    r = c.execute("SELECT id FROM paints WHERE code=? ORDER BY id LIMIT 1", (key,)).fetchone()
    if not r:
        r = c.execute("SELECT id FROM paints WHERE name LIKE ? OR (brand||' '||code) LIKE ? ORDER BY id LIMIT 1",
                      (f"%{key}%", f"%{key}%")).fetchone()
    return r[0] if r else None

cur = c.execute("INSERT INTO projects(name,game,scale,faction,notes) VALUES(?,?,?,?,?)",
    ("Français 1940", "Bolt Action / Chain of Command (à préciser)", "28 mm", "Armée française, campagne de mai-juin 1940",
     "Fiche générée depuis l'inventaire. Teinte bleu horizon non couverte par l'inventaire : voir peintures manquantes."))
pid = cur.lastrowid
manquantes = []
for pos, (nom, tech, note, paints) in enumerate(PLAN, 1):
    sid = c.execute("INSERT INTO sections(project_id,name,technique,note,pos) VALUES(?,?,?,?,?)", (pid, nom, tech, note, pos)).lastrowid
    for key, t, detail in paints:
        pa = find(key)
        if pa is None:
            manquantes.append((nom, key, detail)); continue
        c.execute("INSERT INTO section_paints(section_id,paint_id,detail,technique) VALUES(?,?,?,?)", (sid, pa, detail[:80], t))
c.commit()
print(f"Projet créé (id={pid}).")
if manquantes:
    print("Peintures introuvables dans l'inventaire (non ajoutées) :")
    for m in manquantes: print("  -", *m, sep=" | ")
