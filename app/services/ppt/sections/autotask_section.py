"""Autotask section — Helpdesk Ticket Analytics slides."""
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN

import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.layout_manager as lm

SECTION = "Autotask"

# Fixed ticket-priority taxonomy — used as a fallback so the "Open Ticket By
# Priority" donut always has real category labels/colors to show, even when
# there are zero open tickets. Unlike issue-type or contact charts (whose
# categories only exist if data exists), priority levels are a known, fixed
# set independent of the data.
DEFAULT_PRIORITY_LABELS = ["Critical", "High", "Medium", "Low"]

# ── Chart positions matched exactly from reference PPTX (36) ──────────
# Line + Donut: title is INSIDE chart frame (_set_chart_title), so pos = exact frame pos
# Bar + Stacked: title is a separate textbox 0.38" above chart frame (_add_section_title)
#   → _BAR_T / _STACKED_T are shifted up 0.38" so the chart FRAME lands at the right y
_LINE_L,    _LINE_T,    _LINE_W,    _LINE_H    = 0.20,  0.54,  9.60,  1.87
_DONUT_L,   _DONUT_T,   _DONUT_W,   _DONUT_H   = 5.869, 0.380, 3.771, 2.209
# _BAR_L/_BAR_W match _LINE_L/_LINE_W exactly, so the bar chart's right
# edge lines up with the line chart's right edge (both = 0.20 + 9.60 = 9.80").
_BAR_L,     _BAR_T,     _BAR_W,     _BAR_H     = _LINE_L, 1.96,  _LINE_W, 3.38
_STACKED_L, _STACKED_T, _STACKED_W, _STACKED_H = 5.041, 1.87,  4.781, 3.45

# No-data placeholder positions — clean 2×2 grid with no overlap.
# Used ONLY in the else-branches of _build_combined_slide so real chart
# positions are never touched when data is present.
#   Top row  y=0.46 → 2.56  (h=2.10)   gap 0.10"
#   Bot row  y=2.66 → 5.16  (h=2.50)
#   Left col x=0.10 → 4.95  (w=4.85)   gap 0.10"
#   Right col x=5.05 → 9.90 (w=4.85)
_ND_LINE_L,    _ND_LINE_T,    _ND_LINE_W,    _ND_LINE_H    = 0.10, 0.46, 4.85, 2.10
_ND_DONUT_L,   _ND_DONUT_T,   _ND_DONUT_W,   _ND_DONUT_H   = 5.05, 0.46, 4.85, 2.10
_ND_BAR_L,     _ND_BAR_T,     _ND_BAR_W,     _ND_BAR_H     = 0.10, 2.66, 4.85, 2.50
_ND_STACKED_L, _ND_STACKED_T, _ND_STACKED_W, _ND_STACKED_H = 5.05, 2.66, 4.85, 2.50


def _hex(h):
    h = h.lstrip('#')
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _add_line_totals_overlay(slide, total_completed, total_created):
    """Overlay ovals + text labels at top-right of line chart.
    Positioned relative to the line chart's right edge (_LINE_L + _LINE_W)
    so it always sits in the corner even if the chart width changes —
    offsets below are the exact distance-from-right-edge measured from the
    original pixel-perfect PPTX reference."""
    right_edge = _LINE_L + _LINE_W   # 0.20 + 9.60 = 9.80

    # Light green oval — Completed series
    ov1 = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.OVAL,
        Inches(right_edge - 0.9555), Inches(0.5051), Inches(0.0692), Inches(0.07)
    )
    ov1.fill.solid()
    ov1.fill.fore_color.rgb = RGBColor(0xB6, 0xF0, 0x92)
    ov1.line.fill.background()

    tb1 = slide.shapes.add_textbox(
        Inches(right_edge - 0.9706), Inches(0.4492), Inches(1.26), Inches(0.38)
    )
    r1 = tb1.text_frame.paragraphs[0].add_run()
    r1.text = f"Total Completed: {total_completed}"
    r1.font.size      = Pt(7)
    r1.font.bold      = True
    r1.font.name      = lm.FONT_NAME
    r1.font.color.rgb = RGBColor(0x37, 0x41, 0x51)

    # Dark green oval — Created series
    ov2 = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.OVAL,
        Inches(right_edge - 0.9440), Inches(0.6603), Inches(0.0611), Inches(0.07)
    )
    ov2.fill.solid()
    ov2.fill.fore_color.rgb = RGBColor(0x03, 0x4E, 0x27)
    ov2.line.fill.background()

    tb2 = slide.shapes.add_textbox(
        Inches(right_edge - 0.9555), Inches(0.5826), Inches(1.14), Inches(0.38)
    )
    r2 = tb2.text_frame.paragraphs[0].add_run()
    r2.text = f"Total Created: {total_created}"
    r2.font.size      = Pt(7)
    r2.font.bold      = True
    r2.font.name      = lm.FONT_NAME
    r2.font.color.rgb = RGBColor(0x37, 0x41, 0x51)


