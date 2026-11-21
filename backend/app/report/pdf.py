import io
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.schemas import Recommendation, Report, SourceStatus
from app.land.settings import land_settings
from app.report.summary import summarize

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
]
SECTIONS = [("retencja", "3. Rekomendacje retencyjne"), ("agrotechnika", "4. Rekomendacje agrotechniczne")]


@lru_cache(maxsize=1)
def fonts() -> tuple[str, str]:
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            return "Body", "Body-Bold"
    return "Helvetica", "Helvetica-Bold"


def _styles() -> dict[str, ParagraphStyle]:
    regular, bold = fonts()
    green = colors.HexColor("#14532d")
    return {
        "title": ParagraphStyle("title", fontName=bold, fontSize=17, leading=21, spaceAfter=6, textColor=green),
        "h": ParagraphStyle(
            "h", fontName=bold, fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=4, textColor=green
        ),
        "h3": ParagraphStyle("h3", fontName=bold, fontSize=10.5, leading=13, spaceBefore=4, spaceAfter=2),
        "p": ParagraphStyle("p", fontName=regular, fontSize=9.5, leading=12.5, spaceAfter=3),
        "small": ParagraphStyle(
            "small", fontName=regular, fontSize=7.8, leading=10, textColor=colors.HexColor("#444444")
        ),
        "lead": ParagraphStyle("lead", fontName=bold, fontSize=11, leading=14, spaceAfter=4),
    }


def _p(text: str, style) -> Paragraph:
    return Paragraph(escape(text), style)


def _recommendations(items: list[Recommendation], st) -> list:
    if not items:
        return [_p("Brak rekomendacji w tej kategorii dla tej działki.", st["p"])]
    out = []
    for i, rec in enumerate(items, 1):
        block = [_p(f"{i}. {rec.title}", st["h3"]), _p(rec.justification, st["p"])]
        if rec.eco_scheme:
            block.append(_p(f"Wsparcie: {rec.eco_scheme}", st["small"]))
        if rec.evidence_ids:
            block.append(_p(f"Źródła: {', '.join(rec.evidence_ids)}", st["small"]))
        out.append(KeepTogether(block))
    return out


def _qr(url: str) -> Drawing:
    widget = QrCodeWidget(url)
    x1, y1, x2, y2 = widget.getBounds()
    size = 2.6 * cm
    drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    drawing.add(widget)
    return drawing


