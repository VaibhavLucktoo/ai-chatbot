"""Portrait-friendly vector replacements for the report's five Mermaid blocks.

Public API: get_diagram(index, width=480), where index is zero-based and follows
the Markdown source order. Returns a ReportLab Drawing. No browser required.
"""

from math import atan2, cos, sin

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String, Circle
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase.pdfmetrics import stringWidth


NAVY = HexColor("#12304B")
TEAL = HexColor("#177C83")
ORANGE = HexColor("#C77B25")
INK = HexColor("#20374A")
GRAY = HexColor("#647887")
PALE_BLUE = HexColor("#EDF3F8")
PALE_TEAL = HexColor("#E9F5F3")
PALE_ORANGE = HexColor("#FFF3E4")
PALE_GRAY = HexColor("#F5F7F9")
FONT = "Helvetica"
BOLD = "Helvetica-Bold"
BASE_WIDTH = 480


def _wrap(text, width, size=9.5, font=FONT):
    result = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            result.append("")
            continue
        line = ""
        for word in words:
            trial = f"{line} {word}" if line else word
            if line and stringWidth(trial, font, size) > width:
                result.append(line)
                line = word
            else:
                line = trial
        result.append(line)
    return result


class _Diagram:
    """Coordinates use a top-left origin; exported Drawing uses PDF coordinates."""

    def __init__(self, height):
        self.height = height
        self.drawing = Drawing(BASE_WIDTH, height)

    def rect(self, x, y, w, h, fill, stroke=TEAL, radius=5, sw=0.8):
        self.drawing.add(Rect(x, self.height - y - h, w, h, rx=radius, ry=radius,
                              fillColor=fill, strokeColor=stroke, strokeWidth=sw))

    def text(self, text, x, y, width, size=9.5, leading=11.5, bold=False,
             color=INK, align="center"):
        font = BOLD if bold else FONT
        lines = _wrap(text, width, size, font)
        for n, line in enumerate(lines):
            anchor = "middle" if align == "center" else "start"
            px = x + width / 2 if align == "center" else x
            self.drawing.add(String(px, self.height - y - size - n * leading,
                                    line, fontName=font, fontSize=size,
                                    fillColor=color, textAnchor=anchor))
        return len(lines) * leading

    def box(self, text, x, y, w, h, kind="normal", size=9.5):
        fill, stroke, bold = PALE_TEAL, TEAL, False
        if kind == "main":
            fill, stroke, bold = NAVY, NAVY, True
        elif kind == "decision":
            fill, stroke, bold = PALE_ORANGE, ORANGE, True
        elif kind == "outcome":
            fill, stroke = PALE_BLUE, NAVY
        elif kind == "warning":
            fill, stroke = PALE_ORANGE, ORANGE
        elif kind == "data":
            fill, stroke = PALE_GRAY, NAVY
        self.rect(x, y, w, h, fill, stroke, radius=10 if kind == "decision" else 5)
        font = BOLD if bold else FONT
        lines = _wrap(text, w - 13, size, font)
        leading = size + 2
        text_top = y + (h - len(lines) * leading) / 2 + 0.5
        self.text(text, x + 6.5, text_top, w - 13, size=size, leading=leading,
                  bold=bold, color=white if kind == "main" else INK)

    def arrow(self, points, color=GRAY, dashed=False, head=True, sw=0.9):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            line = Line(x1, self.height - y1, x2, self.height - y2,
                        strokeColor=color, strokeWidth=sw)
            if dashed:
                line.strokeDashArray = [3, 3]
            self.drawing.add(line)
        if head:
            (x1, y1), (x2, y2) = points[-2:]
            angle = atan2(y2 - y1, x2 - x1)
            back = 5
            side = 2.7
            ax, ay = x2 - back * cos(angle), y2 - back * sin(angle)
            vertices = [x2, self.height - y2,
                        ax - side * sin(angle), self.height - (ay + side * cos(angle)),
                        ax + side * sin(angle), self.height - (ay - side * cos(angle))]
            self.drawing.add(Polygon(vertices, fillColor=color, strokeColor=color,
                                     strokeWidth=0.2))

    def label(self, text, x, y, w, size=9):
        lines = _wrap(text, w, size)
        self.rect(x - 2, y - 1, w + 4, len(lines) * (size + 2) + 2,
                  white, white, radius=0, sw=0)
        self.text(text, x, y, w, size=size, leading=size + 2, color=GRAY)

    def note(self, text, y, color=GRAY):
        self.text(text, 10, y, 460, size=9, leading=11, color=color)


