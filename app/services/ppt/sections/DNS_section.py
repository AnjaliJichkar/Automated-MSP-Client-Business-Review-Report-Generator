"""
DNSFilter section — DNS Security & Filtering.
Slide 1: Section heading divider.
Slide 2: All Counts — KPI stat cards (total_threats_count, total_blocked_requests) + info note.
"""
import app.services.ppt.slide_builder as sb
import app.services.ppt.chart_builder as cb
import app.services.ppt.layout_manager as lm
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE


_SECTION      = "DNSFilter"
_NOTE_TOP     = 4.25   # info-note top for chart slides (58-60)
_KPI_NOTE_TOP = 2.68   # slide 57 — moved up 4 cm from default (4.25 - 4/2.54)

_INFO_TEXT = (
    "DNSFilter data is limited to the last 60 days. "
    "Months older than 60 days will display the last month’s data. "
    "Quarterly reports always show the last month’s data."
)

def _draw_quarterly_progress_cards(slide, title: str, allowed_dict: dict, blocked_dict: dict,
                                   is_threats: bool, left_in: float, top_in: float, w_in: float, h_in: float):
    """
    Draws custom UI progress bar cards for each month exactly matching the screenshot.
    """
    # 1. Section Title
    cb._add_section_title(slide, title, left_in, top_in, w_in)
    title_h = 0.38
    content_top = top_in + title_h
    content_h = h_in - title_h

    # 2. Color mapping matching screenshot exactly
    if is_threats:
        # Threats: Allowed = Red (Bad), Blocked = Green (Good)
        clr_allowed = RGBColor(0xDC, 0x26, 0x26)  # #DC2626 Red
        clr_blocked = RGBColor(0x16, 0xA3, 0x4A)  # #16A34A Green
    else:
        # Requests: Allowed = Green (Good), Blocked = Red (Bad)
        clr_allowed = RGBColor(0x16, 0xA3, 0x4A)  # #16A34A Green
        clr_blocked = RGBColor(0xDC, 0x26, 0x26)  # #DC2626 Red

    months = list(allowed_dict.keys())
    if not months:
        # No monthly data — show a light centered message instead of
        # leaving this area completely blank (and instead of the old
        # grey placeholder box).
        msg = slide.shapes.add_textbox(
            Inches(left_in), Inches(content_top + content_h / 2 - 0.15),
            Inches(w_in), Inches(0.3)
        )
        mp = msg.text_frame.paragraphs[0]
        mp.alignment = PP_ALIGN.CENTER
        mr = mp.add_run()
        mr.text = "No data for this period"
        mr.font.size = Pt(10)
        mr.font.name = lm.FONT_NAME
        mr.font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)
        return

    block_h = content_h / len(months)
    bar_w = w_in - 0.3
    bar_x = left_in + 0.15

    for i, month in enumerate(months):
        m_top = content_top + i * block_h
        
        val_a = int(allowed_dict.get(month, 0))
        val_b = int(blocked_dict.get(month, 0))
        total = val_a + val_b
        pct_a = (val_a / total * 100) if total > 0 else 0.0
        pct_b = (val_b / total * 100) if total > 0 else 0.0

        # ── Top Text Row (Month | Allowed | Blocked | Total) ──────────────
        tb_top = slide.shapes.add_textbox(Inches(bar_x), Inches(m_top + 0.02), Inches(bar_w), Inches(0.28))
        p = tb_top.text_frame.paragraphs[0]
        
        r_m = p.add_run()
        r_m.text = f"{str(month).capitalize()}   "
        r_m.font.bold = True
        r_m.font.size = Pt(11)
        r_m.font.name = lm.FONT_NAME
        r_m.font.color.rgb = lm.CLR_DARK

        r_a = p.add_run()
        # Always show a checkmark for the allowed count; color indicates good/bad.
        r_a.text = f"✔ {val_a:,}   "
        r_a.font.bold = True
        r_a.font.size = Pt(10)
        r_a.font.name = lm.FONT_NAME
        r_a.font.color.rgb = clr_allowed

        r_b = p.add_run()
        r_b.text = f"🚫 {val_b:,}   "
        r_b.font.bold = True
        r_b.font.size = Pt(10)
        r_b.font.name = lm.FONT_NAME
        r_b.font.color.rgb = clr_blocked

        r_t = p.add_run()
        r_t.text = f"Total: {total:,}"
        r_t.font.size = Pt(9.5)
        r_t.font.name = lm.FONT_NAME
        r_t.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

        # ── Middle Progress Bar Shape (Pill style) ────────────────────────
        bar_y = m_top + 0.32
        bar_h = min(block_h * 0.20, 0.15)

        # Full background pill (represents 100% width in secondary color)
        bg_pill = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            Inches(bar_x), Inches(bar_y), Inches(bar_w), Inches(bar_h)
        )
        bg_pill.fill.solid()
        bg_pill.fill.fore_color.rgb = clr_blocked
        bg_pill.line.fill.background()
        cb._set_shape_adj(bg_pill, 50000)  # Pill rounding

        # Primary color overlay pill proportional to allowed ratio
        w_a = bar_w * (pct_a / 100.0)
        bar_pieces = [bg_pill]
        if w_a > 0.05:
            fg_pill = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
                Inches(bar_x), Inches(bar_y), Inches(w_a), Inches(bar_h)
            )
            fg_pill.fill.solid()
            fg_pill.fill.fore_color.rgb = clr_allowed
            fg_pill.line.fill.background()
            cb._set_shape_adj(fg_pill, 50000)
            bar_pieces.append(fg_pill)

        # Lock the overlay pieces together as a single group so the bar can
        # never be accidentally dragged apart in PowerPoint (this was the
        # cause of the "dismantled" bars — the pieces were previously left
        # as independent, unlinked shapes).
        if len(bar_pieces) > 1:
            bar_group = slide.shapes.add_group_shape(bar_pieces)
            bar_group.name = f"progress_bar_{'threats' if is_threats else 'requests'}_{str(month).lower()}"

        # ── Bottom Percentage Labels Row ──────────────────────────────────
        # Left label: "% allowed"
        tb_bot_l = slide.shapes.add_textbox(Inches(bar_x), Inches(bar_y + bar_h + 0.02), Inches(bar_w / 2), Inches(0.22))
        p_bl = tb_bot_l.text_frame.paragraphs[0]
        r_bl = p_bl.add_run()
        r_bl.text = f"{pct_a:.1f}% allowed"
        r_bl.font.size = Pt(8)
        r_bl.font.name = lm.FONT_NAME
        r_bl.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

        # Right label: "% blocked"
        tb_bot_r = slide.shapes.add_textbox(Inches(bar_x + bar_w / 2), Inches(bar_y + bar_h + 0.02), Inches(bar_w / 2), Inches(0.22))
        p_br = tb_bot_r.text_frame.paragraphs[0]
        p_br.alignment = PP_ALIGN.RIGHT
        r_br = p_br.add_run()
        r_br.text = f"{pct_b:.1f}% blocked"
        r_br.font.size = Pt(8)
        r_br.font.name = lm.FONT_NAME
        r_br.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