def _add_donut_legend(slide, labels, colors,
                      donut_l, donut_t, donut_w, donut_h):
    """
    Manual priority legend placed on the RIGHT side of the donut chart frame.
    Items stack vertically, starting ~37% down from the donut top.
    All positions are clamped to stay within the 10" slide width.
    """
    SLIDE_W = 10.0
    OV_SIZE = 0.10
    Y_GAP   = 0.19

    # Oval x at ~71.6% of donut width (right portion, clear of circle edge)
    ov_x = donut_l + donut_w * 0.716
    tx_x = ov_x + 0.055
    # Text width: fill remaining slide width with a small margin
    tx_w = min(SLIDE_W - tx_x - 0.05, 1.30)
    # Clamp to ensure textbox right edge stays within slide
    if tx_x + tx_w > SLIDE_W - 0.05:
        tx_w = SLIDE_W - tx_x - 0.05

    y_start = donut_t + 0.37

    for i, (lbl, clr) in enumerate(zip(labels, colors)):
        ov_y = y_start + i * Y_GAP

        ov = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.OVAL,
            Inches(ov_x), Inches(ov_y), Inches(OV_SIZE), Inches(OV_SIZE)
        )
        ov.fill.solid()
        ov.fill.fore_color.rgb = _hex(clr)
        ov.line.fill.background()

        tb = slide.shapes.add_textbox(
            Inches(tx_x), Inches(ov_y - 0.07), Inches(tx_w), Inches(0.24)
        )
        r = tb.text_frame.paragraphs[0].add_run()
        r.text           = str(lbl)
        r.font.size      = Pt(8)
        r.font.bold      = False
        r.font.name      = lm.FONT_NAME
        r.font.color.rgb = RGBColor(0x24, 0x27, 0x2B)


def _add_line_totals_bottom_overlay(slide, total_completed, total_created):
    """Bottom-left legend for appendix Daily Tickets slide (MAGNA-TILES 45 positions)."""
    # Dark oval — Created
    ov1 = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.OVAL,
        Inches(0.300), Inches(4.865), Inches(0.130), Inches(0.130)
    )
    ov1.fill.solid()
    ov1.fill.fore_color.rgb = RGBColor(0x03, 0x4E, 0x27)
    ov1.line.fill.background()

    tb1 = slide.shapes.add_textbox(
        Inches(0.365), Inches(4.820), Inches(1.144), Inches(0.380)
    )
    r1 = tb1.text_frame.paragraphs[0].add_run()
    r1.text           = f"Total Created: {total_created}"
    r1.font.size      = Pt(7)
    r1.font.bold      = True
    r1.font.name      = lm.FONT_NAME
    r1.font.color.rgb = RGBColor(0x37, 0x41, 0x51)

    # Light oval — Completed
    ov2 = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.OVAL,
        Inches(1.874), Inches(4.865), Inches(0.130), Inches(0.130)
    )
    ov2.fill.solid()
    ov2.fill.fore_color.rgb = RGBColor(0xB6, 0xF0, 0x92)
    ov2.line.fill.background()

    tb2 = slide.shapes.add_textbox(
        Inches(1.939), Inches(4.820), Inches(1.260), Inches(0.380)
    )
    r2 = tb2.text_frame.paragraphs[0].add_run()
    r2.text           = f"Total Completed: {total_completed}"
    r2.font.size      = Pt(7)
    r2.font.bold      = True
    r2.font.name      = lm.FONT_NAME
    r2.font.color.rgb = RGBColor(0x37, 0x41, 0x51)


def _add_bottom_labels(slide, total_tix):
    """Bottom title labels + total count for bar and stacked charts."""
    # "Total Tickets - N" — bottom-left of bar chart area, aligned to the
    # bar chart's actual left edge (was hardcoded to the old layout before).
    tb1 = slide.shapes.add_textbox(
        Inches(_BAR_L), Inches(4.9833), Inches(1.2145), Inches(0.2356)
    )
    r1 = tb1.text_frame.paragraphs[0].add_run()
    r1.text           = f"Total Tickets - {total_tix}"
    r1.font.size      = Pt(8)
    r1.font.bold      = True
    r1.font.name      = lm.FONT_NAME
    r1.font.color.rgb = RGBColor(0x37, 0x41, 0x51)

    # "Tickets Created By Contact" — centred below bar chart
    # Span the full bar chart width (_BAR_L to _BAR_L+_BAR_W) so CENTER alignment
    # places the text exactly in the middle of the bar chart column.
    tb2 = slide.shapes.add_textbox(
        Inches(_BAR_L), Inches(5.089), Inches(_BAR_W), Inches(0.32)
    )
    p2 = tb2.text_frame.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text           = "Tickets Created By Contact"
    r2.font.size      = Pt(10)
    r2.font.bold      = True
    r2.font.name      = lm.FONT_NAME
    r2.font.color.rgb = RGBColor(0x24, 0x27, 0x2B)