def _ingestion():
    d = _Diagram(646)
    x, w, center = 148, 218, 257
    stages = [
        ("HTTP upload", 8, 26, "main"),
        ("Multipart parsing and file spooling", 47, 32, "normal"),
        ("Filename, content type, byte envelope and size checks", 91, 36, "normal"),
        ("SHA-256 of exact PDF bytes", 140, 28, "normal"),
        ("Existing hash?", 180, 34, "decision"),
        ("pypdf page extraction in a thread", 238, 32, "normal"),
        ("Claim pending row in short DB transaction", 284, 38, "normal"),
        ("Claim owned?", 337, 32, "decision"),
        ("Page-local token chunks", 389, 28, "normal"),
        ("Embedding batches of 32", 433, 28, "normal"),
        ("Validate and retain all chunk records in memory", 477, 38, "normal"),
        ("Single transaction: chunks plus ready status", 529, 42, "normal"),
        ("Searchable PDF", 586, 28, "outcome"),
    ]
    for (_, y1, h1, _), (_, y2, _, _) in zip(stages, stages[1:]):
        d.arrow([(center, y1 + h1), (center, y2)])
    d.arrow([(119, 109), (x, 109)])
    d.arrow([(x, 197), (120, 197)])
    d.arrow([(x + w, 197), (379, 197)])
    d.arrow([(x + w, 353), (426, 353), (426, 224)])
    # All four cleanup edges join a single failure/cancellation spine.
    for yy in (403, 447, 496, 550):
        d.arrow([(x, yy), (136, yy)], color=ORANGE, head=False)
    d.arrow([(136, 403), (136, 550)], color=ORANGE, head=False)
    d.arrow([(136, 477), (120, 477)], color=ORANGE)
    for text, y, h, kind in stages:
        d.box(text, x, y, w, h, kind)
    d.box("CLI file", 10, 95, 109, 28, "main")
    d.box("Return busy result; HTTP maps to 409", 7, 181, 113, 51, "warning")
    d.box("Return existing result", 379, 181, 94, 43, "outcome")
    d.box("Attempt pending-to-failed cleanup", 7, 444, 113, 66, "warning")
    d.label("pending", 91, 167, 50)
    d.label("ready", 379, 165, 65)
    d.label("missing or failed", 196, 219, 122)
    d.label("no", 397, 333, 22)
    d.label("yes", 238, 370, 38)
    d.text("Failure or cancellation from chunking, embedding, validation or publication",
           7, 521, 113, size=9, leading=11, color=ORANGE)
    d.note("The upload request waits for the entire pipeline. Publication is atomic.", 627)
    return d.drawing


def _query():
    d = _Diagram(590)
    center = 247
    main = [
        ("POST /v1/chat", 6, 24, "main"),
        ("LangGraph: retrieve", 39, 26, "normal"),
        ("Unspecified document reference?", 74, 34, "decision"),
        ("FastEmbed query vector", 125, 30, "normal"),
        ("PostgreSQL: ready and compatible chunks", 166, 32, "data"),
    ]
    for (_, y1, h1, _), (_, y2, _, _) in zip(main, main[1:]):
        d.arrow([(center, y1 + h1), (center, y2)])
    d.arrow([(138, 91), (65, 91), (65, 123)])
    d.arrow([(356, 91), (420, 91), (420, 125)])
    d.arrow([(366, 144), (356, 144)])
    d.arrow([(center, 198), (center, 202), (124, 202), (124, 209)])
    d.arrow([(center, 198), (center, 202), (352, 202), (352, 209)])
    d.arrow([(124, 249), (124, 255), (center, 255), (center, 261)])
    d.arrow([(352, 249), (352, 255), (center, 255), (center, 261)])
    d.arrow([(center, 288), (center, 301)])
    d.arrow([(center, 331), (center, 344)])
    d.arrow([(138, 360), (65, 360), (65, 397)])
    d.arrow([(center, 376), (center, 397)])
    d.arrow([(center, 433), (center, 440), (240, 440), (240, 447)])
    d.arrow([(313, 464), (326, 464)])
    d.arrow([(398, 481), (398, 493)])
    d.arrow([(326, 514), (313, 514)])
    d.arrow([(168, 514), (154, 514)])
    d.arrow([(81, 535), (81, 539), (240, 539), (240, 543)])
    for text, y, h, kind in main:
        d.box(text, 138, y, 218, h, kind)
    d.box("Return upload prompt or filename choices", 7, 123, 116, 55, "warning")
    d.box("Auto-select document", 366, 125, 107, 40)
    d.box("Semantic candidates: cosine distance", 37, 209, 174, 40)
    d.box("Lexical candidates: English full-text search", 264, 209, 176, 40)
    d.box("Reciprocal Rank Fusion", 138, 261, 218, 27)
    d.box("Take first N passages in fused order", 138, 301, 218, 30)
    d.box("Evidence heuristic passes?", 138, 344, 218, 32, "decision")
    d.box("Canonical insufficient-context answer", 7, 397, 116, 44, "warning")
    d.box("Validate passages and build JSON context", 138, 397, 218, 36)
    d.box("LangChain CompatibleChatModel.ainvoke", 168, 447, 145, 34)
    d.box("New HTTPX client: chat/completions", 326, 447, 145, 34)
    d.box("Configured local or hosted model", 326, 493, 145, 42, "main")
    d.box("Validate complete text and JSON schema", 168, 493, 145, 42)
    d.box("Check source numbers and renumber citations", 9, 493, 145, 42)
    d.box("Answer plus document/page references", 168, 543, 145, 30, "outcome")
    d.label("yes: zero or multiple ready documents", 7, 95, 116, size=9)
    d.label("exactly one", 366, 102, 105)
    d.label("no or explicit IDs", 181, 110, 134)
    d.label("no", 93, 362, 29)
    d.label("yes", 230, 378, 34)
    d.note("Read transaction closes before generation. Citation validity is not factual support.", 577)
    return d.drawing