def build_slides(prs, data):
    charts = lm.normalize(data).get("charts", {})

    # Slide 1 — section divider
    sb.add_section_slide(prs, _SECTION, "AI-powered content filtering & threat blocking")

    req_counts    = charts.get("request_counts", {})
    quaterly_data = charts.get("quaterly_data", {})
    monthly_data  = charts.get("monthly_data", {})

    if quaterly_data and any(k in quaterly_data for k in ["threats_over_months", "allowed_vs_blocked_request_quarterly"]):
        # ── CONSOLIDATED 2-SLIDE QUARTERLY LAYOUT ────────────────────────
        _build_quarterly_slide_1(prs, req_counts, quaterly_data.get("threats_over_months", {}))
        _build_quarterly_slide_2(prs, quaterly_data.get("allowed_vs_blocked_request_quarterly", {}), quaterly_data.get("allowed_vs_blocked_threats_quarterly", {}))
    else:
        # ── ORIGINAL MONTHLY LAYOUT (Pulling from monthly_data) ──────────
        if req_counts:
            _build_all_counts_slide(prs, req_counts)
        _build_threats_over_time_slide(prs, monthly_data.get("threats_over_time", {}))
        _build_allowed_vs_blocked_requests_slide(prs, monthly_data.get("allowed_vs_blocked_request", []))
        _build_allowed_vs_blocked_threats_slide(prs, monthly_data.get("allowed_vs_blocked_threats", []))

# ── Slide builders ────────────────────────────────────────────────────