def _build_sla_priority_slide(prs, _section, sla: dict):
    """
    2-column slide: First Response KPI | Resolution KPI.

    The slide intentionally contains only the two SLA KPI charts.
    """
    first_r = float(sla.get('first_response_percentage') or 0)
    resol   = float(sla.get('resolution_percentage')    or 0)

    s1, s2 = lm.calc_slots(2)
    slide = sb.new_content_slide(prs, _section, "SLA Met Percentage")

    TITLE_H = 0.38   # same offset used by add_circular_kpi / _add_section_title

    # ── Left: First Response Met Percentage ──────────────────────────────────
    # add_circular_kpi renders a full ring even at 0% — always call it.
    cb.add_circular_kpi(slide, "First Response Met Percentage", first_r, 100,
                        left_in=s1[0], top_in=s1[1], w_in=s1[2], h_in=s1[3])

    # ── Middle: Resolution Met Percentage ────────────────────────────────────
    cb.add_circular_kpi(slide, " SLA Met Percentage", resol, 100,
                        left_in=s2[0], top_in=s2[1], w_in=s2[2], h_in=s2[3])

def _build_combined_slide(prs, _section,
                          series, days, total_completed, total_created,
                          tbc_data, t_labels, t_values, total_tix):
    """Slide 7 layout: daily trend and contact charts combined on one slide.

    The line chart (daily trend) and bar chart (tickets by contact) are
    independent charts — each is only drawn if its own data is present.
    When both are present, same stacked half/half layout as always. When
    only one is present, it expands to fill the whole slide instead of
    leaving the other half blank. Slide is skipped entirely if neither
    chart has data.
    """
    has_trend   = bool(series)
    has_contact = bool(tbc_data)

    if not has_trend and not has_contact:
        return

    slide = sb.new_content_slide(prs, _section, "Daily Tickets Trend")

    if has_trend and has_contact:
        # Both present — original stacked half/half layout, unchanged.
        cb.add_line_chart(
            slide, "Daily Tickets Created vs Completed",
            x_labels=[str(d) for d in days],
            series_data=series,
            colors=["#034E27", "#B6F092"],
            x_axis_title="No. Of Days",
            y_axis_title="Number Of Tickets",
            left_in=_LINE_L, top_in=_LINE_T, w_in=_LINE_W, h_in=_LINE_H
        )
        _add_line_totals_overlay(slide, total_completed, total_created)

        cb.add_bar_chart(
            slide, "",
            labels=t_labels, values=t_values,
            single_color='#00A550',
            x_axis_title="Number Of Tickets",
            left_in=_BAR_L, top_in=_BAR_T, w_in=_BAR_W, h_in=_BAR_H
        )
        _add_bottom_labels(slide, total_tix)

    elif has_trend:
        # Only the trend chart — full-width/full-height, same coordinates
        # already used for the solo version of this chart in the appendix.
        cb.add_line_chart(
            slide, "Daily Tickets Created vs Completed",
            x_labels=[str(d) for d in days],
            series_data=series,
            colors=["#034E27", "#B6F092"],
            x_axis_title="No. Of Days",
            y_axis_title="Number Of Tickets",
            left_in=0.20, top_in=0.55, w_in=9.60, h_in=4.17
        )
        _add_line_totals_bottom_overlay(slide, total_completed, total_created)

    else:
        # Only the contact bar chart — expand upward to fill the freed space.
        cb.add_bar_chart(
            slide, "Tickets Created By Contact",
            labels=t_labels, values=t_values,
            single_color='#00A550',
            x_axis_title="Number Of Tickets",
            corner_label=f"Total Tickets - {total_tix}",
            left_in=0.20, top_in=0.55, w_in=9.60, h_in=4.17
        )


