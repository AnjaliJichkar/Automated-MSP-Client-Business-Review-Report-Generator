"""
Dropsuite section — Backup & Storage.
Slide 1: Section header divider.
Slide 2: 2 donut charts — Mailbox Backup Distribution + OneDrive Backup Distribution.
Slide 3: 4 KPI info cards — OneDrive Backup, SharePoint, Google Drive, Shared Drive.
All colors sourced from cb.BRAND_COLORS / cb.pie_palette (PMS green palette).
"""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.layout_manager as lm
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

SECTION = "Dropsuite"

# KPI card accent colors — 4 visually distinct picks from cb.BRAND_COLORS (PMS green palette)
# Index 0 = #00A550, 5 = #008C40, 2 = #3CB043, 9 = #007030
_CARD_ACCENTS = [
    cb.BRAND_COLORS[0],   # #00A550  deep vivid green  — OneDrive Backup
    cb.BRAND_COLORS[5],   # #008C40  deep forest green — SharePoint
    cb.BRAND_COLORS[2],   # #3CB043  medium vivid      — Google Drive
    cb.BRAND_COLORS[9],   # #007030  dark green        — Shared Drive
]


def _rgb(hex_str: str) -> RGBColor:
    h = hex_str.lstrip('#')
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _fmt_value(v) -> str:
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v) if v is not None else '—'


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "Backup & Storage")

    charts = lm.normalize(data).get('charts', {})

    # ── Slide 2: 2 Donut Charts ───────────────────────────────────────────
    mailbox_dist  = dict(charts.get('mailbox_backup_status_distribution') or {})
    onedrive_dist = dict(charts.get('onedrive_backup_status_distribution') or {})

    def _mailbox_fn(s, l, t, w, h):
        labels = [k.title() for k in mailbox_dist]
        values = list(mailbox_dist.values())
        total  = sum(v for v in values if isinstance(v, (int, float)))
        cb.add_donut_chart(
            s, "Mailbox Backup Distribution",
            labels=labels, values=values,
            colors=cb.pie_palette(len(labels)),
            center_label=f"{total}\nTotal Mailboxes",
            center_value_size=9,
            left_in=l, top_in=t, w_in=w, h_in=h,
        )
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _onedrive_dist_fn(s, l, t, w, h):
        labels = [k.title() for k in onedrive_dist]
        values = list(onedrive_dist.values())
        total  = sum(v for v in values if isinstance(v, (int, float)))
        cb.add_donut_chart(
            s, "OneDrive Backup Distribution",
            labels=labels, values=values,
            colors=cb.pie_palette(len(labels)),
            center_label=f"{total}\nTotal",
            center_value_size=9,
            left_in=l, top_in=t, w_in=w, h_in=h,
        )
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Backup Status Distribution", [
        (lambda: bool(mailbox_dist),  _mailbox_fn,       "Mailbox Backup Distribution"),
        (lambda: bool(onedrive_dist), _onedrive_dist_fn, "OneDrive Backup Distribution"),
    ])

    # ── Slide 3: 4 KPI Info Cards (2×2 grid) ─────────────────────────────
    onedrive_ov   = dict(charts.get('onedrive_backup_storage_overview') or {})
    sharepoint_ov = dict(charts.get('sharepoint_storage_and_capacity_overview') or {})
    google_ov     = dict(charts.get('google_drive_storage_and_capacity_overview') or {})
    shared_ov     = dict(charts.get('shared_drive_storage_and_capacity_overview') or {})

    if onedrive_ov or sharepoint_ov or google_ov or shared_ov:
        slide = sb.new_content_slide(prs, SECTION, "Backup & Storage Overview")

        GAP    = 0.20
        card_w = (lm.CONTENT_W_IN - GAP) / 2
        card_h = (lm.CHART2_H_IN  - GAP) / 2
        L1, L2 = lm.CONTENT_LEFT_IN, lm.CONTENT_LEFT_IN + card_w + GAP
        T1, T2 = lm.CHART2_TOP_IN,   lm.CHART2_TOP_IN + card_h + GAP

        if onedrive_ov:
            _draw_kpi_list_card(slide, "OneDrive Backup",
                                _onedrive_items(onedrive_ov),
                                L1, T1, card_w, card_h, accent=_CARD_ACCENTS[0])
            cb.add_live_badge(slide, L1 + card_w - 0.65, T1 + 0.05)

        if sharepoint_ov:
            _draw_kpi_list_card(slide, "SharePoint Overview",
                                _sharepoint_items(sharepoint_ov),
                                L2, T1, card_w, card_h, accent=_CARD_ACCENTS[1])
            cb.add_live_badge(slide, L2 + card_w - 0.65, T1 + 0.05)

        if google_ov:
            _draw_kpi_list_card(slide, "Google Drive Overview",
                                _google_drive_items(google_ov),
                                L1, T2, card_w, card_h, accent=_CARD_ACCENTS[2])
            cb.add_live_badge(slide, L1 + card_w - 0.65, T2 + 0.05)

        if shared_ov:
            _draw_kpi_list_card(slide, "Shared Drive Overview",
                                _shared_drive_items(shared_ov),
                                L2, T2, card_w, card_h, accent=_CARD_ACCENTS[3])
            cb.add_live_badge(slide, L2 + card_w - 0.65, T2 + 0.05)


