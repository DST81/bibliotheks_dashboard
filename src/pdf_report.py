from __future__ import annotations

import io
import pandas as pd
import requests
import textwrap
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from fpdf import FPDF

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency fallback
    Image = None


KPIItems = Mapping[str, Any] | Sequence[tuple[str, Any]]
ChartItems = Iterable[tuple[str, Any]]
FilterItems = Mapping[str, Any] | Sequence[tuple[str, Any]]


@dataclass(frozen=True)
class ReportResult:
    pdf_bytes: bytes
    failed_charts: list[tuple[str, str]]


def _pdf_text(value: Any) -> str:
    """FPDF core fonts are latin-1 based; replace unsupported symbols safely."""
    text = "" if value is None else str(value)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _normalise_kpis(kpis: KPIItems) -> list[tuple[str, str]]:
    if isinstance(kpis, Mapping):
        items = kpis.items()
    else:
        items = kpis
    return [(_pdf_text(label), _pdf_text(value)) for label, value in items]


def _normalise_filters(filters: FilterItems | None) -> list[tuple[str, str]]:
    if not filters:
        return []
    if isinstance(filters, Mapping):
        items = filters.items()
    else:
        items = filters
    normalised = []
    for label, value in items:
        if value in (None, "", []):
            continue
        value_text = str(value)
        if value_text in ("Alle", "Nein"):
            continue
        normalised.append((_pdf_text(label), _pdf_text(value_text)))
    return normalised


def chart_to_png_bytes(chart: Any, *, scale: float = 2.0, width: int = 1500, height: int = 520) -> bytes:
    """Render common dashboard chart objects to PNG bytes.

    Supports Altair/Vega charts via ``save`` and Plotly figures via ``to_image``.
    """
    if chart is None:
        raise ValueError("Kein Diagramm uebergeben.")

    if hasattr(chart, "save"):
        buffer = io.BytesIO()
        if hasattr(chart, "properties"):
            try:
                chart = chart.properties(width=width, height=height)
            except Exception:
                pass
        chart.save(buffer, format="png", scale_factor=scale)
        buffer.seek(0)
        return buffer.read()

    if hasattr(chart, "to_image"):
        return chart.to_image(format="png", width=width, height=height, scale=scale)

    raise TypeError(f"Diagrammtyp wird nicht unterstuetzt: {type(chart).__name__}")