def build_slides(prs, data: dict, section_override=None, skip_section_slide=False):
    _section = section_override or SECTION
    if not skip_section_slide:
        sb.add_section_slide(prs, _section, "Helpdesk Ticket Analytics")

    data   = lm.normalize(data)
    charts = data.get('charts', {})
    sla    = charts.get('sla_performance') or {}

    # ── Data extraction ──────────────────────────────────────────────────
    # Line chart
    dtt       = charts.get('daily_tickets_trend') or {}
    days      = dtt.get('days', list(range(1, 31)))
    created   = dtt.get('created', [])
    completed = dtt.get('completed', [])
    series = {}
    if created:   series['Created']   = created
    if completed: series['Completed'] = completed
    total_created   = sum(int(v) for v in created)   if created   else 0
    total_completed = sum(int(v) for v in completed) if completed else 0

    # Bar by contact
    tbc      = charts.get('tickets_by_contact') or {}
    tbc_data = tbc.get('data', [])
    t_labels = [d.get('name', '')   for d in tbc_data[:12]]
    t_values = [d.get('tickets', 0) for d in tbc_data[:12]]
    tbc_sum  = tbc.get('tickets_by_contact_summary') or {}
    total_tix = tbc_sum.get('contacts_summary', {}).get('total_tickets') or sum(t_values)

    # Monthly tickets by type (separate slide)
    mtbt         = charts.get('monthly_tickets_by_type') or {}
    _mtbt_labels = list(mtbt.keys())
    _mtbt_values = list(mtbt.values())
    _mtbt_clrs   = cb.brand_palette(len(_mtbt_labels))
    _mtbt_total  = sum(int(v) for v in _mtbt_values if v)

    if section_override:
        # ── Customer Success Dashboard (slide 7): combined 4-chart layout only ──
        _build_combined_slide(prs, _section, series, days, total_completed, total_created,
                      tbc_data, t_labels, t_values, total_tix)
    else:
        # ── Appendix slides ───────────────────────────────────────────────────

        # ── Slide A: Daily Tickets Created vs Completed (full width) ─────────
        if dtt:
            slide_a = sb.new_content_slide(prs, _section, "Daily Tickets Trend")
            cb.add_line_chart(
                slide_a, "Daily Tickets Created vs Completed",
                x_labels=[str(d) for d in days],
                series_data=series,
                colors=["#034E27", "#B6F092"],
                x_axis_title="No. Of Days",
                y_axis_title="Number Of Tickets",
                left_in=0.20, top_in=0.55, w_in=9.60, h_in=4.17
            )
            _add_line_totals_bottom_overlay(slide_a, total_completed, total_created)

        # ── Slide B: Tickets Created By Contact (left) | Tickets By Issue Type (right) ──
        # Equal half-slide columns when both present; full width when only one is.
        if tbc_data or mtbt:
            slide_b = sb.new_content_slide(prs, _section, "Tickets By Contact & Issue Type")
            if tbc_data and mtbt:
                s1, s2 = lm.calc_slots(2)
                cb.add_bar_chart(
                    slide_b, "Tickets Created By Contact",
                    labels=t_labels, values=t_values,
                    single_color='#00A550',
                    x_axis_title="Number Of Tickets",
                    corner_label=f"Total Tickets - {total_tix}",
                    left_in=s1[0], top_in=s1[1], w_in=s1[2], h_in=s1[3]
                )
                cb.add_bar_chart(
                    slide_b, "Tickets By Issue Type",
                    labels=_mtbt_labels, values=_mtbt_values, colors=_mtbt_clrs,
                    x_axis_title="Number of Tickets",
                    corner_label=f"Total Tickets - {_mtbt_total}",
                    left_in=s2[0], top_in=s2[1], w_in=s2[2], h_in=s2[3]
                )
            elif tbc_data:
                s1 = lm.calc_slots(1)[0]
                cb.add_bar_chart(
                    slide_b, "Tickets Created By Contact",
                    labels=t_labels, values=t_values,
                    single_color='#00A550',
                    x_axis_title="Number Of Tickets",
                    corner_label=f"Total Tickets - {total_tix}",
                    left_in=s1[0], top_in=s1[1], w_in=s1[2], h_in=s1[3]
                )
            else:
                s1 = lm.calc_slots(1)[0]
                cb.add_bar_chart(
                    slide_b, "Tickets By Issue Type",
                    labels=_mtbt_labels, values=_mtbt_values, colors=_mtbt_clrs,
                    x_axis_title="Number of Tickets",
                    corner_label=f"Total Tickets - {_mtbt_total}",
                    left_in=s1[0], top_in=s1[1], w_in=s1[2], h_in=s1[3]
                )

        # ── Slide C: SLA Met Percentage KPIs ─────────────────────────────────
        if sla:
            _build_sla_priority_slide(prs, _section, sla)