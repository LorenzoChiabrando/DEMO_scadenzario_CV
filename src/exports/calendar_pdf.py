from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)


class CalendarPdfError(RuntimeError):
    """Errore durante la creazione del PDF."""


@dataclass(frozen=True, slots=True)
class CalendarPdfRow:
    """Riga del calendario da stampare."""

    label: str
    values: tuple[str, ...]
    background: str = "#ffffff"


@dataclass(frozen=True, slots=True)
class CalendarPdfDocument:
    """Dati necessari per creare il calendario PDF."""

    title: str
    period: str
    column_headers: tuple[str, ...]
    rows: tuple[CalendarPdfRow, ...]
    legend: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.period.strip():
            raise ValueError("PDF title and period are required")
        if not self.column_headers:
            raise ValueError("the PDF requires at least one calendar column")
        expected = len(self.column_headers)
        if any(len(row.values) != expected for row in self.rows):
            raise ValueError("every PDF row must match the number of columns")


def _safe_text(value: object) -> str:
    return str(value or "").replace("–", "-").replace("—", "-")


def _draw_cell_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    *,
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
) -> None:
    metrics = QFontMetrics(painter.font())
    horizontal_padding = 8
    available_width = max(1, int(rect.width()) - horizontal_padding)
    elided = metrics.elidedText(_safe_text(text), Qt.TextElideMode.ElideRight, available_width)
    painter.drawText(rect.adjusted(4, 2, -4, -2), alignment, elided)


def write_calendar_pdf(path: str | Path, document: CalendarPdfDocument) -> Path:
    """Crea il PDF e restituisce il percorso del file."""

    output_path = Path(path)
    if output_path.suffix.casefold() != ".pdf":
        output_path = output_path.with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = QPdfWriter(str(output_path))
    writer.setResolution(144)
    page_size = (
        QPageSize.PageSizeId.A3 if len(document.column_headers) > 10 else QPageSize.PageSizeId.A4
    )
    writer.setPageSize(QPageSize(page_size))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
    writer.setTitle(_safe_text(document.title))
    writer.setCreator("MMSD CV")

    painter = QPainter(writer)
    if not painter.isActive():
        raise CalendarPdfError(f"Impossibile creare il PDF in {output_path}")

    try:
        page = writer.pageLayout().paintRectPixels(writer.resolution())
        left = float(page.left())
        top = float(page.top())
        width = float(page.width())
        height = float(page.height())

        painter.fillRect(QRectF(left, top, width, height), QColor("#ffffff"))
        painter.setPen(QColor("#1e293b"))
        painter.setFont(QFont("Helvetica", 18, QFont.Weight.Bold))
        painter.drawText(
            QRectF(left, top, width, 44),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _safe_text(document.title),
        )
        painter.setFont(QFont("Helvetica", 10, QFont.Weight.Normal))
        painter.setPen(QColor("#475569"))
        painter.drawText(
            QRectF(left, top + 42, width, 28),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _safe_text(document.period),
        )

        table_top = top + 78
        legend_height = 0
        if document.legend:
            legend_lines = (len(document.legend) + 2) // 3
            legend_height = 28 + legend_lines * 22
        table_height = height - (table_top - top) - legend_height - 18
        header_height = 38.0
        row_height = min(
            82.0,
            max(30.0, (table_height - header_height) / max(1, len(document.rows))),
        )
        label_width = max(126.0, width * 0.12)
        value_width = (width - label_width) / len(document.column_headers)

        border_pen = QPen(QColor("#cbd5e1"))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.setFont(QFont("Helvetica", 8, QFont.Weight.Bold))

        corner_rect = QRectF(left, table_top, label_width, header_height)
        painter.fillRect(corner_rect, QColor("#e2e8f0"))
        painter.setPen(border_pen)
        painter.drawRect(corner_rect)
        painter.setPen(QColor("#1e293b"))
        _draw_cell_text(painter, corner_rect, "Attività")

        for column, header in enumerate(document.column_headers):
            rect = QRectF(
                left + label_width + column * value_width,
                table_top,
                value_width,
                header_height,
            )
            painter.fillRect(rect, QColor("#e2e8f0"))
            painter.setPen(border_pen)
            painter.drawRect(rect)
            painter.setPen(QColor("#1e293b"))
            _draw_cell_text(painter, rect, header)

        for row_index, row in enumerate(document.rows):
            y = table_top + header_height + row_index * row_height
            label_rect = QRectF(left, y, label_width, row_height)
            painter.fillRect(label_rect, QColor(row.background))
            painter.setPen(border_pen)
            painter.drawRect(label_rect)
            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Helvetica", 7, QFont.Weight.Bold))
            _draw_cell_text(
                painter,
                label_rect,
                row.label,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            painter.setFont(QFont("Helvetica", 7, QFont.Weight.Normal))
            for column, value in enumerate(row.values):
                rect = QRectF(
                    left + label_width + column * value_width,
                    y,
                    value_width,
                    row_height,
                )
                painter.fillRect(rect, QColor(row.background))
                painter.setPen(border_pen)
                painter.drawRect(rect)
                painter.setPen(QColor("#1e293b"))
                _draw_cell_text(painter, rect, value)

        if document.legend:
            legend_top = table_top + header_height + len(document.rows) * row_height + 14
            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Helvetica", 8, QFont.Weight.Bold))
            painter.drawText(
                QRectF(left, legend_top, width, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Legenda specializzandi",
            )
            painter.setFont(QFont("Helvetica", 7, QFont.Weight.Normal))
            legend_column_width = width / 3
            for index, (initials, full_name) in enumerate(document.legend):
                legend_column = index % 3
                legend_row = index // 3
                rect = QRectF(
                    left + legend_column * legend_column_width,
                    legend_top + 22 + legend_row * 22,
                    legend_column_width,
                    20,
                )
                _draw_cell_text(
                    painter,
                    rect,
                    f"{initials} = {full_name}",
                    alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                )
    finally:
        painter.end()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise CalendarPdfError(f"Il PDF non è stato scritto in {output_path}")
    return output_path
