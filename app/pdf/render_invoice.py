from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.db.repos.invoice_repo import InvoiceRepository
from app.db.repos.settings_repo import SettingsRepository
from app.domain.money import cents_to_euros


@dataclass(frozen=True)
class PdfResult:
    pdf_path: Path


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

    # Épaisseurs
    table_line_w = 1.0
    header_line_w = 1.5
    c.setLineWidth(table_line_w)

    # =========================
    # EN-TÊTE : logo à gauche + "FACTURE" centré
    # =========================
    header_y = top  # ligne de base du titre

    # Logo à gauche
    logo_path = Path(__file__).resolve().parents[1] / "assets" / "ha_autos_logo.png"
    logo_w = 40 * mm
    logo_h = 40 * mm
    logo_x = left + 5 * mm
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
            pass

    # "FACTURE" centré
    c.setFont("Helvetica-Bold", 16)
    title = "FACTURE"
    title_w = c.stringWidth(title, "Helvetica-Bold", 16)
    c.drawString((page_w - title_w) / 2, header_y - 4 * mm, title)

    # Trait fin sous l'entête
    c.setLineWidth(header_line_w)
    c.line(left, header_y - 10 * mm, right, header_y - 10 * mm)
    c.setLineWidth(table_line_w)

    # =========================
    # BLOC GARAGE (infos visibles) - sous le trait
    # =========================
    garage_top = (header_y - 25 * mm)
    text_x = left + logo_w - 15 * mm

    garage_name = (s.get("garage_name") or "").strip()
    garage_siret = (s.get("garage_siret") or "").strip()
    garage_addr = (s.get("garage_address") or "").strip()
    garage_cp = (s.get("garage_postal_code") or "").strip()
    garage_phone = (s.get("garage_phone") or "").strip()

    # Fallback si rien n'est renseigné en paramètres
    if not any([garage_name, garage_addr, garage_cp, garage_phone, garage_siret]):
        garage_name = "(Paramètres garage non renseignés)"

    y = garage_top

    c.setFont("Helvetica-Bold", 11)
    c.drawString(text_x, y, garage_name)

    c.setFont("Helvetica", 10)

    if garage_siret:
        y -= 5.2 * mm
        c.setFont("Helvetica", 9)
        c.drawString(text_x, y, f"{garage_siret}")
        c.setFont("Helvetica", 10)

    if garage_addr:
        y -= 5.2 * mm
        c.drawString(text_x, y, garage_addr)

    if garage_cp:
        y -= 5.2 * mm
        c.drawString(text_x, y, garage_cp)

    if garage_phone:
        y -= 5.2 * mm
        c.drawString(text_x, y, garage_phone)

    # =========================
    # DATE + N° (ENCADRÉ)
    # =========================
    meta_w = 35 * mm
    meta_h = 18 * mm
    meta_x = right - meta_w
    meta_y = garage_top - 2 * mm - meta_h

    c.rect(meta_x, meta_y, meta_w, meta_h, stroke=1, fill=0)

    inv_date = (getattr(inv, "date", "") or "").replace("-", "/")
    c.setFont("Helvetica", 10)
    c.drawString(meta_x + 4 * mm, meta_y + meta_h - 7 * mm, f"Date : {inv_date}")
    if getattr(inv, "number", ""):
        c.drawString(meta_x + 4 * mm, meta_y + meta_h - 13 * mm, f"N° : {inv.number}")

    # =========================
    # FACTURER À (encadré à droite, sous date)
    # =========================
    bill_w = 66 * mm
    bill_h = 29 * mm
    bill_x = right - bill_w
    bill_y = meta_y - bill_h - 5 * mm

    c.rect(bill_x, bill_y, bill_w, bill_h, stroke=1, fill=0)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(bill_x + 4 * mm, bill_y + bill_h - 7 * mm, "Facturer à :")

    c.setFont("Helvetica", 10)
    y_b = bill_y + bill_h - 13 * mm
    if getattr(inv, "customer_name", ""):
        c.drawString(bill_x + 4 * mm, y_b, inv.customer_name)
        y_b -= 6 * mm
    if getattr(inv, "customer_address", ""):
        c.drawString(bill_x + 4 * mm, y_b, inv.customer_address[:48])
        y_b -= 6 * mm
    cp_c = (getattr(inv, "customer_postal_code", "") or "").strip()
    if cp_c:
        c.drawString(bill_x + 4 * mm, y_b, cp_c)

    # =========================
    # TABLEAU
    # =========================
    table_x = left
    table_y_top = bill_y - 10 * mm
    table_w = right - left

    w_qty = 22 * mm
    w_unit = 35 * mm
    w_total = 30 * mm
    w_desc = table_w - (w_qty + w_unit + w_total)

    x_qty = table_x
    x_desc = x_qty + w_qty
    x_unit = x_desc + w_desc
    x_total = x_unit + w_unit
    x_end = x_total + w_total

    row_h = 7 * mm

    def draw_header(y_top: float) -> float:
        c.rect(table_x, y_top - row_h, table_w, row_h, stroke=1, fill=0)
        c.line(x_desc, y_top - row_h, x_desc, y_top)
        c.line(x_unit, y_top - row_h, x_unit, y_top)
        c.line(x_total, y_top - row_h, x_total, y_top)

        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_qty + 2 * mm, y_top - 5 * mm, "Qté")
        c.drawString(x_desc + 2 * mm, y_top - 5 * mm, "Description")
        c.drawRightString(x_unit + w_unit - 2 * mm, y_top - 5 * mm, "Prix unitaire")
        c.drawRightString(x_end - 2 * mm, y_top - 5 * mm, "Total")
        return y_top - row_h

    def draw_row(y_top: float, qty: str, desc: str, unit: str, total: str) -> float:
        c.rect(table_x, y_top - row_h, table_w, row_h, stroke=1, fill=0)
        c.line(x_desc, y_top - row_h, x_desc, y_top)
        c.line(x_unit, y_top - row_h, x_unit, y_top)
        c.line(x_total, y_top - row_h, x_total, y_top)

        c.setFont("Helvetica", 10)
        c.drawString(x_qty + 2 * mm, y_top - 5 * mm, qty)
        c.drawString(x_desc + 2 * mm, y_top - 5 * mm, (desc or "")[:70])
        c.drawRightString(x_unit + w_unit - 2 * mm, y_top - 5 * mm, unit)
        c.drawRightString(x_end - 2 * mm, y_top - 5 * mm, total)
        return y_top - row_h

    def draw_empty_area(y_top: float, y_bottom: float) -> None:
        # Bordures verticales seulement
        c.line(table_x, y_bottom, table_x, y_top)
        c.line(x_end, y_bottom, x_end, y_top)
        c.line(x_desc, y_bottom, x_desc, y_top)
        c.line(x_unit, y_bottom, x_unit, y_top)
        c.line(x_total, y_bottom, x_total, y_top)

    y = draw_header(table_y_top)

    for ln in lines:
        unit = f"{ln.unit_price_cents/100:.2f} €"
        total = f"{ln.line_total_cents/100:.2f} €"
        y = draw_row(y, str(ln.qty), (ln.description or ""), unit, total)

    RESERVED_UNDER_TABLE = 48 * mm
    table_bottom_limit = bottom + RESERVED_UNDER_TABLE

    empty_bottom = table_bottom_limit
    if y > empty_bottom:
        draw_empty_area(y, empty_bottom)
    c.line(table_x, empty_bottom, x_end, empty_bottom)

    # =========================
    # TOTAUX (encadré complet) - labels proches des valeurs
    # =========================
    after_table_y = empty_bottom - 10 * mm

    # Valeurs à droite
    value_x = x_end - 2 * mm
    # Labels rapprochés 
    label_x = value_x - 20 * mm

    line_step = 6 * mm
    ty = after_table_y

    c.setFont("Helvetica", 10)
    c.drawRightString(label_x, ty, "Sous-total (HT)")
    c.drawRightString(value_x, ty, cents_to_euros(inv.subtotal_cents))
    ty -= line_step

    c.drawRightString(label_x, ty, "TVA (20%)")
    c.drawRightString(value_x, ty, cents_to_euros(inv.vat_cents))
    ty -= line_step

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(label_x, ty, "Total (TTC)")
    c.drawRightString(value_x, ty, cents_to_euros(inv.total_cents))
    ty -= line_step

    # Message
    c.setFont("Helvetica", 10)
    c.drawString(left, bottom, "Merci pour votre confiance.")

    c.save()
    return PdfResult(pdf_path=out_path)