def _table(rows: list[list[str]], widths, regular: str, bold: str) -> Table:
    style = ParagraphStyle("cell", fontName=regular, fontSize=7.5, leading=9.5)
    head = ParagraphStyle("head", fontName=bold, fontSize=7.8, leading=9.5)
    data = [[Paragraph(escape(str(c)), head if i == 0 else style) for c in row] for i, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f3ea")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def render(report: Report, map_png: bytes | None) -> bytes:
    st = _styles()
    regular, bold = fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.7 * cm,
        rightMargin=1.7 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Wodiva – raport działki {report.parcel.id}",
        author="Wodiva",
    )
    p = report.parcel
    summary = summarize(report)
    crop = report.water.crop_name if report.water else report.crop
    url = f"{land_settings().public_url.rstrip('/')}/api/report/{report.id}"
    story: list = [
        _p("Wodiva – raport o sytuacji wodnej działki", st["title"]),
        Table(
            [
                [_p(f"Działka: {p.id}", st["p"]), _qr(url)],
                [
                    _p(
                        f"{p.commune or ''}, {p.county or ''}, {p.voivodeship or ''} · obręb "
                        f"{p.region or '-'} · {p.area_ha:.2f} ha",
                        st["p"],
                    ),
                    "",
                ],
                [
                    _p(
                        f"Uprawa: {crop} · data analizy: {report.analysis_date.isoformat()} · raport z "
                        f"{report.created_at:%Y-%m-%d %H:%M} UTC",
                        st["p"],
                    ),
                    "",
                ],
            ],
            colWidths=[14.5 * cm, 3 * cm],
            style=TableStyle([("SPAN", (1, 0), (1, 2)), ("VALIGN", (0, 0), (-1, -1), "TOP")]),
        ),
        _p("1. Ocena stanu wilgotności", st["h"]),
        _p(summary.headline, st["lead"]),
    ]
    story += [_p(f"• {f}", st["p"]) for f in summary.findings]
    story.append(_p("2. Przyczyny niedoboru wody", st["h"]))
    if not report.causes:
        story.append(_p("Nie wskazano przyczyn niedoboru wody (brak oceny albo brak niedoboru).", st["p"]))
    for cause in report.causes:
        extra = f" (ok. {cause.contribution_mm:.0f} mm)" if cause.contribution_mm else ""
        story.append(_p(f"{cause.rank}. {cause.label}{extra}", st["h3"]))
        story.append(_p(cause.evidence, st["small"]))
    for category, title in SECTIONS:
        story.append(_p(title, st["h"]))
        story += _recommendations([r for r in report.recommendations if r.category == category], st)
        if category == "retencja" and map_png:
            story.append(Spacer(1, 4))
            story.append(Image(io.BytesIO(map_png), width=12.5 * cm, height=12.5 * cm))
    story.append(_p("5. Nawadnianie", st["h"]))
    irr = report.irrigation
    if irr is None:
        story.append(_p("Brak oceny nawadniania.", st["p"]))
    else:
        head = f"Nawadnianie: {irr.status}"
        if irr.gross_dose_mm:
            head += f", dawka brutto ok. {irr.gross_dose_mm:.0f} mm"
        if irr.first_day:
            head += f", od {irr.first_day.isoformat()}"
        story.append(_p(head + ".", st["h3"]))
        story.append(_p(irr.reason, st["p"]))
        story.append(_p(irr.legal_note, st["small"]))
    story.append(_p("Pewność wyników", st["h"]))
    rows = [["Część", "Pewność", "Dlaczego"]] + [[c.section, c.level, c.reason] for c in report.confidence]
    story.append(_table(rows, [3.2 * cm, 2 * cm, 12.3 * cm], regular, bold))
    story.append(_p("Braki danych", st["h"]))
    missing = [
        f"{s.name}: {'brak danych' if s.status == SourceStatus.missing else 'dane niepełne'}"
        + (f" ({s.note})" if s.note else "")
        for s in report.sources
        if s.status != SourceStatus.ok
    ]
    story += [_p(f"• {m}", st["p"]) for m in missing] or [_p("Wszystkie źródła odpowiedziały.", st["p"])]
    story.append(_p("Ograniczenia raportu", st["h"]))
    story += [_p(f"• {item.message}", st["p"]) for item in report.limitations]
    story.append(_p("Źródła danych", st["h"]))
    rows = [["Dane", "Licencja", "Okres / pobrano", "Status"]]
    for s in report.sources:
        period = f"{s.period_start or ''}–{s.period_end or ''}".strip("–")
        rows.append(
            [
                s.name,
                s.license,
                f"{period} / {s.retrieved_at:%Y-%m-%d}" if period else f"{s.retrieved_at:%Y-%m-%d}",
                s.status.value,
            ]
        )
    story.append(_table(rows, [5.3 * cm, 6.4 * cm, 3.6 * cm, 2.2 * cm], regular, bold))
    story.append(Spacer(1, 6))
    story.append(
        _p(
            (
                "Raport wygenerowany automatycznie przez aplikację Wodiva na podstawie danych pobranych w chwili "
                "analizy. Rejestr źródeł naukowych (E01–E22): /api/evidence."
            ),
            st["small"],
        )
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.drawString(1.7 * cm, 0.9 * cm, f"Wodiva · raport {report.id} · działka {p.id}")
        canvas.drawRightString(A4[0] - 1.7 * cm, 0.9 * cm, f"strona {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