class DashboardReportPDF(FPDF):
    def __init__(self, *, title: str, subtitle: str | None = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.title = _pdf_text(title)
        self.subtitle = _pdf_text(subtitle)
        self.generated_at = datetime.now()
        self.set_margins(14, 18, 14)
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(38, 70, 83)
            self.cell(0, 6, self.title, ln=True)
            self.set_draw_color(224, 232, 236)
            self.line(14, self.get_y() + 1, 196, self.get_y() + 1)
            self.ln(6)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(130, 143, 150)
        self.cell(0, 8, f"Seite {self.page_no()}", align="C")


def _add_cover(
    pdf: DashboardReportPDF,
    accent_color: tuple[int, int, int]
):
    pdf.add_page()

    r, g, b = accent_color

    # Kompakter Header
    header_height = 24

    pdf.set_fill_color(r, g, b)
    pdf.rect(
        0,
        0,
        210,
        header_height,
        style="F"
    )

    # -----------------------------------------
    # Linke Spalte: Titel + erstellt am
    # -----------------------------------------
    pdf.set_xy(14, 7)

    pdf.set_font(
        "Helvetica",
        "B",
        16
    )

    pdf.set_text_color(
        255, 255, 255
    )

    pdf.cell(
        100,
        6,
        pdf.title
    )

    pdf.set_xy(14, 15)

    pdf.set_font(
        "Helvetica",
        "",
        7.5
    )

    pdf.set_text_color(
        220, 230, 234
    )

    pdf.cell(
        100,
        4,
        f"Erstellt am {pdf.generated_at:%d.%m.%Y %H:%M}"
    )

    # -----------------------------------------
    # Rechte Spalte: Subtitle / Filterinfos
    # -----------------------------------------
    if pdf.subtitle:

        subtitle_lines = pdf.subtitle.splitlines()

        pdf.set_font(
            "Helvetica",
            "",
            7.5
        )

        pdf.set_text_color(
            235, 240, 242
        )

        right_x = 118
        right_width = 78

        pdf.set_xy(
            right_x,
            7
        )

        for line in subtitle_lines[:2]:

            pdf.cell(
                right_width,
                5,
                _pdf_text(line),
                align="R"
            )

            pdf.set_x(right_x)
            pdf.set_y(pdf.get_y() + 5)
            pdf.set_x(right_x)

    # Startposition für restlichen Inhalt
    pdf.set_text_color(
        48, 56, 64
    )

    pdf.set_y(
        header_height + 7
    )


def _section_title(pdf: FPDF, title: str):
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(38, 70, 83)
    pdf.cell(0, 8, _pdf_text(title), ln=True)
    pdf.set_draw_color(224, 232, 236)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(5)


def _add_kpi_cards(
    pdf: FPDF,
    kpis: list[tuple[str, str]],
    accent_color: tuple[int, int, int],
    *,
    title: str = "Kennzahlen",
):
    if not kpis:
        return

    _section_title(pdf, title)

    cards_per_row = 3
    gap = 5
    page_width = 182
    card_width = (page_width - gap * (cards_per_row - 1)) / cards_per_row
    card_height = 25
    start_x = 14
    r, g, b = accent_color

    row_y = pdf.get_y()
    for idx, (label, value) in enumerate(kpis):
        value_lines = value.splitlines()
        current_value = value_lines[0] if value_lines else ""
        detail_value = " | ".join(value_lines[1:])

        col = idx % cards_per_row
        if col == 0 and idx > 0:
            row_y += card_height + 5
        if row_y > 246:
            pdf.add_page()
            row_y = pdf.get_y()

        x = start_x + col * (card_width + gap)
        y = row_y
        pdf.set_fill_color(250, 252, 253)
        pdf.set_draw_color(224, 232, 236)
        pdf.rect(x, y, card_width, card_height, style="DF")
        pdf.set_draw_color(r, g, b)
        pdf.line(x, y, x, y + card_height)

        pdf.set_xy(x + 4, y + 3)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(108, 122, 132)
        pdf.cell(card_width - 8, 5, label[:34])
        pdf.set_x(x + 4)
        pdf.set_y(y + 10)
        pdf.set_x(x + 4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(34, 40, 46)
        pdf.cell(card_width - 8, 8, current_value[:22])

        if detail_value:
            pdf.set_xy(x + 4, y + 19)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(108, 122, 132)
            pdf.cell(card_width - 8, 4, detail_value[:38])

    pdf.set_y(row_y + card_height + 7)


def _add_filter_summary(pdf: FPDF, filters: list[tuple[str, str]]):
    if not filters:
        return

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(38, 70, 83)
    pdf.cell(0, 4, "Aktive Filter", ln=True)

    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(48, 56, 64)
    filter_text = " | ".join(f"{label}: {value}" for label, value in filters[:10])
    if len(filters) > 10:
        filter_text += f" | +{len(filters) - 10} weitere"

    pdf.set_fill_color(245, 248, 250)
    pdf.set_draw_color(224, 232, 236)
    x = 14
    y = pdf.get_y() + 1
    width = 182
    line_height = 4
    lines = textwrap.wrap(_pdf_text(filter_text), width=132) or [""]
    box_height = max(8, len(lines) * line_height + 4)
    pdf.rect(x, y, width, box_height, style="DF")
    pdf.set_xy(x + 3, y + 2)
    pdf.multi_cell(width - 6, line_height, _pdf_text(filter_text))
    pdf.set_y(y + box_height + 5)


def _image_size_mm(png_bytes: bytes, max_width: float, max_height: float) -> tuple[float, float]:
    if Image is None:
        return max_width, min(max_height, 95)

    with Image.open(io.BytesIO(png_bytes)) as image:
        width_px, height_px = image.size

    if width_px <= 0 or height_px <= 0:
        return max_width, min(max_height, 95)

    ratio = min(max_width / width_px, max_height / height_px)
    return width_px * ratio, height_px * ratio


def _add_chart(
    pdf: FPDF,
    title: str,
    chart: Any,
    failed_charts: list[tuple[str, str]],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
):
    pdf.set_xy(x, y)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(38, 70, 83)
    pdf.multi_cell(width, 5, _pdf_text(title))
    image_y = pdf.get_y() + 1.5

    try:
        png_bytes = chart_to_png_bytes(chart, width=1500, height=520)
        if not png_bytes:
            raise ValueError("Diagramm-Rendering lieferte leere Bytes zurueck.")

        max_width = width
        max_height = height - (image_y - y)
        image_width, image_height = _image_size_mm(png_bytes, max_width, max_height)

        image_x = x + (max_width - image_width) / 2
        pdf.image(io.BytesIO(png_bytes), x=image_x, y=image_y, w=image_width, h=image_height)
    except Exception as exc:
        failed_charts.append((title, str(exc)))
        pdf.set_fill_color(255, 247, 237)
        pdf.set_draw_color(251, 191, 36)
        pdf.rect(x, image_y, width, 18, style="DF")
        pdf.set_xy(x + 3, image_y + 4)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(146, 64, 14)
        pdf.multi_cell(width - 6, 5, _pdf_text(f"Diagramm konnte nicht eingebettet werden: {exc}"))


def _add_charts_grid(pdf: FPDF, charts: list[tuple[str, Any]], failed_charts: list[tuple[str, str]]):
    if not charts:
        return

    if pdf.get_y() > 92:
        pdf.add_page()

    _section_title(pdf, "Diagramme")

    chart_width = 182
    chart_height = 70
    gap = 8

    for chart_title, chart in charts[:3]:
        y = pdf.get_y()
        if y + chart_height > 274:
            pdf.add_page()
            _section_title(pdf, "Diagramme")
            y = pdf.get_y()

        _add_chart(
            pdf,
            chart_title,
            chart,
            failed_charts,
            x=14,
            y=y,
            width=chart_width,
            height=chart_height,
        )

        pdf.set_y(y + chart_height + gap)


def _output_bytes(pdf: FPDF) -> bytes:
    output = pdf.output()
    if isinstance(output, bytes):
        return output
    if isinstance(output, bytearray):
        return bytes(output)
    return str(output).encode("latin-1", errors="replace")


def build_report_pdf(
    *,
    title: str,
    kpis: KPIItems,
    charts: ChartItems,
    subtitle: str | None = None,
    filters: FilterItems | None = None,
    kpi_title: str = "Kennzahlen",
    kpi_sections: Sequence[tuple[str, KPIItems]] | None = None,
    accent_color: tuple[int, int, int] = (38, 70, 83),
) -> ReportResult:
    """Build a reusable KPI and chart dashboard report."""
    pdf = DashboardReportPDF(title=title, subtitle=subtitle)
    _add_cover(pdf, accent_color)
    _add_filter_summary(pdf, _normalise_filters(filters))
    _add_kpi_cards(pdf, _normalise_kpis(kpis), accent_color, title=kpi_title)
    for section_title, section_kpis in kpi_sections or []:
        _add_kpi_cards(
            pdf,
            _normalise_kpis(section_kpis),
            accent_color,
            title=section_title,
        )

    failed_charts: list[tuple[str, str]] = []
    charts = list(charts)
    _add_charts_grid(pdf, charts, failed_charts)

    return ReportResult(pdf_bytes=_output_bytes(pdf), failed_charts=failed_charts)

def build_top_media_pdf(
    top_media: pd.DataFrame,
    *,
    title: str,
    subtitle: str | None = None,
) -> bytes:

    pdf = DashboardReportPDF(
        title=title,
        subtitle=subtitle,
    )

    _add_cover(
        pdf,
        accent_color=(38, 70, 83),
    )

    _section_title(pdf, "Top Medien")

    # -----------------------------------------
    # Layout
    # -----------------------------------------
    cards_per_row = 3

    card_width = 56
    card_height = 72

    gap_x = 7
    gap_y = 4

    x_positions = [
        14,
        14 + card_width + gap_x,
        14 + 2*(card_width + gap_x)
    ]

    start_y = pdf.get_y()

    top_media_reset = top_media.reset_index(drop=True)

    for idx, row in top_media_reset.iterrows():

        position_in_row = idx % cards_per_row

        # Neue Zeile
        if position_in_row == 0:

            # Ab zweiter Kartenzeile nach unten gehen
            if idx > 0:
                start_y += card_height + gap_y

            # Seitenumbruch
            if start_y + card_height > 274:
                pdf.add_page()
                _section_title(pdf, "Top Medien")
                start_y = pdf.get_y()

        x = x_positions[position_in_row]

        add_media_card(
            pdf=pdf,
            row=row,
            rank=idx + 1,
            x=x,
            y=start_y,
            width=card_width,
            height=card_height,
        )

    return _output_bytes(pdf)

def load_cover(url):
    if Image is None:
        return None

    if not url or not str(url).strip():
        return None

    try:
        response = requests.get(
            str(url),
            timeout=5
        )
        response.raise_for_status()

        image = Image.open(
            io.BytesIO(response.content)
        ).convert("RGB")

        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=90
        )
        buffer.seek(0)

        return buffer

    except Exception:
        return None

def add_media_card(
    pdf,
    row,
    rank,
    x,
    y,
    width=56,
    height=62,
):
    # Hintergrund
    pdf.set_fill_color(250, 252, 253)
    pdf.set_draw_color(224, 232, 236)
    pdf.rect(x, y, width, height, style="DF")

    # Kopfzeile
    header_y = y + 3

    pdf.set_xy(x + 4, header_y)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(38, 70, 83)
    pdf.cell(15, 5, f"#{rank}", align="L")

    pdf.set_xy(x + 20, header_y)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(42, 157, 143)
    pdf.cell(
        width - 24,
        5,
        f"{int(row.get('Ausleihen', 0))} Ausleihen",
        align="R",
    )

    # Cover
    cover = load_cover(row.get("URL_Cover"))

    cover_w = 28
    cover_h = 39

    cover_x = x + (width - cover_w) / 2
    cover_y = y + 9

    if cover:
        pdf.image(
            cover,
            x=cover_x,
            y=cover_y,
            w=cover_w,
            h=cover_h,
        )
    else:
        pdf.set_fill_color(235, 238, 240)
        pdf.rect(
            cover_x,
            cover_y,
            cover_w,
            cover_h,
            style="F",
        )

    # Titel
    titel = _pdf_text(
        row.get("MedienTitel", "-")
    )

    if len(titel) > 60:
        titel = titel[:57] + "..."

    pdf.set_xy(
        x + 3,
        y + 49,
    )

    pdf.set_font(
        "Helvetica",
        "B",
        8,
    )

    pdf.set_text_color(
        34, 40, 46
    )

    pdf.multi_cell(
        width - 6,
        3.6,
        titel,
        align="C",
    )

    # Autor
    autor = _pdf_text(
        row.get("MedienAutor", "-")
    )

    if len(autor) > 38:
        autor = autor[:35] + "..."

    pdf.set_xy(
        x + 3,
        y + 55,
    )

    pdf.set_font(
        "Helvetica",
        "",
        7,
    )

    pdf.set_text_color(
        108, 122, 132
    )

    pdf.cell(
        width - 6,
        4,
        autor,
        align="C",
    )
