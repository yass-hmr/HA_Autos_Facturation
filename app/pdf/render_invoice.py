from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.db.repos.invoice_repo import InvoiceRepository
from app.db.repos.settings_repo import SettingsRepository
from app.domain.money import cents_to_euros
from app.utils.dates import iso_to_fr


@dataclass(frozen=True)
class PdfResult:
    pdf_path: Path


def _t(v) -> str:
    """Force une valeur en texte (évite le crash reportlab sur objets inattendus)."""
    if v is None:
        return ""
    # Protection anti-erreur: quelqu’un a mis {"texte"} => set
    if isinstance(v, set):
        if len(v) == 1:
            return str(next(iter(v)))
        return " ".join(str(x) for x in v)
    return str(v)


def _wrap_n_chars(text: str, n: int) -> List[str]:
    text = _t(text).strip()
    if not text:
        return [""]
    if len(text) <= n:
        return [text]
    return [text[i : i + n] for i in range(0, len(text), n)]


def render_invoice_pdf(
    *,
    conn: sqlite3.Connection,
    invoice_id: int,
    out_path: Path,
) -> PdfResult:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    settings_repo = SettingsRepository(conn)
    invoice_repo = InvoiceRepository(conn)

    s = settings_repo.get()
    inv = invoice_repo.get_header(invoice_id)
    lines = invoice_repo.get_lines(invoice_id)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    page_w, page_h = A4

    # Marges
    left = 20 * mm
    right = page_w - 20 * mm
    top = page_h - 20 * mm
    bottom = 20 * mm

    # Styles
    table_line_w = 1.0
    header_line_w = 1.5
    c.setLineWidth(table_line_w)

    # =========================
    # EN-TÊTE : logo à gauche + "FACTURE" centré
    # =========================
    header_y = top

    logo_path = Path(__file__).resolve().parents[1] / "assets" / "ha_autos_logo.png"
    logo_w = 40 * mm
    logo_h = 40 * mm
    logo_x = left
    logo_y = header_y - logo_h + 23 * mm

    if logo_path.exists():
        try:
            c.drawImage(
                ImageReader(str(logo_path)),
                logo_x,
                logo_y,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            # on ignore l’image si souci
            pass

    c.setFont("Helvetica-Bold", 16)
    title = "FACTURE"
    title_w = c.stringWidth(title, "Helvetica-Bold", 16)
    c.drawString((page_w - title_w) / 2, header_y - 4 * mm, title)

    c.setLineWidth(header_line_w)
    c.line(left, header_y - 10 * mm, right, header_y - 10 * mm)
    c.setLineWidth(table_line_w)

    # =========================
    # BLOC GARAGE (VISIBLE, à gauche sous l'entête)
    # =========================
    garage_top = header_y - 30 * mm
    text_x = left + (logo_w - 20 * mm) if logo_path.exists() else left
    y = garage_top

    garage_name = _t(s.get("garage_name")).strip()
    garage_addr = _t(s.get("garage_address")).strip()
    garage_cp = _t(s.get("garage_postal_code")).strip()
    garage_phone = _t(s.get("garage_phone")).strip()
    garage_email = _t(s.get("garage_email")).strip()
    garage_siret = _t(s.get("garage_siret")).strip()

    c.setFont("Helvetica-Bold", 11)
    if garage_name:
        c.drawString(text_x, y, garage_name)
        y -= 5.5 * mm

    c.setFont("Helvetica", 10)
    if garage_addr:
        c.drawString(text_x, y, garage_addr)
        y -= 5.5 * mm
    if garage_cp:
        c.drawString(text_x, y, garage_cp)
        y -= 5.5 * mm
    if garage_phone:
        c.drawString(text_x, y, garage_phone)
        y -= 5.5 * mm
    if garage_email:
        c.drawString(text_x, y, garage_email)
        y -= 5.5 * mm
    if garage_siret:
        c.setFont("Helvetica", 9)
        c.drawString(text_x, y, f"{garage_siret}")
        c.setFont("Helvetica", 10)

    # =========================
    # DATE + N° (ENCADRÉ à droite)
    # =========================
    meta_w = 42 * mm
    meta_h = 18 * mm
    meta_x = right - meta_w
    meta_y = garage_top - 2 * mm - meta_h

    c.rect(meta_x, meta_y, meta_w, meta_h, stroke=1, fill=0)

    inv_date = iso_to_fr(_t(getattr(inv, "date", "")))
    inv_number = _t(getattr(inv, "number", "")).strip()

    c.setFont("Helvetica", 10)
    c.drawString(meta_x + 4 * mm, meta_y + meta_h - 7 * mm, f"Date : {inv_date}")
    if inv_number:
        c.drawString(meta_x + 4 * mm, meta_y + meta_h - 13 * mm, f"N° : {inv_number}")

    # =========================
    # FACTURER À (encadré à droite, sous date)
    # =========================
    bill_w = 60 * mm
    bill_h = 46 * mm
    bill_x = right - bill_w
    bill_y = meta_y - bill_h - 5 * mm

    c.rect(bill_x, bill_y, bill_w, bill_h, stroke=1, fill=0)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(bill_x + 4 * mm, bill_y + bill_h - 7 * mm, "Facturer à :")

    c.setFont("Helvetica", 10)
    y_b = bill_y + bill_h - 13 * mm

    customer_name = _t(getattr(inv, "customer_name", "")).strip()
    customer_addr = _t(getattr(inv, "customer_address", "")).strip()
    customer_cp = _t(getattr(inv, "customer_postal_code", "")).strip()
    customer_phone = _t(getattr(inv, "customer_phone", "")).strip()
    customer_email = _t(getattr(inv, "customer_email", "")).strip()

    if customer_name:
        c.drawString(bill_x + 4 * mm, y_b, customer_name[:40])
        y_b -= 6 * mm
    if customer_addr:
        c.drawString(bill_x + 4 * mm, y_b, customer_addr[:40])
        y_b -= 6 * mm
    if customer_cp:
        c.drawString(bill_x + 4 * mm, y_b, customer_cp[:40])
        y_b -= 6 * mm
    if customer_phone:
        c.drawString(bill_x + 4 * mm, y_b, customer_phone[:40])
        y_b -= 6 * mm
    if customer_email:
        c.drawString(bill_x + 4 * mm, y_b, customer_email[:40])

    # =========================
    # TABLEAU (avec Référence)
    # =========================
    table_x = left
    table_y_top = bill_y - 15 * mm
    table_w = right - left

    w_qty = 18 * mm
    w_ref = 28 * mm
    w_unit = 30 * mm
    w_total = 28 * mm
    w_desc = table_w - (w_qty + w_ref + w_unit + w_total)

    x_qty = table_x
    x_ref = x_qty + w_qty
    x_desc = x_ref + w_ref
    x_unit = x_desc + w_desc
    x_total = x_unit + w_unit
    x_end = x_total + w_total

    row_h = 7 * mm

    def draw_header(y_top: float) -> float:
        c.rect(table_x, y_top - row_h, table_w, row_h, stroke=1, fill=0)
        c.line(x_ref, y_top - row_h, x_ref, y_top)
        c.line(x_desc, y_top - row_h, x_desc, y_top)
        c.line(x_unit, y_top - row_h, x_unit, y_top)
        c.line(x_total, y_top - row_h, x_total, y_top)

        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_qty + 2 * mm, y_top - 5 * mm, "Qté")
        c.drawString(x_ref + 2 * mm, y_top - 5 * mm, "Référence")
        c.drawString(x_desc + 2 * mm, y_top - 5 * mm, "Description")
        c.drawRightString(x_unit + w_unit - 2 * mm, y_top - 5 * mm, "Prix unitaire")
        c.drawRightString(x_end - 2 * mm, y_top - 5 * mm, "Total")
        return y_top - row_h

    def draw_row(y_top: float, qty: str, ref: str, desc: str, unit: str, total: str) -> float:
        # wrap référence/description
        ref_lines = _wrap_n_chars(ref, 14)
        desc_lines = _wrap_n_chars(desc, 36)
        nb = max(len(ref_lines), len(desc_lines), 1)
        h = max(row_h, (nb * 4.5 * mm) + 2 * mm)

        c.rect(table_x, y_top - h, table_w, h, stroke=1, fill=0)
        c.line(x_ref, y_top - h, x_ref, y_top)
        c.line(x_desc, y_top - h, x_desc, y_top)
        c.line(x_unit, y_top - h, x_unit, y_top)
        c.line(x_total, y_top - h, x_total, y_top)

        c.setFont("Helvetica", 10)
        c.drawString(x_qty + 2 * mm, y_top - 5 * mm, _t(qty))

        # Référence + Description sur plusieurs lignes
        c.setFont("Helvetica", 9)
        ty = y_top - 5 * mm
        for i in range(nb):
            if i < len(ref_lines) and ref_lines[i]:
                c.drawString(x_ref + 2 * mm, ty, ref_lines[i])
            if i < len(desc_lines) and desc_lines[i]:
                c.drawString(x_desc + 2 * mm, ty, desc_lines[i])
            ty -= 4.5 * mm

        c.setFont("Helvetica", 10)
        c.drawRightString(x_unit + w_unit - 2 * mm, y_top - 5 * mm, _t(unit))
        c.drawRightString(x_end - 2 * mm, y_top - 5 * mm, _t(total))

        return y_top - h

    def draw_empty_area(y_top: float, y_bottom: float) -> None:
        # Zone vide = uniquement verticales, pas d'horizontales internes
        c.line(table_x, y_bottom, table_x, y_top)
        c.line(x_end, y_bottom, x_end, y_top)
        c.line(x_ref, y_bottom, x_ref, y_top)
        c.line(x_desc, y_bottom, x_desc, y_top)
        c.line(x_unit, y_bottom, x_unit, y_top)
        c.line(x_total, y_bottom, x_total, y_top)

    y = draw_header(table_y_top)

    for ln in lines:
        qty = _t(getattr(ln, "qty", ""))
        ref = _t(getattr(ln, "reference", ""))
        desc = _t(getattr(ln, "description", ""))
        unit = f"{getattr(ln, 'unit_price_cents', 0)/100:.2f} €"
        total = f"{getattr(ln, 'line_total_cents', 0)/100:.2f} €"
        y = draw_row(y, qty, ref, desc, unit, total)

    # Réserver de la place sous le tableau (totaux + message)
    RESERVED_UNDER_TABLE = 48 * mm
    table_bottom_limit = bottom + RESERVED_UNDER_TABLE

    empty_bottom = table_bottom_limit
    if y > empty_bottom:
        draw_empty_area(y, empty_bottom)

    # Ligne horizontale finale (bas du tableau)
    c.line(table_x, empty_bottom, x_end, empty_bottom)

    # =========================
    # TOTAUX sous le tableau
    # =========================
    after_table_y = empty_bottom - 10 * mm

    value_x = x_end - 2 * mm
    label_x = value_x - 20 * mm  # rapproché

    line_step = 6 * mm
    ty = after_table_y

    c.setFont("Helvetica", 10)
    c.drawRightString(label_x, ty, "Sous-total (HT)")
    c.drawRightString(value_x, ty, cents_to_euros(getattr(inv, "subtotal_cents", 0)))
    ty -= line_step

    c.drawRightString(label_x, ty, "TVA (20%)")
    c.drawRightString(value_x, ty, cents_to_euros(getattr(inv, "vat_cents", 0)))
    ty -= line_step

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(label_x, ty, "Total (TTC)")
    c.drawRightString(value_x, ty, cents_to_euros(getattr(inv, "total_cents", 0)))
    ty -= line_step

    # =========================
    # Message
    # =========================
    c.setFont("Helvetica", 10)
    c.drawString(left, bottom, "Merci pour votre confiance.")

    c.save()
    return PdfResult(pdf_path=out_path)