def _table(d, title, fields, x, y, w):
    row_h = 21
    header_h = 30
    h = header_h + len(fields) * row_h
    d.rect(x, y, w, h, white, NAVY, radius=5)
    d.rect(x, y, w, header_h, NAVY, NAVY, radius=4)
    d.text(title, x + 5, y + 7, w - 10, size=10, bold=True, color=white)
    for i, (typ, name) in enumerate(fields):
        ry = y + header_h + i * row_h
        if i % 2 == 0:
            d.rect(x + 1, ry, w - 2, row_h, PALE_BLUE, PALE_BLUE, radius=0, sw=0)
        d.text(typ, x + 9, ry + 5, 58, size=9, align="left", color=GRAY)
        d.text(name, x + 72, ry + 5, w - 80, size=9.5, align="left")


def _data_model():
    d = _Diagram(293)
    d.text("One DOCUMENT contains zero or more DOCUMENT_CHUNK records.",
           10, 5, 460, size=10, bold=True)
    d.arrow([(122, 54), (122, 35), (356, 35), (356, 54)])
    d.label("1", 167, 23, 20)
    d.label("0..*", 301, 23, 32)
    _table(d, "DOCUMENT", [
        ("uuid", "id [PK]"), ("string", "filename"),
        ("string", "content_sha256 [UK]"), ("int", "page_count"),
        ("string", "status"), ("datetime", "created_at"),
    ], 12, 54, 218)
    _table(d, "DOCUMENT_CHUNK", [
        ("uuid", "id [PK]"), ("uuid", "document_id [FK]"),
        ("int", "chunk_index"), ("int", "page_number"),
        ("text", "content"), ("string", "embedding_space"),
        ("vector", "embedding"),
    ], 250, 54, 218)
    d.note("PK = primary key; FK = foreign key; UK = unique key.", 245)
    d.note("Current schema has no owner/tenant, source-PDF, version, or job-lease fields.", 266)
    return d.drawing