def _build_all_counts_slide(prs, rc):
    slide = sb.new_content_slide(prs, _SECTION, "All Counts")

    total_threats = rc.get("total_threats_count", 0)
    total_blocked = rc.get("total_blocked_requests", 0)

    cards = [
        {
            "label":    "Total Threats",
            "value":    f"{total_threats:,}",
            "color":    cb.CLR_BLUE,    # #00A550 — brand primary green
            "bg_color": "#E0F5EA",
        },
        {
            "label":    "Total Blocked Requests",
            "value":    f"{total_blocked:,}",
            "color":    cb.CLR_GREEN,   # #74C045 — brand secondary green
            "bg_color": "#F0F8E6",
        },
    ]

    # KPI stat cards — occupy upper portion, leave room at bottom for info note
    cb.add_stat_cards(
        slide,
        title="All Counts",
        cards=cards,
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=2.0,
        value_font_size=18,
    )


# ── Shared helper ─────────────────────────────────────────────────────

def _add_info_note(slide, text, left_in, top_in, w_in):
    """
    Renders a light-blue info strip: [i] circle on the left, description text on the right.
    Used as a data-disclaimer note at the bottom of KPI slides.
    """
    NOTE_H    = 0.40
    ICON_SIZE = 0.25
    ICON_GAP  = 0.10
    BG_CLR    = RGBColor(0xE0, 0xF5, 0xEA)   # light green tint
    ICON_CLR  = RGBColor(0x00, 0xA5, 0x50)   # brand primary green #00A550
    BORD_CLR  = RGBColor(0xA0, 0xD8, 0xB0)   # light green border
    TEXT_CLR  = RGBColor(0x37, 0x40, 0x50)   # body dark

    # ── background strip ──────────────────────────────────────────────
    bg = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        Inches(left_in), Inches(top_in),
        Inches(w_in), Inches(NOTE_H),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG_CLR
    bg.line.color.rgb = BORD_CLR

    # ── info icon circle ──────────────────────────────────────────────
    icon_top  = top_in + (NOTE_H - ICON_SIZE) / 2
    icon_left = left_in + 0.15
    circ = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.OVAL,
        Inches(icon_left), Inches(icon_top),
        Inches(ICON_SIZE), Inches(ICON_SIZE),
    )
    circ.fill.solid()
    circ.fill.fore_color.rgb = ICON_CLR
    circ.line.fill.background()

    ctf = circ.text_frame
    ctf.word_wrap = False
    ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
    cp = ctf.paragraphs[0]
    cp.alignment = PP_ALIGN.CENTER
    cr = cp.add_run()
    cr.text = "i"
    cr.font.bold = True
    cr.font.size = Pt(9)
    cr.font.name = lm.FONT_NAME
    cr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # ── description text ──────────────────────────────────────────────
    txt_left = icon_left + ICON_SIZE + ICON_GAP
    txt_w    = w_in - (txt_left - left_in) - 0.15
    tb = slide.shapes.add_textbox(
        Inches(txt_left), Inches(top_in + 0.05),
        Inches(txt_w), Inches(NOTE_H - 0.05),
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = text
    run.font.name = lm.FONT_NAME
    run.font.size = Pt(8)
    run.font.color.rgb = TEXT_CLR


# ── Slide 3: Daily Threats Over Time ─────────────────────────────────

def _build_threats_over_time_slide(prs, tot):
    """Area-fill line chart: daily threat count over the month."""
    if not tot:
        return
    slide = sb.new_content_slide(prs, _SECTION, "Daily Threats Over Time")

    dates  = sorted(tot.keys())
    values = [tot[d] for d in dates]

    cb.add_area_line_chart(
        slide, "Daily Threats Over Time",
        dates, values,
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.7874,  # increased by 2 cm (≈0.7874 in)
    )


# ── Slides 4–5: Dual-axis Allowed vs Blocked ─────────────────────────

def _build_allowed_vs_blocked_requests_slide(prs, data):
    """Bar (Allowed, left) + Line (Blocked, right) — request volumes."""
    if not data:
        return
    slide  = sb.new_content_slide(prs, _SECTION, "Allowed vs Blocked Requests")
    dates   = [row.get("date", "")    for row in data]
    allowed = [row.get("allowed", 0)  for row in data]
    blocked = [row.get("blocked", 0)  for row in data]

    cb.add_dual_axis_bar_line_chart(
        slide, "Allowed vs Blocked Requests",
        dates,
        bar_values=allowed,  bar_label="Allowed",  bar_color=cb.CLR_BLUE,
        line_values=blocked, line_label="Blocked",  line_color=cb.CLR_YELLOW,
        bar_axis_title="Allowed Requests",
        line_axis_title="Blocked Requests",
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.7874,  # increased by 2 cm (≈0.7874 in)
    )


def _build_allowed_vs_blocked_threats_slide(prs, data):
    """Bar (Blocked, left) + Line (Allowed, right) — threat breakdown."""
    if not data:
        return
    slide   = sb.new_content_slide(prs, _SECTION, "Allowed vs Blocked Threats")
    dates   = [row.get("date", "")    for row in data]
    blocked = [row.get("blocked", 0)  for row in data]
    allowed = [row.get("allowed", 0)  for row in data]

    cb.add_dual_axis_bar_line_chart(
        slide, "Allowed vs Blocked Threats",
        dates,
        bar_values=blocked,  bar_label="Blocked",  bar_color=cb.CLR_GREEN,
        line_values=allowed, line_label="Allowed",  line_color=cb.CLR_YELLOW,
        bar_axis_title="Blocked Requests",
        line_axis_title="Allowed Requests",
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.7874,  # increased by 2 cm (≈0.7874 in)
    )

def _draw_vertical_stat_cards(slide, title: str, cards: list,
                              left_in: float, top_in: float, w_in: float, h_in: float,
                              val_font_size: int = 32, lbl_font_size: int = 13):
    """Draws KPI stat cards stacked vertically one above the other.

    val_font_size and lbl_font_size allow callers to shrink text when space is reduced.
    """
    cb._add_section_title(slide, title, left_in, top_in, w_in)
    title_h = 0.38
    content_top = top_in + title_h
    content_h = h_in - title_h

    n_cards = len(cards)
    if n_cards == 0:
        return

    gap = 0.25
    card_h = (content_h - gap * (n_cards - 1)) / n_cards
    card_w = w_in - 0.30  # Slight right margin so it doesn't touch the chart

    for i, card in enumerate(cards):
        c_top = content_top + i * (card_h + gap)
        
        # Rounded rectangle box
        box = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            Inches(left_in), Inches(c_top), Inches(card_w), Inches(card_h)
        )
        box.fill.solid()
        bg_hex = str(card.get("bg_color", "#E0F5EA")).lstrip("#")
        box.fill.fore_color.rgb = RGBColor(int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16))
        box.line.fill.background()
        cb._set_shape_adj(box, 15000)
        
        # Text inside box
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        
        # Value (Big & Bold)
        p_val = tf.paragraphs[0]
        p_val.alignment = PP_ALIGN.CENTER
        r_val = p_val.add_run()
        r_val.text = str(card.get("value", ""))
        r_val.font.bold = True
        r_val.font.size = Pt(val_font_size)
        r_val.font.name = lm.FONT_NAME
        
        clr = card.get("color", cb.CLR_BLUE)
        if isinstance(clr, str):
            clr_hex = clr.lstrip("#")
            clr = RGBColor(int(clr_hex[0:2], 16), int(clr_hex[2:4], 16), int(clr_hex[4:6], 16))
        r_val.font.color.rgb = clr
        
        # Label (Smaller below)
        p_lbl = tf.add_paragraph()
        p_lbl.alignment = PP_ALIGN.CENTER
        r_lbl = p_lbl.add_run()
        r_lbl.text = str(card.get("label", ""))
        r_lbl.font.bold = True
        r_lbl.font.size = Pt(lbl_font_size)
        r_lbl.font.name = lm.FONT_NAME
        r_lbl.font.color.rgb = lm.CLR_DARK

