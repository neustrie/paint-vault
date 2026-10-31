import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

def render_project_pdf(p, secs, statuts):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm,
                            title=f"Fiche projet - {p['name']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=24, leading=28, alignment=0)
    meta = ParagraphStyle("meta", parent=ss["Normal"], fontSize=12, leading=16, textColor=colors.HexColor("#444444"))
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=12, leading=15)
    bold = ParagraphStyle("bold", parent=cell, fontName="Helvetica-Bold")
    E = lambda s: escape(str(s or ""))
    story = [Paragraph(E(p["name"]), h1)]
    line = " · ".join(x for x in [p["game"], p["scale"], p["faction"]] if x)
    if line: story.append(Paragraph(E(line), meta))
    if p["notes"]: story += [Spacer(1, 3*mm), Paragraph(E(p["notes"]).replace("\n", "<br/>"), cell)]
    story.append(Spacer(1, 6*mm))
    rows = [[Paragraph("Élément", bold), Paragraph("Peinture(s) et technique", bold)]]
    for s in secs:
        sec = s["s"]; lines = []
        mix = len(s["paints"]) > 1
        for sp in s["paints"]:
            ref = f"{sp['brand']} {sp['code']}".strip()
            part = f"{sp['parts']} part(s) · " if mix and sp["parts"] else ""
            warn = "  [À RACHETER]" if sp["status"] != "en_stock" else ""
            sw = f'<font color="{sp["hex"]}">■■</font> ' if sp["hex"] else ""
            lines.append(f"{sw}{E(part)}<b>{E(sp['name'])}</b> ({E(ref)}) — <i>{E(sp['technique'])}</i>{warn}")
        if mix: lines.insert(0, "<i>Mélange :</i>")
        if sec["note"]: lines.append(f"<i>{E(sec['note'])}</i>")
        rows.append([Paragraph(E(sec["name"]), bold),
                     Paragraph("<br/>".join(lines) or "-", cell)])
    t = Table(rows, colWidths=[45*mm, 135*mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6e6e6")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(t)
    doc.build(story)
    return buf.getvalue()