def _production():
    d = _Diagram(649)
    # Left lane = durable ingestion; right lane = authorized query and generation.
    d.arrow([(240, 31), (240, 43)])
    d.arrow([(240, 79), (240, 95)])
    d.arrow([(109, 118), (95, 118), (95, 193)])
    d.arrow([(190, 142), (219, 142), (219, 291), (190, 291)])
    d.arrow([(365, 142), (365, 193)])
    d.arrow([(102, 312), (102, 329)])
    d.arrow([(15, 352), (7, 352), (7, 215), (15, 215)])
    d.arrow([(102, 375), (102, 395)])
    d.arrow([(102, 435), (102, 487)])
    d.arrow([(367, 231), (367, 253)])
    d.arrow([(280, 272), (241, 272), (241, 520), (190, 520)])
    d.arrow([(367, 291), (367, 310)])
    d.arrow([(367, 354), (367, 374)])
    d.arrow([(367, 409), (367, 429)])
    d.arrow([(367, 469), (367, 490)])
    d.arrow([(367, 528), (367, 548)])
    d.arrow([(455, 570), (474, 570), (474, 118), (379, 118)])
    # Explicit redacted-observability edges, matching the source diagram.
    d.arrow([(15, 608), (2, 608), (2, 118), (109, 118)], color=TEAL, dashed=True)
    d.arrow([(15, 600), (10, 600), (10, 363), (15, 363)], color=TEAL, dashed=True)
    d.arrow([(190, 608), (260, 608), (260, 332), (280, 332)], color=TEAL, dashed=True)
    d.box("Client", 161, 5, 158, 26, "main")
    d.box("TLS ingress: upload limits and rate limits", 109, 43, 270, 36)
    d.box("API: identity, authorization, request budget", 109, 95, 270, 47, "main")
    d.box("Private immutable PDF storage", 15, 193, 175, 44, "data")
    d.box("Durable ingestion jobs", 15, 274, 175, 38, "data")
    d.box("Bounded isolated ingestion workers", 15, 329, 175, 46)
    d.box("Ingestion embedding capacity", 15, 395, 175, 40)
    d.box("PostgreSQL: document versions, chunks, indexes", 15, 487, 175, 65, "data")
    d.box("Query embedding capacity", 280, 193, 175, 38)
    d.box("Indexed hybrid retrieval", 280, 253, 175, 38)
    d.box("LangGraph: context budget and evidence decisions", 280, 310, 175, 44)
    d.box("LangChain model interface", 280, 374, 175, 35)
    d.box("Shared HTTP pool and bounded model calls", 280, 429, 175, 40)
    d.box("Approved local or hosted provider", 280, 490, 175, 38, "main")
    d.box("Validate output and citation contract", 280, 548, 175, 44)
    d.box("Redacted metrics and release evaluations", 15, 582, 175, 50, "outcome")
    d.label("upload source", 28, 156, 112)
    d.label("create job; return 202", 195, 169, 70)
    d.label("authorized query", 302, 158, 129)
    d.label("read source", 21, 246, 112)
    d.text("INGESTION", 26, 449, 149, size=9, bold=True, color=TEAL)
    d.note("Proposed design. Dashed arrows carry redacted metrics/evaluation signals.", 636)
    return d.drawing


def _recovery():
    d = _Diagram(490)
    d.drawing.add(Circle(240, d.height - 15, 5, fillColor=NAVY, strokeColor=NAVY))
    d.arrow([(240, 20), (240, 35)])
    d.arrow([(240, 69), (240, 137)])
    d.arrow([(240, 175), (240, 242)])
    d.arrow([(240, 274), (240, 330)])
    d.arrow([(240, 362), (240, 415)])
    d.arrow([(329, 156), (409, 156), (409, 207)], color=ORANGE)
    d.arrow([(464, 229), (474, 229), (474, 52), (329, 52)], color=ORANGE)
    d.arrow([(151, 156), (88, 156), (88, 52), (151, 52)], color=ORANGE)
    d.box("queued", 151, 35, 178, 34, "outcome")
    d.box("processing", 151, 137, 178, 38, "main")
    d.box("ready", 151, 242, 178, 32, "outcome")
    d.box("superseded", 151, 330, 178, 32, "data")
    d.box("deleted", 151, 415, 178, 32, "data")
    d.box("failed", 354, 207, 110, 45, "warning")
    d.label("Worker claims lease and attempt token", 151, 87, 178)
    d.label("Owner publishes complete index generation", 151, 193, 178)
    d.label("Owner records terminal failure", 351, 165, 110)
    d.label("Approved retry", 343, 33, 116)
    d.label("Expired lease reconciled", 22, 92, 115)
    d.label("Replacement becomes active", 151, 293, 178)
    d.label("Retention policy", 151, 382, 178)
    d.note("Proposed recovery: only the current attempt token may publish or record failure.", 466)
    return d.drawing


_BUILDERS = (_ingestion, _query, _data_model, _production, _recovery)


def get_diagram(index, width=480):
    """Return one of five drawings in source order, scaled to the requested width.

    Base dimensions (points): 480x646, 480x590, 480x293, 480x649, 480x490.
    Scaling also scales text; use width >=480 for 9-10 pt base labels.
    """
    if type(index) is not int or not 0 <= index < len(_BUILDERS):
        raise ValueError("Diagram index must be an integer from 0 to 4.")
    if not isinstance(width, (int, float)) or width <= 0:
        raise ValueError("Diagram width must be a positive number.")
    drawing = _BUILDERS[index]()
    factor = float(width) / BASE_WIDTH
    drawing.scale(factor, factor)
    drawing.width *= factor
    drawing.height *= factor
    return drawing