# ── KPI item builders ──────────────────────────────────────────────────

def _onedrive_items(d: dict) -> list:
    mapping = [
        ('total_accounts', 'Total Accounts'),
        ('total_storage',  'Total Storage'),
        ('activated',      'Activated'),
        ('deactivated',    'Deactivated'),
    ]
    return [(lbl, _fmt_value(d.get(k)))
            for k, lbl in mapping if d.get(k) is not None]


def _sharepoint_items(d: dict) -> list:
    mapping = [
        ('domain_count',     'Domain Count'),
        ('total_site_count', 'Total Sites'),
        ('total_file_count', 'Total Files'),
        ('total_storage',    'Total Storage'),
    ]
    return [(lbl, _fmt_value(d.get(k)))
            for k, lbl in mapping if d.get(k) is not None]


def _google_drive_items(d: dict) -> list:
    mapping = [
        ('drive_count',      'Drive Count'),
        ('total_file_count', 'Total Files'),
        ('total_storage',    'Total Storage'),
    ]
    return [(lbl, _fmt_value(d.get(k)))
            for k, lbl in mapping if d.get(k) is not None]


def _shared_drive_items(d: dict) -> list:
    mapping = [
        ('domain_count',     'Domain Count'),
        ('total_file_count', 'Total Files'),
        ('total_storage',    'Total Storage'),
    ]
    return [(lbl, _fmt_value(d.get(k)))
            for k, lbl in mapping if d.get(k) is not None]


# ── KPI List Card renderer ─────────────────────────────────────────────

def _draw_kpi_list_card(slide, title: str, items: list,
                        left_in, top_in, w_in, h_in,
                        accent: str = '#00A550'):
    """
    KPI info card: white rounded rect + accent left bar + bold title + label/value rows.
    items: list of (label_str, value_str) tuples — fully dynamic, no hardcoding.
    accent: hex color from cb.BRAND_COLORS — used for left bar and label text.
    """
    PAD     = 0.18
    TITLE_H = 0.28

    # ── Card background ───────────────────────────────────────────────────
    card = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        Inches(left_in), Inches(top_in),
        Inches(w_in),    Inches(h_in)
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    card.line.color.rgb      = RGBColor(0xE2, 0xE8, 0xF0)
    card.line.width          = Pt(0.75)

    # ── Accent left-edge bar (PMS green color) ────────────────────────────
    bar = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(left_in), Inches(top_in),
        Inches(0.055),   Inches(h_in)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = _rgb(accent)
    bar.line.fill.background()

    # ── Title ─────────────────────────────────────────────────────────────
    text_left = left_in + 0.055 + PAD
    text_w    = w_in - 0.055 - PAD * 2

    tb_title = slide.shapes.add_textbox(
        Inches(text_left), Inches(top_in + 0.10),
        Inches(text_w),    Inches(TITLE_H)
    )
    tf = tb_title.text_frame
    tf.word_wrap = False
    p  = tf.paragraphs[0]
    r  = p.add_run()
    r.text           = title
    r.font.bold      = True
    r.font.size      = Pt(10)
    r.font.name      = lm.FONT_NAME
    r.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

    # ── Divider ───────────────────────────────────────────────────────────
    div_top = top_in + 0.10 + TITLE_H + 0.04
    div = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(left_in + 0.055 + PAD * 0.5), Inches(div_top),
        Inches(text_w + PAD),                Inches(0.012)
    )
    div.fill.solid()
    div.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
    div.line.fill.background()

    if not items:
        return

    # ── Row layout ────────────────────────────────────────────────────────
    rows_top = div_top + 0.06
    avail_h  = h_in - (rows_top - top_in) - 0.10
    row_h    = min(avail_h / len(items), 0.36)

    VAL_COL_W = w_in * 0.38

    for i, (label, value) in enumerate(items):
        ry = rows_top + i * row_h

        # Label — left, PMS green accent color
        tb_lbl = slide.shapes.add_textbox(
            Inches(text_left),          Inches(ry),
            Inches(text_w - VAL_COL_W), Inches(row_h)
        )
        tb_lbl.text_frame.word_wrap = False
        lp = tb_lbl.text_frame.paragraphs[0]
        lp.alignment = PP_ALIGN.LEFT
        lr = lp.add_run()
        lr.text           = label
        lr.font.size      = Pt(8.5)
        lr.font.name      = lm.FONT_NAME
        lr.font.color.rgb = _rgb(accent)

        # Value — right, dark bold
        val_left = left_in + w_in - PAD - VAL_COL_W
        tb_val = slide.shapes.add_textbox(
            Inches(val_left), Inches(ry),
            Inches(VAL_COL_W + PAD - 0.05), Inches(row_h)
        )
        tb_val.text_frame.word_wrap = False
        vp = tb_val.text_frame.paragraphs[0]
        vp.alignment = PP_ALIGN.RIGHT
        vr = vp.add_run()
        vr.text           = str(value)
        vr.font.size      = Pt(8.5)
        vr.font.bold      = True
        vr.font.name      = lm.FONT_NAME
        vr.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)