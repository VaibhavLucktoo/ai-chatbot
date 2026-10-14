"""Format the approved Markdown review as a readable, diagrammed PDF."""

from pathlib import Path
import hashlib
import html
import json
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / "vendor"))
sys.path.insert(0, str(HERE))

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Preformatted, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents
from diagrams import get_diagram


SOURCE = ROOT / "docs/rag-production-review-2026-10-09.md"
OUTPUT = ROOT / "output/pdf/rag-production-review-2026-10-09.pdf"
NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#157A83")
INK = colors.HexColor("#23384B")
MUTED = colors.HexColor("#5C6F7F")
LIGHT = colors.HexColor("#F0F5F8")
LINE = colors.HexColor("#D3E0E7")


def register_fonts():
    fontdir = Path("C:/Windows/Fonts")
    for name, file in [
        ("Review", "calibri.ttf"), ("Review-Bold", "calibrib.ttf"),
        ("Review-Italic", "calibrii.ttf"), ("Review-BoldItalic", "calibriz.ttf"),
        ("Review-Mono", "consola.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(fontdir / file)))
    pdfmetrics.registerFontFamily(
        "Review", normal="Review", bold="Review-Bold",
        italic="Review-Italic", boldItalic="Review-BoldItalic",
    )


def normalized(value):
    for char in ["\u2011", "\u2012", "\u2013", "\u2014", "\u2212"]:
        value = value.replace(char, "-")
    return value.replace("\u00a0", " ")


def inline(value):
    """Convert inline markup without displaying Markdown punctuation."""
    value = normalized(value)
    saved = []

    def remember(result):
        saved.append(result)
        return "ZZINLINETOKEN" + str(len(saved)-1) + "ZZ"

    def link(match):
        label, target = match.groups()
        label = inline(label)
        if target.startswith(("https://", "http://")):
            return remember('<link href="' + html.escape(target, quote=True) +
                            '" color="#157A83">' + label + '</link>')
        return remember('<font color="#476477">' + label + '</font>')

    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, value)
    value = re.sub(r"`([^`]+)`", lambda m: remember(
        '<font face="Review-Mono" size="8.6">' + html.escape(m.group(1)) + '</font>'
    ), value)
    value = html.escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    for i, item in enumerate(saved):
        value = value.replace("ZZINLINETOKEN" + str(i) + "ZZ", item)
    return value


def create_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "Body", fontName="Review", fontSize=10.5, leading=14.2,
        textColor=INK, spaceAfter=7, allowWidows=0, allowOrphans=0,
    ))
    styles.add(ParagraphStyle(
        "MainHeading", fontName="Review-Bold", fontSize=21, leading=25,
        textColor=NAVY, spaceBefore=3, spaceAfter=15, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        "SubHeading", fontName="Review-Bold", fontSize=12.6, leading=16.4,
        textColor=TEAL, spaceBefore=12, spaceAfter=8, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        "FindingHeading", parent=styles["SubHeading"], fontSize=12,
        leading=15.4, spaceBefore=9, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        "FindingBody", parent=styles["Body"], fontSize=10.2,
        leading=13.6, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        "Cell", fontName="Review", fontSize=9.1, leading=12.2,
        textColor=INK, spaceAfter=0, splitLongWords=True,
    ))
    styles.add(ParagraphStyle(
        "CellHeader", parent=styles["Cell"], fontName="Review-Bold", textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        "BulletItem", parent=styles["Body"], leftIndent=13, firstLineIndent=-9,
        bulletIndent=0, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        "CodeBlock", fontName="Review-Mono", fontSize=7.9, leading=10.7,
        textColor=INK, backColor=LIGHT, borderColor=LINE, borderWidth=0.5,
        borderPadding=9, spaceBefore=4, spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "Caption", fontName="Review-Italic", fontSize=9, leading=12,
        textColor=MUTED, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        "CoverTitle", fontName="Review-Bold", fontSize=35, leading=38,
        textColor=NAVY, spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        "CoverSub", fontName="Review", fontSize=16, leading=21,
        textColor=TEAL, spaceAfter=16,
    ))
    return styles


