from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/pdfs/vendor'))
import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageDraw

pdf = pdfium.PdfDocument(str(ROOT / 'output/pdf/ai_chatbot_project_analysis.pdf'))
out = ROOT / 'tmp/pdfs/rendered'
out.mkdir(parents=True, exist_ok=True)
thumbs = []
for i, page in enumerate(pdf):
    im = page.render(scale=1.5).to_pil()
    im.save(out / f'page-{i+1:02d}.png')
    thumbs.append(ImageOps.contain(im, (298, 421)))
    page.close()
sheet = Image.new('RGB', (4*318, ((len(thumbs)+3)//4)*456), '#dce3e8')
draw = ImageDraw.Draw(sheet)
for i, im in enumerate(thumbs):
    x, y = (i % 4)*318+10, (i//4)*456
    sheet.paste(im, (x, y+24))
    draw.text((x, y+6), f'Page {i+1}', fill='black')
sheet.save(out / 'contact-sheet.png')
print('Rendered pages:', len(thumbs))