# ── Quarterly Slide Builders ──────────────────────────────────────────

def _build_quarterly_slide_1(prs, rc, threats_months):
    """Slide 2 (Quarterly): Left slot = All Counts KPI cards | Right slot = Threats Trend Column Chart."""
    has_counts = bool(rc)
    has_trend  = bool(threats_months)

    if not has_counts and not has_trend:
        return

    slide = sb.new_content_slide(prs, _SECTION, "Filtering Counts & Quarterly Threat Trend")

    # Left half slot — shrink and nudge down when shown alongside quarterly chart
    KPI_NUDGE_DOWN_IN = 0.19685  # 0.5 cm in inches
    KPI_SHRINK_H_IN = 0.19685

    # Lower the quarterly trend by 2 cm, then enlarge it upward by 2 cm
    TREND_NUDGE_DOWN_IN = 0.7874   # 2.0 cm in inches
    TREND_ENLARGE_UP_IN = 0.7874   # enlarge upwards by 2.0 cm
    new_top = lm.CHART2_TOP_IN + TREND_NUDGE_DOWN_IN - TREND_ENLARGE_UP_IN
    new_h = 3.5 + TREND_ENLARGE_UP_IN

    if has_counts and has_trend:
        cards_left, cards_w = lm.CHART2_L1_IN, lm.CHART2_W_IN
        trend_left, trend_w = lm.CHART2_L2_IN, lm.CHART2_W_IN
    elif has_counts:
        cards_left, cards_w = lm.CONTENT_LEFT_IN, lm.CONTENT_W_IN
    else:
        trend_left, trend_w = lm.CONTENT_LEFT_IN, lm.CONTENT_W_IN

    if has_counts:
        total_threats = rc.get("total_threats_count", 0)
        total_blocked = rc.get("total_blocked_requests", 0)
        cards = [
            {
                "label":    "Total Threats",
                "value":    f"{total_threats:,}",
                "color":    cb.CLR_BLUE,    # #00A550 — brand primary green
                "bg_color": "#E0F5EA",
            },
            {
                "label":    "Total Blocked Requests",
                "value":    f"{total_blocked:,}",
                "color":    cb.CLR_GREEN,   # #74C045 — brand secondary green
                "bg_color": "#F0F8E6",
            },
        ]
        _draw_vertical_stat_cards(
            slide,
            title="All Counts",
            cards=cards,
            left_in=cards_left,
            top_in=lm.CHART2_TOP_IN + KPI_NUDGE_DOWN_IN,
            w_in=cards_w,
            h_in=3.8 - KPI_SHRINK_H_IN,
            val_font_size=18,
            lbl_font_size=11,
        )

    if has_trend:
        months = [str(m).capitalize() for m in threats_months.keys()]
        values = [int(v) for v in threats_months.values()]
        cb.add_column_chart(
            slide, "Quarterly Threats Trend",
            labels=months,
            values=values,
            single_color=cb.CLR_BLUE,  # Strictly forces #00A550 brand green
            y_axis_title="Threat Count",
            left_in=trend_left,
            top_in=new_top,
            w_in=trend_w,
            h_in=new_h,
        )