class ReviewDocument(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        self.section_title = "Architecture and production review"
        self.heading_seq = 0
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                      id="normal")
        self.addPageTemplates(PageTemplate(id="normal", frames=[frame], onPage=self.decorate))

    def beforeDocument(self):
        self.section_title = "Architecture and production review"
        self.heading_seq = 0

    def decorate(self, canvas, doc):
        canvas.saveState()
        if doc.page > 1:
            canvas.setStrokeColor(LINE)
            canvas.setLineWidth(0.65)
            canvas.line(self.leftMargin, A4[1]-34, A4[0]-self.rightMargin, A4[1]-34)
            canvas.setFillColor(MUTED)
            canvas.setFont("Review", 8)
            canvas.drawString(self.leftMargin, A4[1]-27, "AI CHATBOT  /  RAG REVIEW")
            canvas.drawRightString(A4[0]-self.rightMargin, A4[1]-27, "9 October 2026")
        canvas.setStrokeColor(LINE)
        canvas.line(self.leftMargin, 34, A4[0]-self.rightMargin, 34)
        canvas.setFont("Review", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(self.leftMargin, 22, "Static review - proposals require approval")
        canvas.drawRightString(A4[0]-self.rightMargin, 22, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in {"MainHeading", "SubHeading", "FindingHeading"}:
            title = flowable.getPlainText()
            if title == "Contents":
                return
            self.heading_seq += 1
            key = "heading_" + str(self.heading_seq)
            self.canv.bookmarkPage(key)
            if flowable.style.name == "MainHeading":
                self.section_title = title
                self.canv.addOutlineEntry(title, key, level=0, closed=False)
                self.notify("TOCEntry", (0, title, self.page, key))
            elif title.startswith("R") and re.match(r"R\d+", title):
                self.canv.addOutlineEntry(title, key, level=1, closed=True)


def make_table(lines, styles, width):
    cells = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    cells = [row for row in cells if not all(re.fullmatch(r":?-+:?", cell.strip()) for cell in row)]
    count = len(cells[0])
    # Reserve enough space for filenames while keeping prose columns readable.
    first = " ".join(cells[0]).casefold()
    if count == 2:
        ratios = [0.32, 0.68] if ("file" not in first and "group" not in first) else [0.39, 0.61]
    elif count == 3:
        ratios = [0.28, 0.29, 0.43]
        if "file" in first:
            ratios = [0.27, 0.28, 0.45]
    elif count == 4:
        ratios = [0.08, 0.28, 0.23, 0.41]
    else:
        ratios = [1/count]*count
    rows = [[Paragraph(inline(cell), styles["CellHeader" if i == 0 else "Cell"])
             for cell in row] for i, row in enumerate(cells)]
    table = Table(rows, colWidths=[width*x for x in ratios], repeatRows=1,
                  hAlign="LEFT", splitByRow=1, splitInRow=1, spaceBefore=3, spaceAfter=12)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("LINEBELOW", (0,0), (-1,0), 0.75, TEAL),
        ("LINEBELOW", (0,1), (-1,-1), 0.3, LINE),
    ]))
    return table


