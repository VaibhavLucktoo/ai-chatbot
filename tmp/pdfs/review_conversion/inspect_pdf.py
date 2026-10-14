"""Render the PDF edition for visual QA and check source heading coverage."""

from pathlib import Path
import json
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / "vendor"))

from PIL import Image, ImageDraw
import pypdfium2 as pdfium
from pypdf import PdfReader

PDF = ROOT / "output/pdf/rag-production-review-2026-10-09.pdf"
SOURCE = ROOT / "docs/rag-production-review-2026-10-09.md"
RENDER = HERE / "rendered"


def normalize(value):
    for c in ["\u2011", "\u2012", "\u2013", "\u2014", "\u2212"]:
        value = value.replace(c, "-")
    return re.sub(r"\s+", " ", value).strip()


def main():
    RENDER.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(PDF)
    extracted = [page.extract_text() or "" for page in reader.pages]
    combined = normalize(" ".join(extracted))
    headings = [normalize(line.lstrip("# ")) for line in SOURCE.read_text(encoding="utf-8").splitlines()
                if line.startswith(("## ", "### "))]
    missing = [h for h in headings if h not in combined]
    if missing:
        raise ValueError("Missing source headings: " + str(missing))
    document = pdfium.PdfDocument(str(PDF))
    summaries, images = [], []
    for i in range(len(document)):
        page = document[i]
        bitmap = page.render(scale=1.5)
        im = bitmap.to_pil().convert("RGB")
        output = RENDER / f"page-{i+1:02}.png"
        im.save(output)
        images.append(output)
        textpage = page.get_textpage()
        count = textpage.count_chars()
        outside = []
        for ch in range(count):
            try:
                x0,y0,x1,y1 = textpage.get_charbox(ch)
            except Exception:
                continue
            if x0 < -1 or y0 < -1 or x1 > page.get_width()+1 or y1 > page.get_height()+1:
                outside.append(ch)
        summaries.append({"page": i+1, "characters": len(extracted[i]), "outside_page_characters": len(outside),
                          "first_line": extracted[i].splitlines()[0] if extracted[i].splitlines() else ""})
        textpage.close()
        page.close()
    document.close()
    sheets = []
    for start in range(0,len(images),12):
        paths=images[start:start+12]
        width,height=360,510
        canvas=Image.new("RGB", (4*(width+16)+16, 3*(height+32)+16), "#d9e2e7")
        draw=ImageDraw.Draw(canvas)
        for j,path in enumerate(paths):
            with Image.open(path) as source:
                thumb=source.copy()
                thumb.thumbnail((width,height),Image.Resampling.LANCZOS)
            x=16+(j%4)*(width+16)
            y=16+(j//4)*(height+32)
            canvas.paste(thumb,(x,y+18))
            draw.text((x,y), f"Page {start+j+1}", fill="#17324d")
        sheet=RENDER / f"contact-{start//12+1:02}.png"
        canvas.save(sheet)
        sheets.append(str(sheet))
    result={"pdf":str(PDF), "pages":len(images), "source_headings_verified":len(headings),
            "all_findings_present":all(f"R{i:02}" in combined for i in range(1,21)),
            "page_summaries":summaries, "contact_sheets":sheets}
    (HERE/"inspection.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