def _build_quarterly_slide_2(prs, avb_req, avb_thr):
    """Slide 3 (Quarterly): Left slot = Allowed vs Blocked Requests | Right slot = Allowed vs Blocked Threats."""
    has_req = bool(avb_req)
    has_thr = bool(avb_thr)

    if not has_req and not has_thr:
        return

    slide = sb.new_content_slide(prs, _SECTION, "Quarterly Allowed vs Blocked Proportions")

    if has_req and has_thr:
        req_left, req_w = lm.CHART2_L1_IN, lm.CHART2_W_IN
        thr_left, thr_w = lm.CHART2_L2_IN, lm.CHART2_W_IN
    elif has_req:
        req_left, req_w = lm.CONTENT_LEFT_IN, lm.CONTENT_W_IN
    else:
        thr_left, thr_w = lm.CONTENT_LEFT_IN, lm.CONTENT_W_IN

    if has_req:
        _draw_quarterly_progress_cards(
            slide,
            "Quarterly Allowed vs Blocked Requests",
            allowed_dict=avb_req.get("allowed", {}),
            blocked_dict=avb_req.get("blocked", {}),
            is_threats=False,
            left_in=req_left,
            top_in=lm.CHART2_TOP_IN,
            w_in=req_w,
            h_in=3.5,
        )

    if has_thr:
        _draw_quarterly_progress_cards(
            slide,
            "Quarterly Allowed vs Blocked Threats",
            allowed_dict=avb_thr.get("allowed", {}),
            blocked_dict=avb_thr.get("blocked", {}),
            is_threats=True,
            left_in=thr_left,
            top_in=lm.CHART2_TOP_IN,
            w_in=thr_w,
            h_in=3.5,
        )