def build():
    register_fonts()
    styles = create_styles()
    source_bytes = SOURCE.read_bytes()
    source = source_bytes.decode("utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ReviewDocument(str(OUTPUT), pagesize=A4, leftMargin=49, rightMargin=49,
                         topMargin=49, bottomMargin=47,
                         title="RAG architecture and production review",
                         author="AI Chatbot code review", subject="PDF edition of the 9 October 2026 review")
    story = [Spacer(1, 65), Paragraph("AI CHATBOT", styles["CoverSub"]),
             Paragraph("RAG architecture<br/>and production review", styles["CoverTitle"]),
             HRFlowable(width="100%", thickness=3, color=TEAL), Spacer(1, 21),
             Paragraph("9 October 2026", styles["CoverSub"]),
             Paragraph("Full lifecycle review, 20 prioritized findings, file-by-file inventory, and proposed production designs.", styles["Body"]),
             Spacer(1, 24),
             Paragraph("Assessment", styles["SubHeading"]),
             Paragraph("The service is a stateless PDF question-answering backend for a shared corpus. Confidential multi-user access, ingestion crash recovery, resource controls, and production verification need further work.", styles["Body"]),
             Spacer(1, 20),
             Paragraph("How to read this document", styles["SubHeading"]),
             Paragraph("Start with the assessment and lifecycle diagrams. Findings R01-R20 explain the evidence, failure scenarios, and proposed remedies. The final section lists work that can be approved separately.", styles["Body"]),
             Paragraph("This PDF reproduces the review as readable prose, tables, and vector diagrams. It does not implement any proposed change.", styles["Caption"]),
             PageBreak(), Paragraph("Contents", styles["MainHeading"])]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("TOCMain", fontName="Review", fontSize=11,
                                      leading=15, textColor=INK, spaceBefore=10, leftIndent=0,
                                      firstLineIndent=0, rightIndent=24)]
    story.extend([toc, Spacer(1,15), Paragraph(
        "The PDF outline also contains bookmarks for all 20 findings. Source references retain the original filenames and line numbers. Website references remain clickable.", styles["Caption"]), PageBreak()])
    lines = source.splitlines()
    index = 1  # Cover replaces the Markdown title.
    diagram_index = 0
    diagram_labels = [
        "Current ingestion - synchronous request lifecycle",
        "Current query and answer - retrieval and generation boundaries",
        "Current stored data - two tables and their relationship",
        "Proposed production architecture - not implemented",
        "Proposed recovery states - not implemented",
    ]
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("## "):
            if not line.startswith(("## 1.", "## 2.", "## 9.")):
                story.append(PageBreak())
            story.append(Paragraph(inline(line[3:]), styles["MainHeading"]))
            index += 1
            continue
        if line.startswith("### "):
            if re.match(r"### R\d+", line):
                end = index + 1
                while end < len(lines) and not lines[end].startswith(("### ", "## ")):
                    end += 1
                group = [Paragraph(inline(line[4:]), styles["FindingHeading"])]
                paragraphs = "\n".join(lines[index+1:end]).strip().split("\n\n")
                for paragraph in paragraphs:
                    group.append(Paragraph(inline(" ".join(paragraph.splitlines())), styles["FindingBody"]))
                story.append(KeepTogether(group))
                index = end
                continue
            story.append(Paragraph(inline(line[4:]), styles["SubHeading"]))
            index += 1
            continue
        if line.startswith("```"):
            language = line[3:].strip()
            end = index + 1
            while end < len(lines) and not lines[end].startswith("```"):
                end += 1
            if language == "mermaid":
                diagram = get_diagram(diagram_index, width=min(480, doc.width))
                diagram.hAlign = "CENTER"
                if diagram.height > 655:
                    raise ValueError("Diagram exceeds approved portrait layout height")
                story.append(diagram)
                story.append(Paragraph(diagram_labels[diagram_index], styles["Caption"]))
                diagram_index += 1
            else:
                block = normalized("\n".join(lines[index+1:end]))
                block = block.replace("├──", "+--").replace("└──", "+--").replace("│", "|")
                story.append(Preformatted(block, styles["CodeBlock"], maxLineLength=104))
            index = end + 1
            continue
        if line.startswith("|"):
            end = index + 1
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            story.append(make_table(lines[index:end], styles, doc.width))
            index = end
            continue
        if line.startswith("- "):
            story.append(Paragraph("&#8226; " + inline(line[2:]), styles["BulletItem"]))
            index += 1
            continue
        # Metadata at the start is printed one item per paragraph.
        if index < 7:
            content = line.replace("**Change boundary:**", "**Original review change boundary:**")
            story.append(Paragraph(inline(content), styles["Body"]))
            index += 1
            continue
        paragraph = [line]
        end = index + 1
        while (end < len(lines) and lines[end].strip()
               and not lines[end].startswith(("## ", "### ", "```", "|", "- "))):
            paragraph.append(lines[end])
            end += 1
        story.append(Paragraph(inline(" ".join(paragraph)), styles["Body"]))
        index = end
    doc.multiBuild(story)
    if SOURCE.read_bytes() != source_bytes:
        raise RuntimeError("Source Markdown changed during conversion")
    from pypdf import PdfReader
    reader = PdfReader(OUTPUT)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    finding_ids = [f"R{i:02}" for i in range(1,21)]
    missing = [x for x in finding_ids if x not in text]
    if missing:
        raise RuntimeError("Missing findings in PDF: " + str(missing))
    metadata = {"output": str(OUTPUT), "pages": len(reader.pages), "bytes": OUTPUT.stat().st_size,
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(), "diagrams": diagram_index,
                "findings": 20, "source_unchanged": True}
    (HERE / "build_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    build()
