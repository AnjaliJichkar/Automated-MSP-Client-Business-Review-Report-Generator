"""
Chart Builder — Native python-pptx editable charts.
All functions add charts/shapes directly to the slide.
Every function handles the "no data" case gracefully.
"""
import math
from io import BytesIO
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.chart.data import CategoryChartData, ChartData
from pptx.oxml.ns import qn
from lxml import etree
import app.services.ppt.layout_manager as lm

# ── Full color dictionary ─────────────────────────────────────────────
CHART_COLORS = {
    # --- LAVENDER FAMILY ---
    "lavender_soft":   RGBColor(0xC4, 0xB5, 0xFD),  # #C4B5FD
    "lavender_light":  RGBColor(0xDD, 0xD6, 0xFE),  # #DDD6FE
    "lavender_medium": RGBColor(0xA7, 0x8B, 0xFA),  # #A78BFA
    "periwinkle":      RGBColor(0xBF, 0xC9, 0xFF),  # #BFC9FF
    "lilac":           RGBColor(0xE0, 0xC3, 0xFC),  # #E0C3FC
    "wisteria":        RGBColor(0xD8, 0xB4, 0xFE),  # #D8B4FE
    # --- BRAND THEME PALETTE ---
    "brand_dark_blue": RGBColor(0x28, 0x60, 0x94),  # #286094
    "brand_teal":      RGBColor(0x4C, 0xA8, 0x8C),  # #4ca88c
    "brand_dark_teal": RGBColor(0x3E, 0x75, 0x64),  # #3e7564
    "brand_green":     RGBColor(0x8F, 0xA6, 0x46),  # #8fa646
    "brand_lime":      RGBColor(0xC5, 0xE3, 0x64),  # #c5e364
    # --- GREEN FAMILY ---
    "lime_green":      RGBColor(0xBE, 0xF2, 0x64),  # #BEF264
    "mint":            RGBColor(0x6E, 0xE7, 0xB7),  # #6EE7B7
    "sage":            RGBColor(0xBB, 0xF7, 0xD0),  # #BBF7D0
    "seafoam":         RGBColor(0xA7, 0xF3, 0xD0),  # #A7F3D0
    "pistachio":       RGBColor(0xD9, 0xF9, 0x9D),  # #D9F99D
    "fresh_green":     RGBColor(0x86, 0xEF, 0xAC),  # #86EFAC
    # --- BLUE FAMILY ---
    "sky_blue":        RGBColor(0x7D, 0xD3, 0xFC),  # #7DD3FC
    "baby_blue":       RGBColor(0xBA, 0xE6, 0xFD),  # #BAE6FD
    "ice_blue":        RGBColor(0xCF, 0xFE, 0xFE),  # #CFFEFE
    "powder_blue":     RGBColor(0xBF, 0xDB, 0xFF),  # #BFDBFF
    "cornflower":      RGBColor(0x93, 0xC5, 0xFD),  # #93C5FD
    "steel_blue":      RGBColor(0xA5, 0xC8, 0xE8),  # #A5C8E8
    # --- PINK / ROSE FAMILY ---
    "blush":           RGBColor(0xFB, 0xCF, 0xE8),  # #FBCFE8
    "rose_quartz":     RGBColor(0xFC, 0xE7, 0xF3),  # #FCE7F3
    "peach":           RGBColor(0xFE, 0xD7, 0xAA),  # #FED7AA
    "salmon":          RGBColor(0xFC, 0xA5, 0xA5),  # #FCA5A5
    "coral":           RGBColor(0xFF, 0xB3, 0xA7),  # #FFB3A7
    # --- YELLOW / AMBER FAMILY ---
    "buttercup":       RGBColor(0xFE, 0xF0, 0x8A),  # #FEF08A
    "lemon":           RGBColor(0xFE, 0xF9, 0xC3),  # #FEF9C3
    "honey":           RGBColor(0xFD, 0xE6, 0x8A),  # #FDE68A
    "champagne":       RGBColor(0xFC, 0xF1, 0xC8),  # #FCF1C8
    # --- NEUTRAL / BASE ---
    "cloud":           RGBColor(0xF1, 0xF5, 0xF9),  # #F1F5F9
    "pearl":           RGBColor(0xE2, 0xE8, 0xF0),  # #E2E8F0
    "fog":             RGBColor(0xF8, 0xFA, 0xFC),  # #F8FAFC
}

# ── Brand color theme — Approved PMS Green palette ───────────────────
# Ordered: vivid/saturated → medium → dark → lighter accents
BRAND_COLORS = [
    '#00A550',  # PMS 354  — deep vivid green    (primary)
    '#74C045',  # PMS 360  — fresh bright green
    '#3CB043',  # PMS 361  — medium vivid green
    '#72C030',  # PMS 368  — bright lime-green
    '#8DC63F',  # PMS 375  — yellow-green accent
    '#008C40',  # PMS 355  — deep forest green
    '#5CA028',  # PMS 369  — medium green
    '#7AAB28',  # PMS 376  — olive-green
    '#3A8E3A',  # PMS 362  — medium forest
    '#007030',  # PMS 356  — dark green
    '#4C861A',  # PMS 370  — dark green
    '#4E7C36',  # PMS 363  — dark forest
    '#6B8E18',  # PMS 377  — olive
    '#3D6B2A',  # PMS 364  — deep forest
    '#5A6E2A',  # PMS 371  — dark olive
    '#3B5B35',  # PMS 357  — very dark forest
    '#8A9A00',  # PMS 384  — dark olive-lime
    '#5A6A20',  # PMS 378  — dark olive
    '#6E7A10',  # PMS 385  — dark olive-green
    '#A0B800',  # PMS 383  — olive-lime
    '#ADDA5E',  # PMS 367  — light yellow-green
    '#B8D400',  # PMS 382  — bright lime-yellow
    '#CCE000',  # PMS 381  — vivid lime
    '#C5E870',  # PMS 374  — pale lime
    '#C8E278',  # PMS 366  — light yellow-green
    '#B0D888',  # PMS 359  — light lime
    '#D0E888',  # PMS 373  — very light lime
    '#BEDD98',  # PMS 358  — pale sage
]

# Pie/donut palette — dark & medium only (no light colors for small slices)
PIE_COLORS = [
    '#00A550',  # PMS 354
    '#74C045',  # PMS 360
    '#3CB043',  # PMS 361
    '#72C030',  # PMS 368
    '#8DC63F',  # PMS 375
    '#008C40',  # PMS 355
    '#5CA028',  # PMS 369
    '#7AAB28',  # PMS 376
    '#3A8E3A',  # PMS 362
    '#007030',  # PMS 356
    '#4C861A',  # PMS 370
    '#4E7C36',  # PMS 363
    '#6B8E18',  # PMS 377
    '#3D6B2A',  # PMS 364
    '#5A6E2A',  # PMS 371
    '#3B5B35',  # PMS 357
    '#8A9A00',  # PMS 384
    '#5A6A20',  # PMS 378
    '#6E7A10',  # PMS 385
]

# ── Chart series palette — brand theme cycling order ─────────────────
PALETTE = list(BRAND_COLORS)


def pie_palette(n: int) -> list:
    """Return exactly n dark/medium colors for pie & donut charts — no light colors."""
    if n <= 0:
        return []
    if n <= len(PIE_COLORS):
        return PIE_COLORS[:n]
    result = list(PIE_COLORS)
    step = 0
    while len(result) < n:
        step += 1
        blend = min(0.10 * step, 0.40)
        for hex_color in PIE_COLORS:
            if len(result) >= n:
                break
            h  = hex_color.lstrip('#')
            r2 = min(255, int(int(h[0:2], 16) + (255 - int(h[0:2], 16)) * blend))
            g2 = min(255, int(int(h[2:4], 16) + (255 - int(h[2:4], 16)) * blend))
            b2 = min(255, int(int(h[4:6], 16) + (255 - int(h[4:6], 16)) * blend))
            result.append(f'#{r2:02X}{g2:02X}{b2:02X}')
    return result[:n]


def brand_palette(n: int) -> list:
    """Return exactly n colors, always staying within the brand theme.

    - n ≤ 8  → pick the first n BRAND_COLORS directly.
    - n > 8  → fill extra slots with progressively lighter tints of each
               brand color (blended toward white), so colours stay
               on-theme no matter how many bars / slices there are.
    """
    if n <= 0:
        return []
    if n <= len(BRAND_COLORS):
        return BRAND_COLORS[:n]

    result = list(BRAND_COLORS)
    step = 0
    while len(result) < n:
        step += 1
        blend = min(0.12 * step, 0.55)   # lighten up to 55% max, stay on-theme
        for hex_color in BRAND_COLORS:
            if len(result) >= n:
                break
            h = hex_color.lstrip('#')
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            r2 = min(255, int(r + (255 - r) * blend))
            g2 = min(255, int(g + (255 - g) * blend))
            b2 = min(255, int(b + (255 - b) * blend))
            result.append(f'#{r2:02X}{g2:02X}{b2:02X}')
    return result[:n]


# Semantic colors — approved PMS green palette only
CLR_BLUE    = '#00A550'   # PMS 354  — deep vivid green (primary)
CLR_GREEN   = '#74C045'   # PMS 360  — fresh bright green
CLR_YELLOW  = '#CCE000'   # PMS 381  — vivid lime
CLR_RED     = '#8DC63F'   # PMS 375  — yellow-green accent
CLR_DARK    = '#24272b'   # near-black — chart titles
CLR_GRAY    = '#E2E8F0'   # Pearl gray — unchanged
CLR_SUCCESS = '#3CB043'   # PMS 361  — medium vivid green
CLR_DANGER  = '#007030'   # PMS 356  — dark green contrast


# ── Helpers ───────────────────────────────────────────────────────────

def _rgb(hex_str: str) -> RGBColor:
    h = hex_str.lstrip('#')
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _inches(val):
    return Inches(val)


def _set_chart_title(chart, title: str):
    chart.has_title = True
    tf = chart.chart_title.text_frame
    tf.text = title
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.runs[0] if p.runs else p.add_run()
    run.font.name  = lm.FONT_NAME   # Times New Roman
    run.font.size  = Pt(10)
    run.font.bold  = True
    run.font.color.rgb = _rgb(CLR_DARK)


def _remove_chart_border(chart):
    """Remove the chart's outer border."""
    try:
        sp_pr = chart._element.find(qn('c:spPr'))
        if sp_pr is None:
            sp_pr = etree.SubElement(chart._element, qn('c:spPr'))
        ln = sp_pr.find(qn('a:ln'))
        if ln is None:
            ln = etree.SubElement(sp_pr, qn('a:ln'))
        no_fill = ln.find(qn('a:noFill'))
        if no_fill is None:
            etree.SubElement(ln, qn('a:noFill'))
    except Exception:
        pass


def _remove_gridlines(chart):
    """Remove all major and minor gridlines from chart via XML."""
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        if plot_area is not None:
            for tag in (qn('c:majorGridlines'), qn('c:minorGridlines')):
                for el in list(plot_area.findall('.//' + tag)):
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)
    except Exception:
        pass


def _set_gap_width(chart, gap_pct: int = 220):
    """Set gap width between bars.  Higher value → narrower bars (default 150, max 500)."""
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        if plot_area is None:
            return
        for bar_el in plot_area.findall(qn('c:barChart')):
            gw = bar_el.find(qn('c:gapWidth'))
            if gw is None:
                gw = etree.SubElement(bar_el, qn('c:gapWidth'))
            gw.set('val', str(gap_pct))
    except Exception:
        pass


def _apply_rounded_bars(chart):
    """Give bars a rounded-rectangle shape (not a sharp rectangle) via XML.
    Applied at both series level and each data-point level so per-point
    colour overrides don't strip the geometry."""
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        if plot_area is None:
            return

        def _patch(sp_pr_el):
            # Remove any stale prstGeom
            for old in list(sp_pr_el.findall(qn('a:prstGeom'))):
                sp_pr_el.remove(old)
            # Build roundRect element
            prst = etree.Element(qn('a:prstGeom'))
            prst.set('prst', 'roundRect')
            av = etree.SubElement(prst, qn('a:avLst'))
            gd = etree.SubElement(av, qn('a:gd'))
            gd.set('name', 'adj')
            gd.set('fmla', 'val 15000')   # ~15 % rounding — subtle but visible
            sp_pr_el.insert(0, prst)       # must precede fill elements
            # Remove bar outline border
            ln = sp_pr_el.find(qn('a:ln'))
            if ln is None:
                ln = etree.SubElement(sp_pr_el, qn('a:ln'))
            if ln.find(qn('a:noFill')) is None:
                etree.SubElement(ln, qn('a:noFill'))

        for bar_el in plot_area.findall(qn('c:barChart')):
            for ser in bar_el.findall(qn('c:ser')):
                # Series-level spPr
                sp_pr = ser.find(qn('c:spPr'))
                if sp_pr is None:
                    sp_pr = etree.SubElement(ser, qn('c:spPr'))
                _patch(sp_pr)
                # Per-point spPr (created by _color_single_series_points)
                for dpt in ser.findall(qn('c:dPt')):
                    dpt_sp = dpt.find(qn('c:spPr'))
                    if dpt_sp is None:
                        dpt_sp = etree.SubElement(dpt, qn('c:spPr'))
                    _patch(dpt_sp)
    except Exception:
        pass


def _set_shape_adj(shape, adj_val: int = 50000):
    """Set corner-rounding on a ROUNDED_RECTANGLE shape (0 = sharp, 50000 = pill/capsule)."""
    try:
        sp_pr = shape._element.find(qn('p:spPr'))
        if sp_pr is None:
            return
        prst = sp_pr.find(qn('a:prstGeom'))
        if prst is None:
            return
        av_lst = prst.find(qn('a:avLst'))
        if av_lst is None:
            av_lst = etree.SubElement(prst, qn('a:avLst'))
        gd = av_lst.find(qn('a:gd'))
        if gd is None:
            gd = etree.SubElement(av_lst, qn('a:gd'))
        gd.set('name', 'adj')
        gd.set('fmla', f'val {adj_val}')
    except Exception:
        pass


def _style_axis(axis, font_size=8):
    """Style chart axis:
    - Labels : black, Times New Roman (original)
    - Axis line : thin 0.5pt light gray — not bold black
    """
    try:
        axis.has_major_gridlines = False
        axis.has_minor_gridlines = False
        axis.tick_labels.font.size  = Pt(font_size)
        axis.tick_labels.font.name  = lm.FONT_NAME
        axis.tick_labels.font.color.rgb = RGBColor(0x00, 0x00, 0x00)

        # Thin light axis line inserted before c:crossAx (schema order)
        ax_el = axis._element
        for old in ax_el.findall(qn('c:spPr')):
            ax_el.remove(old)
        spPr = etree.Element(qn('c:spPr'))
        ln   = etree.SubElement(spPr, qn('a:ln'))
        ln.set('w', '6350')        # 0.5 pt — thin
        ln.set('cap', 'flat')
        sf   = etree.SubElement(ln, qn('a:solidFill'))
        srgb = etree.SubElement(sf, qn('a:sRGBClr'))
        srgb.set('val', 'D1D5DB')  # light gray
        etree.SubElement(ln, qn('a:prstDash')).set('val', 'solid')
        etree.SubElement(ln, qn('a:round'))

        children  = list(ax_el)
        cross_idx = next((i for i, el in enumerate(children)
                          if el.tag == qn('c:crossAx')), len(children))
        ax_el.insert(cross_idx, spPr)
    except Exception:
        pass


def _flatten_series_values(series_data):
    """Flatten a grouped-series dict into a single list of numeric values."""
    values = []
    for vals in series_data.values():
        values.extend(float(v or 0) for v in vals)
    return values


def _hide_legend(chart):
    chart.has_legend = False


def _show_legend(chart, position=XL_LEGEND_POSITION.BOTTOM):
    chart.has_legend = True
    chart.legend.position = position
    chart.legend.include_in_layout = False
    try:
        chart.legend.font.size = Pt(8)
    except Exception:
        pass


def _color_single_series_points(series, colors_hex: list):
    """Apply different fill colors to each point in a single series."""
    for i, point in enumerate(series.points):
        fill = point.format.fill
        fill.solid()
        fill.fore_color.rgb = _rgb(colors_hex[i % len(colors_hex)])


def _color_series(series, color_hex: str):
    """Apply a single fill color to an entire series."""
    fill = series.format.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(color_hex)
    try:
        line = series.format.line
        line.color.rgb = _rgb(color_hex)
    except Exception:
        pass


def _set_series_line(series, color_hex: str, width_pt: float = 2.0):
    """Style a line chart series."""
    line = series.format.line
    line.color.rgb = _rgb(color_hex)
    line.width = Pt(width_pt)


# ── No Data placeholder
def add_no_data(slide, title: str, left_in, top_in, w_in, h_in,
                message: str = "Data Not Available",
                submessage: str = "No data was returned for this metric."):
    """
    Grey placeholder box shown whenever a chart's/table's data is missing
    or empty. `message` and `submessage` default to the generic wording,
    but callers can override them (e.g. message="No Exploited
    Vulnerabilities Found", submessage="" for a table-specific empty state).
    """
    # Outer rectangle — sharp corners, matches the rest of the report UI
    box = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in)
    )
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xF5, 0xF5, 0xF5)
    box.line.color.rgb = RGBColor(0xDD, 0xDD, 0xDD)
    box.line.width = Pt(1)

    # Chart title
    tb = slide.shapes.add_textbox(
        _inches(left_in + 0.15), _inches(top_in + 0.15),
        _inches(w_in - 0.3), _inches(0.35)
    )
    tf = tb.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = title
    run.font.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x24, 0x27, 0x2B)

    # Centered message
    cy = top_in + h_in / 2 - 0.25
    msg = slide.shapes.add_textbox(
        _inches(left_in), _inches(cy),
        _inches(w_in), _inches(0.5)
    )
    tf2 = msg.text_frame
    p2 = tf2.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = message
    r2.font.size = Pt(12)
    r2.font.bold = True
    r2.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # Sub-message (omitted entirely if blank)
    if submessage:
        sub = slide.shapes.add_textbox(
            _inches(left_in), _inches(cy + 0.35),
            _inches(w_in), _inches(0.3)
        )
        tf3 = sub.text_frame
        p3 = tf3.paragraphs[0]
        p3.alignment = PP_ALIGN.CENTER
        r3 = p3.add_run()
        r3.text = submessage
        r3.font.size = Pt(8)
        r3.font.color.rgb = RGBColor(0xBB, 0xBB, 0xBB)


def _remove_chart_background(chart_frame):
    """Remove white fill from chart area and plot area (transparent background)."""
    A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    try:
        sp_pr = chart_frame._element.find('.//{%s}spPr' % A)
        if sp_pr is None:
            from lxml import etree
            sp_pr = etree.SubElement(chart_frame._element, '{%s}spPr' % A)
        for child in list(sp_pr):
            if child.tag in ('{%s}solidFill' % A, '{%s}gradFill' % A, '{%s}noFill' % A):
                sp_pr.remove(child)
        from lxml import etree
        etree.SubElement(sp_pr, '{%s}noFill' % A)
    except Exception:
        pass
    try:
        chart = chart_frame.chart
        for area_tag in ('plotArea', 'chartArea'):
            from lxml import etree
            C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
            areas = chart._element.findall('.//{%s}%s' % (C, area_tag))
            for area in areas:
                sp = area.find('{%s}spPr' % A)
                if sp is None:
                    sp = etree.SubElement(area, '{%s}spPr' % A)
                for child in list(sp):
                    if child.tag in ('{%s}solidFill' % A, '{%s}gradFill' % A, '{%s}noFill' % A):
                        sp.remove(child)
                etree.SubElement(sp, '{%s}noFill' % A)
                ln = sp.find('{%s}ln' % A)
                if ln is None:
                    ln = etree.SubElement(sp, '{%s}ln' % A)
                for child in list(ln):
                    ln.remove(child)
                etree.SubElement(ln, '{%s}noFill' % A)
    except Exception:
        pass


# ── Legend helpers ────────────────────────────────────────────────────

def _draw_auto_legend(slide, labels: list, colors: list,
                      left_in, top_in, w_in):
    """
    Draw a manual legend below a chart using a strict grid column layout.
    Items are packed greedily into rows, then all rows share the same fixed
    column x-positions so labels stay perfectly aligned top-to-bottom.
    """
    LEGEND_ROW_H   = 0.24
    LEGEND_ROW_PAD = 0.04
    _CHAR_W = 0.062
    _DOT    = 0.10
    _GAP    = 0.04
    _IPAD   = 0.18   # horizontal gap between columns

    # Step 1 — compute natural width for every item
    item_widths = [_DOT + _GAP + len(str(l).replace('_', ' ')) * _CHAR_W for l in labels]

    # Step 2 — greedy row packing (break only when item would overflow width)
    rows, cur_row, cur_w = [], [], 0.0
    for iw in item_widths:
        needed = iw + (_IPAD if cur_row else 0)
        if cur_row and cur_w + needed > w_in + 0.01:
            rows.append(cur_row)
            cur_row = [iw]; cur_w = iw
        else:
            cur_row.append(iw); cur_w += needed
    if cur_row:
        rows.append(cur_row)

    # Step 3 — build a flat index map: rows[r][c] → global item index
    max_cols = max(len(r) for r in rows)
    # For each column c, find the maximum item width across all rows that have column c
    col_widths = []
    for c in range(max_cols):
        col_widths.append(max(
            (row[c] for row in rows if c < len(row)),
            default=0
        ))

    # Step 4 — centre the whole grid block within the available width
    grid_total_w = sum(col_widths) + _IPAD * (max_cols - 1)
    grid_x = left_in + (w_in - grid_total_w) / 2

    # Pre-compute fixed x start for each column
    col_x = []
    cx = grid_x
    for cw in col_widths:
        col_x.append(cx)
        cx += cw + _IPAD

    # Step 5 — draw each item at its grid position
    item_idx = 0
    for row_idx, row_items in enumerate(rows):
        row_y = top_in + row_idx * (LEGEND_ROW_H + LEGEND_ROW_PAD)

        for col_idx, iw in enumerate(row_items):
            if item_idx >= len(labels):
                break
            lbl   = str(labels[item_idx]).replace('_', ' ')
            color = colors[item_idx % len(colors)]
            x     = col_x[col_idx]

            # Dot
            dot = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.OVAL,
                _inches(x), _inches(row_y + (LEGEND_ROW_H - _DOT) / 2),
                _inches(_DOT), _inches(_DOT)
            )
            dot.fill.solid()
            dot.fill.fore_color.rgb = _rgb(color)
            dot.line.fill.background()

            # Label text — starts at centre of dot (aligns visually with the circle)
            txt_x = x + _DOT / 2
            txt_w = col_widths[col_idx] - _DOT / 2
            tb2 = slide.shapes.add_textbox(
                _inches(txt_x), _inches(row_y),
                _inches(max(txt_w, 0.3)), _inches(LEGEND_ROW_H)
            )
            tf = tb2.text_frame
            tf.word_wrap = False
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = lbl
            r.font.size = Pt(8)
            r.font.name = lm.FONT_NAME
            r.font.color.rgb = _rgb(CLR_DARK)

            item_idx += 1


# ── Donut Chart ───────────────────────────────────────────────────────

# ── Empty-state ring color — flat neutral gray for the "no data" donut ring
EMPTY_RING_COLOR = '#E5E7EB'


# ═══════════════════════════════════════════════════════════════════
# Hand-drawn donut ring (freeform shapes, NOT a native chart object)
# ═══════════════════════════════════════════════════════════════════
# Replaces the native XL_CHART_TYPE.DOUGHNUT approach. Native chart
# plot-area layout proved unreliable to pin exactly across PowerPoint
# versions/renderers — even after two rounds of genuine XML bugs found
# and fixed (a plotArea lookup that silently matched nothing, then
# missing wMode/hMode), the center label still drifted for some users.
# Hand-drawn shapes have an EXACTLY known center because the geometry
# is computed directly — there is no chart-engine auto-layout in the
# loop at all, so there is nothing left to drift, in any renderer.
#
# Tradeoff (explicitly OK'd): these rings are plain shapes, not
# editable via PowerPoint's native "Edit Data in Excel".

EMPTY_RING_COLOR = '#E5E7EB'


def _donut_polar_xy(cx: float, cy: float, r: float, angle_deg: float) -> tuple:
    """angle_deg: 0 = 12 o'clock (top), increasing clockwise."""
    rad = math.radians(angle_deg)
    return (cx + r * math.sin(rad), cy - r * math.cos(rad))


def _add_donut_wedge_shape(slide, cx: float, cy: float, r_outer: float, r_inner: float,
                           angle_start: float, angle_end: float, color_hex: str):
    """
    One donut slice as a closed freeform polygon (outer arc + inner arc
    back), approximated with short line segments (~3° each). Uses
    absolute EMU coordinates directly (not a scaled local system), so
    position is exact — no rounding-precision loss, no layout ambiguity.
    """
    span = angle_end - angle_start
    if abs(span) < 0.01:
        return None
    n_segs = max(2, int(abs(span) / 3) + 1)
    angles = [angle_start + span * i / n_segs for i in range(n_segs + 1)]
    outer_pts = [_donut_polar_xy(cx, cy, r_outer, a) for a in angles]
    inner_pts = [_donut_polar_xy(cx, cy, r_inner, a) for a in reversed(angles)]
    float_pts = outer_pts + inner_pts
    emu_pts = [(int(Inches(x)), int(Inches(y))) for x, y in float_pts]

    fb = slide.shapes.build_freeform(emu_pts[0][0], emu_pts[0][1], scale=1)
    fb.add_line_segments(emu_pts[1:], close=True)
    shape = fb.convert_to_shape()
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color_hex)
    shape.line.fill.background()
    try:
        shape.shadow.inherit = False
    except Exception:
        pass
    return shape


def _wrap_text_to_width(text: str, max_width_in: float, size_pt: float, bold: bool = False) -> list:
    """Greedy word-wrap using a conservative Times New Roman width estimate —
    breaks a line onto multiple lines if it would be too wide, rather than
    letting it run outside the donut's inner circle."""
    text = str(text)
    if not text:
        return ['']
    per_char_in = size_pt * (0.56 if bold else 0.50) / 72.0
    max_chars = max(1, int(max_width_in / per_char_in))
    words = text.split(' ')
    lines, cur = [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if len(trial) <= max_chars or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ['']


def _count_legend_rows(labels: list, w_in: float) -> int:
    """Mirrors _draw_auto_legend's row-packing math, without drawing — used
    to reserve exact vertical space for the legend before it's drawn."""
    _CHAR_W, _DOT, _GAP, _IPAD = 0.062, 0.10, 0.04, 0.18
    item_widths = [_DOT + _GAP + len(str(l).replace('_', ' ')) * _CHAR_W for l in labels]
    rows, cur_row, cur_w = [], [], 0.0
    for iw in item_widths:
        needed = iw + (_IPAD if cur_row else 0)
        if cur_row and cur_w + needed > w_in + 0.01:
            rows.append(cur_row); cur_row = [iw]; cur_w = iw
        else:
            cur_row.append(iw); cur_w += needed
    if cur_row:
        rows.append(cur_row)
    return max(1, len(rows))


def _draw_donut_center_block(slide, cx: float, cy: float, r_inner: float, line_specs: list):
    """
    line_specs: list of (text, size_pt, bold, color_hex) in final display
    order (label line(s) first, value line last). Each entry is
    auto-wrapped onto multiple lines if too wide for the inner circle;
    the whole resulting block is vertically centered on cy, each line
    horizontally centered on cx. cx/cy are pure geometry the caller
    already used to draw the ring itself, so this is always exactly
    aligned — regardless of how long the label text is.
    """
    usable_w = r_inner * 2 * 0.86

    resolved = []
    for text, size, bold, color in line_specs:
        for line in _wrap_text_to_width(text, usable_w, size, bold):
            resolved.append((line, size, bold, color))

    line_heights = [size * 1.25 / 72.0 for (_, size, _, _) in resolved]
    total_h = sum(line_heights)
    y = cy - total_h / 2
    box_w = usable_w + 0.3

    for (text, size, bold, color), lh in zip(resolved, line_heights):
        box = slide.shapes.add_textbox(
            _inches(cx - box_w / 2), _inches(y), _inches(box_w), _inches(lh)
        )
        box.text_frame.word_wrap = False
        box.text_frame.margin_left = Inches(0)
        box.text_frame.margin_right = Inches(0)
        box.text_frame.margin_top = Inches(0)
        box.text_frame.margin_bottom = Inches(0)
        p = box.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = text
        r.font.name = lm.FONT_NAME
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = _rgb(color)
        y += lh


def _add_empty_donut_chart(slide, title: str, labels: list, colors: list = None,
                           left_in=0, top_in=0, w_in=5, h_in=5,
                           show_title=True, show_legend=True,
                           legend_left_offset: float = 0.0):
    """
    Empty-state donut: a single flat gray ring (no data slices) with the
    REAL category legend drawn below it (so the reader still sees what the
    chart measures) and a "Total / 0" label centered in the hole.
    """
    add_donut_chart(
        slide, title, labels, [0.0] * len(labels), colors,
        left_in=left_in, top_in=top_in, w_in=w_in, h_in=h_in,
        show_title=show_title, show_legend=show_legend,
        legend_left_offset=legend_left_offset,
    )


def add_donut_chart(slide, title: str, labels: list, values: list,
                    colors: list = None, left_in=0, top_in=0, w_in=5, h_in=5,
                    show_title=True, show_legend=True, center_label=None,
                    legend_left_offset: float = 0.0,
                    center_value_size: int = None, center_value_bold: bool = None,
                    center_value_color: str = None):
    """
    Hand-drawn donut ring (freeform wedge shapes) — see the block comment
    above _donut_polar_xy for why. Same external signature/behavior as
    the old native-chart version, so every existing call site (Infima,
    NodeWare, Axcient, etc.) keeps working unchanged.

    If every value is zero/missing but labels are known: renders a flat
    gray ring + the real legend + "Total 0" (matches the old
    _add_empty_donut_chart behavior, now folded in here directly).

    center_label accepts EITHER a string (legacy — '\\n' separates lines,
    first line styled 14pt bold, remaining lines share
    center_value_size/bold/color) OR a list of (text, size_pt, bold,
    color_hex) tuples for full per-line control. Either way, every
    resulting line is now auto-wrapped if it's too wide for the donut's
    inner circle, and the block is vertically centered exactly on the
    ring's true geometric center.
    """
    labels = labels or []
    colors = colors or brand_palette(len(labels) or len(values))
    values = [float(v) if v else 0.0 for v in (values or [])]
    total = sum(values)

    TITLE_H = 0.30 if (show_title and title) else 0.0
    if show_title and title:
        title_box = slide.shapes.add_textbox(
            _inches(left_in), _inches(top_in), _inches(w_in), _inches(TITLE_H)
        )
        title_box.text_frame.word_wrap = False
        tp = title_box.text_frame.paragraphs[0]
        tp.alignment = PP_ALIGN.CENTER
        tr = tp.add_run()
        tr.text = title
        tr.font.name = lm.FONT_NAME
        tr.font.size = Pt(10)
        tr.font.bold = True
        tr.font.color.rgb = _rgb(CLR_DARK)

    legend_h = 0.0
    if show_legend and labels:
        LEGEND_ROW_H, LEGEND_ROW_PAD, LEGEND_TOP_PAD = 0.24, 0.04, 0.06
        n_rows = _count_legend_rows(labels, w_in)
        legend_h = LEGEND_TOP_PAD + n_rows * (LEGEND_ROW_H + LEGEND_ROW_PAD)

    ring_top   = top_in + TITLE_H
    ring_area_h = max(0.4, h_in - TITLE_H - legend_h)
    ring_area_w = w_in

    diameter = max(0.5, min(ring_area_w, ring_area_h) * 0.90)
    r_outer  = diameter / 2
    r_inner  = r_outer * 0.5
    cx = left_in + ring_area_w / 2
    cy = ring_top + ring_area_h / 2

    if total <= 0:
        _add_donut_wedge_shape(slide, cx, cy, r_outer, r_inner, 0, 360, EMPTY_RING_COLOR)
        if show_legend and labels:
            legend_top = ring_top + ring_area_h + 0.05
            _draw_auto_legend(slide, labels, colors, left_in + legend_left_offset, legend_top, w_in)
        _draw_donut_center_block(slide, cx, cy, r_inner, [
            ('Total', 9, False, '#6B7280'),
            ('0', 20, True, '#111827'),
        ])
        return

    cum = 0.0
    for i, v in enumerate(values):
        if v <= 0:
            continue
        a_start = cum / total * 360.0
        cum += v
        a_end = cum / total * 360.0
        color = colors[i % len(colors)]
        _add_donut_wedge_shape(slide, cx, cy, r_outer, r_inner, a_start, a_end, color)

        # Data label (integer count) at the wedge's mid-angle/mid-radius
        mid_a = (a_start + a_end) / 2.0
        mid_r = (r_outer + r_inner) / 2.0
        lx, ly = _donut_polar_xy(cx, cy, mid_r, mid_a)
        lbl_box = slide.shapes.add_textbox(
            _inches(lx - 0.35), _inches(ly - 0.11), _inches(0.7), _inches(0.22)
        )
        lbl_box.text_frame.word_wrap = False
        lp = lbl_box.text_frame.paragraphs[0]
        lp.alignment = PP_ALIGN.CENTER
        lr = lp.add_run()
        lr.text = str(int(v))
        lr.font.name = lm.FONT_NAME
        lr.font.size = Pt(8)
        lr.font.bold = True
        lr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    if show_legend and labels:
        legend_top = ring_top + ring_area_h + 0.05
        _draw_auto_legend(slide, labels, colors, left_in + legend_left_offset, legend_top, w_in)

    if center_label:
        if isinstance(center_label, (list, tuple)):
            line_specs = list(center_label)
        else:
            raw_lines = str(center_label).split('\n')
            line_specs = []
            for idx, line in enumerate(raw_lines):
                if idx == 0:
                    line_specs.append((line, 14, True, '#111827'))
                else:
                    line_specs.append((
                        line,
                        center_value_size if center_value_size is not None else 7,
                        center_value_bold if center_value_bold is not None else False,
                        center_value_color if center_value_color else '#6B7280',
                    ))
        _draw_donut_center_block(slide, cx, cy, r_inner, line_specs)


def _color_chart_points_xml(series, colors_hex: list):
    """Apply per-point colors to a bar/column series via dPt XML elements."""
    A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    ser_el = series._element
    for i, hex_c in enumerate(colors_hex):
        dpt = etree.SubElement(ser_el, qn('c:dPt'))
        idx = etree.SubElement(dpt, qn('c:idx'))
        idx.set('val', str(i))
        inv = etree.SubElement(dpt, qn('c:invertIfNegative'))
        inv.set('val', '0')
        sp = etree.SubElement(dpt, qn('c:spPr'))
        sf = etree.SubElement(sp, '{%s}solidFill' % A)
        clr_el = etree.SubElement(sf, '{%s}srgbClr' % A)
        clr_el.set('val', hex_c.lstrip('#'))
        ln = etree.SubElement(sp, '{%s}ln' % A)
        etree.SubElement(ln, '{%s}noFill' % A)


# ── Vertical Bar (Column) Chart — native PPTX ─────────────────────────

def add_column_chart(slide, title: str, labels: list, values: list,
                     colors: list = None, left_in=0, top_in=0, w_in=5, h_in=5,
                     single_color: str = None, x_axis_title: str = None,
                     y_axis_title: str = None):
    """
    Native COLUMN_CLUSTERED chart with per-point coloring and value data labels.
    Title is rendered as a textbox above the chart.

    If values are missing/empty but categories (labels) are known, the full
    chart frame (axes, categories, title) is rendered with zero-height bars.
    If there are no categories at all either (e.g. no fixed taxonomy exists
    for this metric), a single "No Data" placeholder category is used so the
    chart frame itself is still always shown — never a generic box.
    """
    if not labels:
        labels = ['No Data']
        values = [0.0]
    else:
        values = [float(v or 0) for v in values] if values else [0.0] * len(labels)

    if single_color:
        colors = [single_color] * len(labels)
    else:
        colors = colors or brand_palette(len(labels))

    title_h = 0.38
    _add_section_title(slide, title, left_in, top_in, w_in)

    chart_top = top_in + title_h
    chart_h   = h_in - title_h

    chart_data = CategoryChartData()
    chart_data.categories = labels
    chart_data.add_series('', [float(v or 0) for v in values])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        _inches(left_in), _inches(chart_top), _inches(w_in), _inches(chart_h),
        chart_data
    )
    _remove_chart_background(chart_frame)
    chart = chart_frame.chart
    chart.has_title  = False
    chart.has_legend = False

    # Gap width = 150
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        for bar_el in plot_area.findall(qn('c:barChart')):
            gw = bar_el.find(qn('c:gapWidth'))
            if gw is None:
                gw = etree.SubElement(bar_el, qn('c:gapWidth'))
            gw.set('val', '150')
    except Exception:
        pass

    # Per-point colors
    try:
        ser = chart.series[0]
        if single_color:
            _color_series(ser, single_color)
        else:
            _color_chart_points_xml(ser, colors)
    except Exception:
        pass

    # Data labels: show value, 8pt bold black
    try:
        plot = chart.plots[0]
        plot.has_data_labels = True
        dls = plot.data_labels
        dls.show_value       = True
        dls.show_percentage  = False
        dls.show_series_name = False
        dls.font.size        = Pt(8)
        dls.font.bold        = True
        dls.font.color.rgb   = RGBColor(0x00, 0x00, 0x00)
    except Exception:
        pass

    # Axis labels: Times New Roman 8pt
    try:
        _style_axis(chart.category_axis, font_size=8)
        _style_axis(chart.value_axis, font_size=8)
        _remove_gridlines(chart)
        if x_axis_title:
            _set_axis_title(chart.category_axis, x_axis_title, font_size=8)
        if y_axis_title:
            _set_axis_title(chart.value_axis, y_axis_title, font_size=8)
        # Force zero baseline on the value axis for non-negative series.
        if all(v >= 0 for v in [float(v or 0) for v in values]):
            chart.value_axis.minimum_scale = 0.0
    except Exception:
        pass


# ── Horizontal Bar Chart — native PPTX BAR_CLUSTERED ─────────────────

def add_bar_chart(slide, title: str, labels: list, values: list,
                  colors: list = None, left_in=0, top_in=0, w_in=5, h_in=5,
                  single_color: str = None, x_axis_title: str = None,
                  corner_label: str = None, title_position: str = 'top'):
    """
    Native BAR_CLUSTERED (horizontal) chart with per-point coloring and value labels.
    single_color   : if set, all bars use this color.
    x_axis_title   : optional label shown below the value axis.
    corner_label   : optional text — top-right of the slot when title_position='top'
                     (e.g. "Total Tickets - 42"), or bottom-left row when
                     title_position='bottom'.
    title_position : 'top' (default) — title drawn as a textbox above the chart,
                      same as before.
                      'bottom' — title is NOT drawn above the chart; instead the
                      chart uses the full h_in, and both `title` and
                      `corner_label` are drawn together in a single row at the
                      very bottom of the slot (title right-aligned/underlined,
                      corner_label at bottom-left) — matches decks where the
                      title sits below the x-axis label instead of above the
                      chart.

    If values are missing/empty but categories (labels) are known, the full
    chart frame (axes, categories, title) is rendered with zero-length bars.
    If there are no categories at all either, a single "No Data" placeholder
    category is used so the chart frame itself is still always shown —
    never a generic box.
    """
    if not labels:
        labels = ['No Data']
        values = [0.0]
    else:
        values = [float(v or 0) for v in values] if values else [0.0] * len(labels)

    if single_color:
        colors = [single_color] * len(labels)
    else:
        colors = colors or brand_palette(len(labels))

    # ── Reserve chart geometry based on where the title goes ────────────
    if title_position == 'bottom':
        chart_top = top_in
        chart_h   = h_in - 0.30   # reserve a bottom row for title + corner_label
    else:
        title_h = 0.38
        _add_section_title(slide, title, left_in, top_in, w_in)
        chart_top = top_in + title_h
        chart_h   = h_in - title_h

    chart_data = CategoryChartData()
    chart_data.categories = labels
    chart_data.add_series('', [float(v or 0) for v in values])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        _inches(left_in), _inches(chart_top), _inches(w_in), _inches(chart_h),
        chart_data
    )
    _remove_chart_background(chart_frame)
    chart = chart_frame.chart
    chart.has_title  = False
    chart.has_legend = False

    # Gap width = 150
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        for bar_el in plot_area.findall(qn('c:barChart')):
            gw = bar_el.find(qn('c:gapWidth'))
            if gw is None:
                gw = etree.SubElement(bar_el, qn('c:gapWidth'))
            gw.set('val', '150')
    except Exception:
        pass

    # Per-point colors
    try:
        ser = chart.series[0]
        if single_color:
            _color_series(ser, single_color)
        else:
            _color_chart_points_xml(ser, colors)
    except Exception:
        pass

    # Data labels: show value, 8pt bold black
    try:
        plot = chart.plots[0]
        plot.has_data_labels = True
        dls = plot.data_labels
        dls.show_value       = True
        dls.show_percentage  = False
        dls.show_series_name = False
        dls.font.size        = Pt(8)
        dls.font.bold        = True
        dls.font.color.rgb   = RGBColor(0x00, 0x00, 0x00)
    except Exception:
        pass

    # Axis labels: Times New Roman 8pt
    try:
        _style_axis(chart.category_axis, font_size=8)
        _style_axis(chart.value_axis, font_size=8)
        _remove_gridlines(chart)
        if x_axis_title:
            _set_axis_title(chart.value_axis, x_axis_title, font_size=8)
    except Exception:
        pass

    # ── Title / corner label placement (AFTER the chart is built) ───────
    if title_position == 'bottom':
        row_top = top_in + h_in - 0.28
        if corner_label:
            lbl = slide.shapes.add_textbox(
                _inches(left_in), _inches(row_top), _inches(w_in * 0.35), _inches(0.26)
            )
            tr = lbl.text_frame.paragraphs[0].add_run()
            tr.text = corner_label
            tr.font.size, tr.font.bold, tr.font.name = Pt(9), True, lm.FONT_NAME
            tr.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
        ttl = slide.shapes.add_textbox(
            _inches(left_in + w_in * 0.30), _inches(row_top), _inches(w_in * 0.65), _inches(0.26)
        )
        tr2 = ttl.text_frame.paragraphs[0].add_run()
        tr2.text = title
        tr2.font.size, tr2.font.bold, tr2.font.underline = Pt(11), True, True
        tr2.font.name = lm.FONT_NAME
        tr2.font.color.rgb = RGBColor(0x1E, 0x3D, 0x2F)
    elif corner_label:
        # Corner label (e.g. "Total Tickets - 42") — top-right of the slot
        clbl = slide.shapes.add_textbox(
            _inches(left_in), _inches(top_in + 0.04),
            _inches(w_in - 0.08), _inches(0.32)
        )
        tp = clbl.text_frame.paragraphs[0]
        tp.alignment = PP_ALIGN.RIGHT
        tr = tp.add_run()
        tr.text = corner_label
        tr.font.size = Pt(8)
        tr.font.bold = True
        tr.font.name = lm.FONT_NAME
        tr.font.color.rgb = RGBColor(0x37, 0x41, 0x51)


# ── Grouped Bar Chart (multiple series, horizontal) ───────────────────

def add_grouped_bar_chart(slide, title: str, categories: list,
                          series_data: dict, colors: list = None,
                          left_in=0, top_in=0, w_in=5, h_in=5, horizontal=True,
                          per_category_colors: list = None, corner_label: str = None,
                          x_axis_title: str = None, y_axis_title: str = None):
    """
    Editable grouped bar chart.
    series_data           : dict of {series_name: [values]}
    per_category_colors   : optional list of hex colors per category — overrides
                            per-series coloring so each category column has its
                            own colour across all series (e.g. severity charts).

    If categories are missing/empty but series_data still has known series
    names, a single "No Data" placeholder category (zero values) is used so
    the chart frame itself is always rendered — never a generic box. Only
    falls back to add_no_data() when series_data itself is completely empty
    (no series names known at all).
    """
    if not series_data:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    if not categories:
        categories = ['No Data']
        series_data = {name: [0.0] for name in series_data.keys()}
    else:
        series_data = {
            name: ([float(v or 0) for v in vals] if vals else [0.0] * len(categories))
            for name, vals in series_data.items()
        }

    colors = colors or brand_palette(len(series_data))

    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, vals in series_data.items():
        chart_data.add_series(name, [float(v) for v in vals])

    chart_type = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED

    chart_frame = slide.shapes.add_chart(
        chart_type,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in),
        chart_data
    )
    chart = chart_frame.chart
    _set_chart_title(chart, title)
    _show_legend(chart, XL_LEGEND_POSITION.BOTTOM)

    for i, series in enumerate(chart.series):
        try:
            if per_category_colors:
                _color_chart_points_xml(series, per_category_colors)
            else:
                _color_series(series, colors[i % len(colors)])
        except Exception:
            pass

    # Data labels: value on each bar, black 8pt bold; zeros show as blank
    try:
        plot = chart.plots[0]
        plot.has_data_labels = True
        dls = plot.data_labels
        dls.show_value       = True
        dls.show_percentage  = False
        dls.show_series_name = False
        dls.number_format    = '#,##0;-#,##0;;'   # empty 3rd section = hide zero
        dls.font.size        = Pt(8)
        dls.font.bold        = True
        dls.font.color.rgb   = RGBColor(0x00, 0x00, 0x00)
    except Exception:
        pass

    try:
        _style_axis(chart.category_axis)
        _style_axis(chart.value_axis)
        _remove_gridlines(chart)
        _set_gap_width(chart, 180)
        if horizontal:
            if x_axis_title:
                _set_axis_title(chart.value_axis, x_axis_title, font_size=8)
            if y_axis_title:
                _set_axis_title(chart.category_axis, y_axis_title, font_size=8)
        else:
            if x_axis_title:
                _set_axis_title(chart.category_axis, x_axis_title, font_size=8)
            if y_axis_title:
                _set_axis_title(chart.value_axis, y_axis_title, font_size=8)
        # Force zero baseline on the value axis when values are non-negative.
        if all(v >= 0 for v in _flatten_series_values(series_data)):
            chart.value_axis.minimum_scale = 0.0
    except Exception:
        pass

    if corner_label:
        tb = slide.shapes.add_textbox(
            _inches(left_in), _inches(top_in),
            _inches(w_in - 0.70), _inches(0.28)
        )
        p  = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        tr = p.add_run()
        tr.text           = corner_label
        tr.font.size      = Pt(9)
        tr.font.bold      = True
        tr.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
        tr.font.name      = lm.FONT_NAME


# ── Stacked Bar Chart ─────────────────────────────────────────────────

def add_stacked_bar_chart(slide, title: str, categories: list,
                          series_data: dict, colors: list = None,
                          left_in=0, top_in=0, w_in=5, h_in=5, horizontal=True):
    """
    Editable stacked bar chart.
    series_data: dict of {series_name: [values]}
    """
    if not series_data:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    colors = colors or brand_palette(len(series_data))

    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, vals in series_data.items():
        chart_data.add_series(name, [float(v) for v in vals])

    chart_type = XL_CHART_TYPE.BAR_STACKED if horizontal else XL_CHART_TYPE.COLUMN_STACKED

    chart_frame = slide.shapes.add_chart(
        chart_type,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in),
        chart_data
    )
    chart = chart_frame.chart
    _set_chart_title(chart, title)
    _show_legend(chart, XL_LEGEND_POSITION.BOTTOM)

    for i, series in enumerate(chart.series):
        try:
            _color_series(series, colors[i % len(colors)])
        except Exception:
            pass

    try:
        _style_axis(chart.category_axis)
        _style_axis(chart.value_axis)
        _remove_gridlines(chart)
        _set_gap_width(chart, 220)
    except Exception:
        pass


# ── Line Chart ────────────────────────────────────────────────────────

def _set_axis_title(axis, title_text: str, font_size: int = 8):
    """Add a title label to a chart axis — black, Times New Roman."""
    try:
        axis.has_title = True
        tf = axis.axis_title.text_frame
        tf.word_wrap = False
        p  = tf.paragraphs[0]
        p.clear()
        r  = p.add_run()
        r.text = title_text
        r.font.size = Pt(font_size)
        r.font.name = lm.FONT_NAME
        r.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    except Exception:
        pass


def add_line_chart(slide, title: str, x_labels: list, series_data: dict,
                   colors: list = None, left_in=0, top_in=0, w_in=5, h_in=5,
                   x_axis_title: str = None, y_axis_title: str = None,
                   totals: dict = None):
    """
    Editable line chart.
    series_data : dict of {series_name: [values]}
    x_labels    : list of x-axis category labels.
    totals      : optional dict {series_name: total_count} — shown as colour-swatch
                  legend below the chart (e.g. {'Total Created': 123, 'Total Completed': 98})

    If series_data is missing/empty but x_labels are known (e.g. the days of
    the reporting period), the full chart frame (axes, category labels,
    title) is still rendered as a flat zero-value line — only falls back to
    add_no_data() when there are no x_labels at all to plot against.
    """
    if not x_labels:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    if not series_data:
        series_data = {'No Data': [0.0] * len(x_labels)}

    colors = colors or brand_palette(len(series_data))

    # Reserve bottom space for custom totals legend
    TOTALS_H = 0.38 if totals else 0.0
    chart_h_actual = h_in - TOTALS_H

    chart_data = CategoryChartData()
    chart_data.categories = x_labels
    for name, vals in series_data.items():
        chart_data.add_series(name, [float(v) for v in vals])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(chart_h_actual),
        chart_data
    )
    chart = chart_frame.chart
    _set_chart_title(chart, title)
    # Hide built-in legend — we draw custom totals legend below
    chart.has_legend = False

    for i, series in enumerate(chart.series):
        try:
            _set_series_line(series, colors[i % len(colors)], 1.5)
        except Exception:
            pass

    try:
        _style_axis(chart.category_axis, font_size=8)
        _style_axis(chart.value_axis, font_size=8)
        _remove_gridlines(chart)
        if x_axis_title:
            _set_axis_title(chart.category_axis, x_axis_title, font_size=8)
        if y_axis_title:
            _set_axis_title(chart.value_axis, y_axis_title, font_size=8)
    except Exception:
        pass

    # Custom totals legend
    if totals:
        DOT   = 0.13
        GAP   = 0.05
        IPAD  = 0.25
        CHSZ  = 7
        CHAR_W = 0.058
        leg_top = top_in + chart_h_actual + 0.06
        x_cur   = left_in + 0.1
        series_names = list(series_data.keys())
        for idx, (label, total_val) in enumerate(totals.items()):
            clr = colors[idx % len(colors)]
            # Colour dot
            dot = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.OVAL,
                _inches(x_cur), _inches(leg_top + (TOTALS_H - DOT) / 2 - 0.04),
                _inches(DOT), _inches(DOT)
            )
            dot.fill.solid()
            dot.fill.fore_color.rgb = _rgb(clr)
            dot.line.fill.background()
            # Label text — starts at centre of dot, top slightly below oval centre
            lbl_text = f"{label}: {total_val}"
            lbl_w    = len(lbl_text) * CHAR_W + 0.1
            lbl_box  = slide.shapes.add_textbox(
                _inches(x_cur + DOT / 2), _inches(leg_top + 0.04),
                _inches(lbl_w), _inches(TOTALS_H)
            )
            tp = lbl_box.text_frame.paragraphs[0]
            tp.alignment = PP_ALIGN.LEFT
            tr = tp.add_run()
            tr.text = lbl_text
            tr.font.size = Pt(CHSZ)
            tr.font.bold = True
            tr.font.name = lm.FONT_NAME
            tr.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
            x_cur += DOT + GAP + lbl_w + IPAD


# ── Area-Line Chart helpers ───────────────────────────────────────────

def _set_series_markers(ser_el, color_hex: str, size: int = 5):
    """Add circular dot markers to a line series via XML."""
    h = color_hex.lstrip('#')
    for old in ser_el.findall(qn('c:marker')):
        ser_el.remove(old)
    mk = etree.SubElement(ser_el, qn('c:marker'))
    etree.SubElement(mk, qn('c:symbol')).set('val', 'circle')
    etree.SubElement(mk, qn('c:size')).set('val', str(size))
    sp = etree.SubElement(mk, qn('c:spPr'))
    sf = etree.SubElement(sp, qn('a:solidFill'))
    etree.SubElement(sf, qn('a:srgbClr')).set('val', h)
    ln = etree.SubElement(sp, qn('a:ln'))
    etree.SubElement(ln, qn('a:noFill'))


def _set_axis_label_rotation(axis, rot_angle: int):
    """Rotate axis tick labels. rot_angle in 1/60000 degrees (-2700000 = -45°)."""
    try:
        ax_el = axis._element
        for old in ax_el.findall(qn('c:txPr')):
            ax_el.remove(old)
        txPr = etree.SubElement(ax_el, qn('c:txPr'))
        bp = etree.SubElement(txPr, qn('a:bodyPr'))
        bp.set('rot', str(rot_angle))
        etree.SubElement(txPr, qn('a:lstStyle'))
        p = etree.SubElement(txPr, qn('a:p'))
        pPr = etree.SubElement(p, qn('a:pPr'))
        defRPr = etree.SubElement(pPr, qn('a:defRPr'))
        defRPr.set('sz', '700')
        defRPr.set('b', '0')
    except Exception:
        pass


def _style_major_gridlines(chart, color_hex: str = 'E5E7EB', width_pt: float = 0.5):
    """Style value-axis major gridlines to light gray."""
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        if plot_area is None:
            return
        for val_ax in plot_area.findall('.//' + qn('c:valAx')):
            for gl in val_ax.findall(qn('c:majorGridlines')):
                sp_pr = gl.find(qn('c:spPr'))
                if sp_pr is None:
                    sp_pr = etree.SubElement(gl, qn('c:spPr'))
                for old_ln in sp_pr.findall(qn('a:ln')):
                    sp_pr.remove(old_ln)
                ln = etree.SubElement(sp_pr, qn('a:ln'))
                ln.set('w', str(int(width_pt * 12700)))
                sf = etree.SubElement(ln, qn('a:solidFill'))
                etree.SubElement(sf, qn('a:srgbClr')).set('val', color_hex.lstrip('#'))
    except Exception:
        pass


def add_area_line_chart(slide, title: str, dates: list, values: list,
                        line_color: str = None, fill_color: str = None,
                        left_in=0, top_in=0, w_in=9, h_in=4):
    """
    Line chart with area fill below and circular data-point markers.
    Designed for daily time-series (date strings on x-axis).

    dates  : list of string labels ['2026-04-01', ...]
    values : numeric values matching dates

    If values are missing/empty but dates are known, the full chart frame
    (axes, date labels, title) is rendered as a flat zero-value line. If
    there are no dates at all either, a single "No Data" placeholder
    category is used so the chart frame itself is always shown.
    """
    if not dates:
        dates = ['No Data']
        values = [0.0]
    else:
        values = [float(v or 0) for v in values] if values else [0.0] * len(dates)

    _line = line_color or CLR_BLUE    # brand primary #00A550
    _fill = fill_color or '#E0F5EA'   # soft green area tint

    chart_data = CategoryChartData()
    chart_data.categories = dates
    chart_data.add_series('Threats', [float(v) for v in values])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        _inches(left_in), _inches(top_in),
        _inches(w_in), _inches(h_in),
        chart_data
    )
    chart = chart_frame.chart

    _set_chart_title(chart, title)
    chart.has_legend = False
    _remove_chart_border(chart)

    # Series: line color + area fill below
    series = chart.series[0]
    _set_series_line(series, _line, 1.5)
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = _rgb(_fill)

    # Circular dot markers
    _set_series_markers(series._element, _line, size=5)

    # Axes
    try:
        _style_axis(chart.category_axis, font_size=7)
        _style_axis(chart.value_axis, font_size=8)
        _set_axis_label_rotation(chart.category_axis, -2700000)   # -45°
        _set_axis_title(chart.category_axis, 'Date', font_size=8)
        _set_axis_title(chart.value_axis, 'Values', font_size=8)
        chart.value_axis.has_major_gridlines = True
        _style_major_gridlines(chart)
    except Exception:
        pass


# ── Dual-axis axis scaling helpers ────────────────────────────────────

def _nice_axis_bounds(values, divisions=6):
    """
    Return (nice_max, major_unit) both rounded to clean numbers.
    Uses same divisions count on both axes so gridlines align.
    """
    raw_max = max((v for v in values if v is not None), default=0)
    if raw_max <= 0:
        return float(divisions), 1.0
    raw_unit = raw_max / divisions
    magnitude = 10 ** math.floor(math.log10(raw_unit))
    nice_unit = math.ceil(raw_unit / magnitude) * magnitude
    nice_max  = nice_unit * divisions
    return float(nice_max), float(nice_unit)


def _apply_axis_bounds_xml(ax_el, nice_max, major_unit):
    """
    Write explicit min=0 / max / majorUnit onto a valAx XML element.
    Replaces any existing scaling children to avoid duplicates.
    """
    sc = ax_el.find(qn('c:scaling'))
    if sc is None:
        sc = etree.SubElement(ax_el, qn('c:scaling'))
        etree.SubElement(sc, qn('c:orientation')).set('val', 'minMax')
    for tag in (qn('c:max'), qn('c:min')):
        for old in sc.findall(tag):
            sc.remove(old)
    etree.SubElement(sc, qn('c:max')).set('val', str(nice_max))
    etree.SubElement(sc, qn('c:min')).set('val', '0')
    for old in ax_el.findall(qn('c:majorUnit')):
        ax_el.remove(old)
    etree.SubElement(ax_el, qn('c:majorUnit')).set('val', str(major_unit))


# ── Dual-axis Bar+Line Combo Chart ────────────────────────────────────

def add_dual_axis_bar_line_chart(
        slide, title, dates,
        bar_values, bar_label, bar_color,
        line_values, line_label, line_color,
        bar_axis_title='', line_axis_title='',
        left_in=0, top_in=0, w_in=9, h_in=4):
    """
    Clustered-bar on primary (left) y-axis + line with markers on secondary (right) y-axis.
    Intended for two series with very different value scales (e.g. Allowed vs Blocked).

    dates          : list of date strings, used as category labels
    bar_values     : values for the bar series (large scale — left axis)
    bar_label      : legend name for bars
    bar_color      : hex color for bars (e.g. CLR_BLUE)
    line_values    : values for the line series (small scale — right axis)
    line_label     : legend name for line
    line_color     : hex color for line (e.g. CLR_YELLOW)
    bar_axis_title : optional left y-axis label
    line_axis_title: optional right y-axis label
    """
    if not dates or not bar_values or not line_values:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    # Pre-compute nice axis bounds (same divisions → gridlines align)
    DIVISIONS = 6
    bar_max, bar_unit  = _nice_axis_bounds(bar_values,  DIVISIONS)
    line_max, line_unit = _nice_axis_bounds(line_values, DIVISIONS)

    # ── 1. Create bar chart with both series ──────────────────────────
    chart_data = CategoryChartData()
    chart_data.categories = dates
    chart_data.add_series(bar_label,  [float(v) for v in bar_values])
    chart_data.add_series(line_label, [float(v) for v in line_values])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        _inches(left_in), _inches(top_in),
        _inches(w_in), _inches(h_in),
        chart_data
    )
    chart = chart_frame.chart
    _set_chart_title(chart, title)
    _remove_chart_border(chart)

    # ── 2. Read axis IDs from the generated barChart ──────────────────
    plot_area = chart._element.find('.//' + qn('c:plotArea'))
    bar_chart  = plot_area.find(qn('c:barChart'))
    ax_id_els  = bar_chart.findall(qn('c:axId'))
    CAT_AX_ID  = ax_id_els[0].get('val')
    PRI_AX_ID  = ax_id_els[1].get('val')
    SEC_AX_ID  = str(int(PRI_AX_ID) + 100)

    # ── 3. Style bar series (solid fill, no border) ───────────────────
    bh = bar_color.lstrip('#')
    bar_sers = bar_chart.findall(qn('c:ser'))

    def _apply_fill(ser_el, hex_c, no_border=False):
        sp = ser_el.find(qn('c:spPr'))
        if sp is None:
            sp = etree.SubElement(ser_el, qn('c:spPr'))
        for tag in (qn('a:solidFill'), qn('a:gradFill'), qn('a:pattFill'),
                    qn('a:noFill'), qn('a:grpFill'), qn('a:blipFill')):
            for old in sp.findall(tag): sp.remove(old)
        for old in sp.findall(qn('a:ln')): sp.remove(old)
        etree.SubElement(etree.SubElement(sp, qn('a:solidFill')),
                         qn('a:srgbClr')).set('val', hex_c)
        if no_border:
            etree.SubElement(etree.SubElement(sp, qn('a:ln')), qn('a:noFill'))

    _apply_fill(bar_sers[0], bh, no_border=True)

    # ── 4. Extract second series and convert to line ──────────────────
    line_ser_el = bar_sers[1]
    bar_chart.remove(line_ser_el)

    lh = line_color.lstrip('#')
    lsp = line_ser_el.find(qn('c:spPr'))
    if lsp is None:
        lsp = etree.SubElement(line_ser_el, qn('c:spPr'))
    for tag in (qn('a:solidFill'), qn('a:gradFill'), qn('a:pattFill'),
                qn('a:noFill'), qn('a:grpFill'), qn('a:blipFill')):
        for old in lsp.findall(tag): lsp.remove(old)
    for old in lsp.findall(qn('a:ln')): lsp.remove(old)
    # Set line stroke
    ln_el = etree.SubElement(lsp, qn('a:ln'))
    ln_el.set('w', '19050')   # 1.5 pt
    etree.SubElement(
        etree.SubElement(ln_el, qn('a:solidFill')),
        qn('a:srgbClr')
    ).set('val', lh)
    # Remove bar-only elements
    for tag in (qn('c:invertIfNegative'), qn('c:shape')):
        for el in line_ser_el.findall(tag): line_ser_el.remove(el)
    # Circular markers
    _set_series_markers(line_ser_el, line_color, size=4)

    # ── 5. Insert lineChart element before the first axis ─────────────
    lc = etree.Element(qn('c:lineChart'))
    etree.SubElement(lc, qn('c:grouping')).set('val', 'standard')
    etree.SubElement(lc, qn('c:varyColors')).set('val', '0')
    lc.append(line_ser_el)
    etree.SubElement(lc, qn('c:smooth')).set('val', '0')
    etree.SubElement(lc, qn('c:axId')).set('val', CAT_AX_ID)
    etree.SubElement(lc, qn('c:axId')).set('val', SEC_AX_ID)

    _AX = {qn('c:catAx'), qn('c:valAx'), qn('c:dateAx'), qn('c:serAx')}
    first_ax = next((i for i, el in enumerate(plot_area) if el.tag in _AX),
                    len(list(plot_area)))
    plot_area.insert(first_ax, lc)

    # ── 6. Style existing category + primary value axes ───────────────
    try:
        _style_axis(chart.category_axis, font_size=7)
        _set_axis_label_rotation(chart.category_axis, -2700000)
        _set_axis_title(chart.category_axis, 'Date', font_size=8)
    except Exception:
        pass
    try:
        _style_axis(chart.value_axis, font_size=8)
        if bar_axis_title:
            _set_axis_title(chart.value_axis, bar_axis_title, font_size=8)
        chart.value_axis.has_major_gridlines = True
        _style_major_gridlines(chart)
        # Explicit min/max/unit so left axis starts at 0 with clean ticks
        chart.value_axis.minimum_scale = 0.0
        chart.value_axis.maximum_scale = bar_max
        chart.value_axis.major_unit    = bar_unit
    except Exception:
        pass

    # ── 7. Add secondary right Y-axis ─────────────────────────────────
    sec = etree.SubElement(plot_area, qn('c:valAx'))
    etree.SubElement(sec, qn('c:axId')).set('val', SEC_AX_ID)
    # Scaling with explicit min=0 / max / majorUnit — same divisions as left axis
    sc = etree.SubElement(sec, qn('c:scaling'))
    etree.SubElement(sc, qn('c:orientation')).set('val', 'minMax')
    etree.SubElement(sc, qn('c:max')).set('val', str(line_max))
    etree.SubElement(sc, qn('c:min')).set('val', '0')
    etree.SubElement(sec, qn('c:delete')).set('val', '0')
    etree.SubElement(sec, qn('c:axPos')).set('val', 'r')

    # Optional right axis title
    if line_axis_title:
        atx  = etree.SubElement(sec, qn('c:title'))
        tx   = etree.SubElement(atx, qn('c:tx'))
        rich = etree.SubElement(tx, qn('c:rich'))
        bp   = etree.SubElement(rich, qn('a:bodyPr'))
        bp.set('rot', '-5400000')   # -90°, reads top-to-bottom on right
        etree.SubElement(rich, qn('a:lstStyle'))
        rp   = etree.SubElement(rich, qn('a:p'))
        rr   = etree.SubElement(rp, qn('a:r'))
        rPr  = etree.SubElement(rr, qn('a:rPr'))
        rPr.set('lang', 'en-US')
        rPr.set('sz', '800')
        rPr.set('b', '0')
        etree.SubElement(rr, qn('a:t')).text = line_axis_title
        etree.SubElement(atx, qn('c:overlay')).set('val', '0')

    nf = etree.SubElement(sec, qn('c:numFmt'))
    nf.set('formatCode', 'General')
    nf.set('sourceLinked', '0')
    etree.SubElement(sec, qn('c:tickLblPos')).set('val', 'nextTo')
    etree.SubElement(sec, qn('c:majorUnit')).set('val', str(line_unit))

    # Thin gray axis line
    sp_sec = etree.SubElement(sec, qn('c:spPr'))
    ln_sec = etree.SubElement(
        etree.SubElement(sp_sec, qn('a:ln')), qn('a:solidFill'))
    etree.SubElement(ln_sec, qn('a:srgbClr')).set('val', 'D1D5DB')

    # 8pt font for tick labels
    txpr = etree.SubElement(sec, qn('c:txPr'))
    etree.SubElement(txpr, qn('a:bodyPr'))
    etree.SubElement(txpr, qn('a:lstStyle'))
    defR = etree.SubElement(
        etree.SubElement(
            etree.SubElement(txpr, qn('a:p')), qn('a:pPr')),
        qn('a:defRPr'))
    defR.set('sz', '800')
    defR.set('b', '0')

    etree.SubElement(sec, qn('c:crossAx')).set('val', CAT_AX_ID)
    etree.SubElement(sec, qn('c:crosses')).set('val', 'max')
    etree.SubElement(sec, qn('c:crossBetween')).set('val', 'between')

    # ── 8. Legend top-right, narrow gap ──────────────────────────────
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    try:
        chart.legend.font.size = Pt(8)
        chart.legend.font.name = lm.FONT_NAME
    except Exception:
        pass

    _set_gap_width(chart, 150)


# ── Stat Cards (shapes + text boxes) ─────────────────────────────────

def add_stat_cards(slide, title: str, cards: list,
                   left_in=0, top_in=0, w_in=5, h_in=5,
                   value_font_size: int = 22):
    """
    Displays stat cards using python-pptx shapes (editable in PowerPoint).
    cards: list of dicts with keys: label, value, subtitle, color (hex), bg_color (hex)
    Layout: auto-grid (max 2 cols).
    """
    if not cards:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    # Section title
    _add_section_title(slide, title, left_in, top_in, w_in)

    n = len(cards)
    cols = 2 if n > 2 else (1 if n == 1 else 2)
    rows = math.ceil(n / cols)

    title_h = 0.38
    gap = 0.12
    avail_h = h_in - title_h - gap * (rows + 1)
    avail_w = w_in - gap * (cols + 1)
    card_w = avail_w / cols
    card_h = min(avail_h / rows, 1.8)

    card_top_start = top_in + title_h + gap

    for idx, card in enumerate(cards):
        row = idx // cols
        col = idx % cols
        cx = left_in + gap + col * (card_w + gap)
        cy = card_top_start + row * (card_h + gap)

        card_color = card.get('color', PALETTE[idx % len(PALETTE)])
        bg_hex = card.get('bg_color', '#F9FAFA')
        bg_rgb = _rgb(bg_hex)

        # Card background
        shape = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(cx), _inches(cy),
            _inches(card_w), _inches(card_h)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg_rgb
        shape.line.fill.background()

        # Value (large number)
        val_top = cy + card_h * 0.15
        val_h = card_h * 0.45
        val_box = slide.shapes.add_textbox(
            _inches(cx + 0.1), _inches(val_top),
            _inches(card_w - 0.2), _inches(val_h)
        )
        tf = val_box.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(card.get('value', '—'))
        run.font.size = Pt(value_font_size)
        run.font.bold = True
        run.font.name = lm.FONT_NAME
        run.font.color.rgb = _rgb(card_color)

        # Label
        lbl_box = slide.shapes.add_textbox(
            _inches(cx + 0.1), _inches(cy + card_h * 0.6),
            _inches(card_w - 0.2), _inches(card_h * 0.22)
        )
        lp = lbl_box.text_frame.paragraphs[0]
        lp.alignment = PP_ALIGN.CENTER
        lr = lp.add_run()
        lr.text = card.get('label', '')
        lr.font.size = Pt(11)
        lr.font.bold = True
        lr.font.name = lm.FONT_NAME
        lr.font.color.rgb = lm.CLR_TEXT

        # Subtitle
        sub_text = card.get('subtitle', '')
        if sub_text:
            sub_box = slide.shapes.add_textbox(
                _inches(cx + 0.1), _inches(cy + card_h * 0.82),
                _inches(card_w - 0.2), _inches(card_h * 0.18)
            )
            sp = sub_box.text_frame.paragraphs[0]
            sp.alignment = PP_ALIGN.CENTER
            sr = sp.add_run()
            sr.text = sub_text
            sr.font.size = Pt(8)
            sr.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)


# ── Progress Bars (shapes) ────────────────────────────────────────────

def add_progress_bars(slide, title: str, items: list,
                      left_in=0, top_in=0, w_in=5, h_in=5):
    """
    Horizontal progress bars for SLA / success rates.
    items: list of {'label': str, 'value': float, 'target': float, 'unit': str}
    """
    if not items:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    _add_section_title(slide, title, left_in, top_in, w_in)

    n = len(items)
    title_h = 0.38
    spacing = (h_in - title_h) / n
    bar_h = min(spacing * 0.3, 0.22)
    bar_w = w_in - 1.2

    for i, item in enumerate(items):
        val    = float(item.get('value', 0))
        target = float(item.get('target', 100))
        label  = item.get('label', '')
        unit   = item.get('unit', '%')

        pct    = min(val / target, 1.0) if target > 0 else 0
        c_hex  = CLR_GREEN if pct >= 0.9 else (CLR_YELLOW if pct >= 0.7 else CLR_RED)

        block_top = top_in + title_h + i * spacing
        lbl_top   = block_top + spacing * 0.08
        bar_top   = block_top + spacing * 0.38
        val_top   = block_top + spacing * 0.64

        # Label
        lbl_box = slide.shapes.add_textbox(
            _inches(left_in + 0.1), _inches(lbl_top),
            _inches(w_in - 0.2), _inches(0.25)
        )
        lp = lbl_box.text_frame.paragraphs[0]
        lr = lp.add_run()
        lr.text = label
        lr.font.size = Pt(9)
        lr.font.color.rgb = lm.CLR_TEXT

        # Background bar
        bg = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            _inches(left_in + 0.1), _inches(bar_top),
            _inches(bar_w), _inches(bar_h)
        )
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(0xEE, 0xEE, 0xEE)
        bg.line.fill.background()

        # Foreground bar (value)
        if pct > 0:
            fg = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.RECTANGLE,
                _inches(left_in + 0.1), _inches(bar_top),
                _inches(bar_w * pct), _inches(bar_h)
            )
            fg.fill.solid()
            fg.fill.fore_color.rgb = _rgb(c_hex)
            fg.line.fill.background()

        # Value text (right of bar)
        vbox = slide.shapes.add_textbox(
            _inches(left_in + 0.1 + bar_w + 0.05), _inches(bar_top - 0.04),
            _inches(0.9), _inches(0.32)
        )
        vp = vbox.text_frame.paragraphs[0]
        vr = vp.add_run()
        vr.text = f"{val:.1f}{unit}"
        vr.font.size = Pt(10)
        vr.font.bold = True
        vr.font.color.rgb = _rgb(c_hex)

        # Target text
        if target != 100 or unit != '%':
            tbox = slide.shapes.add_textbox(
                _inches(left_in + 0.1), _inches(val_top),
                _inches(bar_w), _inches(0.22)
            )
            tp = tbox.text_frame.paragraphs[0]
            tr = tp.add_run()
            tr.text = f"Target: {target}{unit}"
            tr.font.size = Pt(8)
            tr.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)


# ── Gauge (half-donut via native doughnut chart) ───────────────────────

def add_gauge_chart(slide, title: str, value: float, max_val: float = 100,
                    label: str = '', color: str = None,
                    left_in=0, top_in=0, w_in=5, h_in=5):
    """
    Half-gauge implemented as a donut chart with [value, remaining, fill] pattern.
    'fill' segment (equal to max_val) is hidden below to create a half-circle effect.
    """
    if value is None:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    color = color or CLR_BLUE
    pct   = min(max(float(value) / float(max_val), 0.0), 1.0) if max_val else 0.0

    # 3 segments: value, remaining, bottom-half (hidden = same color as background)
    val_seg  = float(value)
    rem_seg  = float(max_val) - val_seg
    fill_seg = float(max_val)   # bottom hidden half

    chart_data = CategoryChartData()
    chart_data.categories = ['Value', 'Remaining', 'Hidden']
    chart_data.add_series('', [val_seg, rem_seg if rem_seg >= 0 else 0, fill_seg])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.DOUGHNUT,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in),
        chart_data
    )
    chart = chart_frame.chart
    _set_chart_title(chart, title)
    _hide_legend(chart)

    plot = chart.plots[0]
    try:
        plot.doughnut_hole_size = 55
    except Exception:
        pass

    # Rotate so "hidden" segment is at bottom (270° rotation = top start)
    try:
        pie_el = plot._element
        ser = pie_el.findall(qn('c:ser'))
        if ser:
            pass
        # Set first slice angle to 270 so hidden segment is at the bottom
        # This is done via XML: <c:firstSliceAng val="270"/>
        pie_of = pie_el.find(qn('c:dLbls'))
    except Exception:
        pass

    # Try to set rotation via XML
    try:
        plot_el = chart._element.find('.//' + qn('c:doughnutChart'))
        if plot_el is not None:
            fsa = plot_el.find(qn('c:firstSliceAng'))
            if fsa is None:
                fsa = etree.SubElement(plot_el, qn('c:firstSliceAng'))
            fsa.set('val', '270')
    except Exception:
        pass

    # Color slices
    try:
        pts = plot.series[0].points
        if len(pts) >= 1:
            pts[0].format.fill.solid()
            pts[0].format.fill.fore_color.rgb = _rgb(color)         # value
        if len(pts) >= 2:
            pts[1].format.fill.solid()
            pts[1].format.fill.fore_color.rgb = RGBColor(0xEE, 0xEE, 0xEE)  # remaining
        if len(pts) >= 3:
            pts[2].format.fill.solid()
            pts[2].format.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)  # hidden
    except Exception:
        pass

    # Value label overlay (text box on top of chart)
    val_str = f"{value:.1f}" if isinstance(value, float) else str(value)
    pct_str = f"{pct * 100:.0f}%"
    lbl_w   = 1.5
    lbl_h   = 0.5
    lbl_l   = left_in + (w_in - lbl_w) / 2
    lbl_t   = top_in + h_in * 0.45

    txt_box = slide.shapes.add_textbox(
        _inches(lbl_l), _inches(lbl_t), _inches(lbl_w), _inches(lbl_h)
    )
    tf = txt_box.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = val_str
    r.font.size = Pt(20)
    r.font.bold = True
    r.font.color.rgb = _rgb(color)

    if label:
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = label
        r2.font.size = Pt(8)
        r2.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)


# ── Security Risk Score — clean semicircle gauge ──────────────────────

def _draw_security_risk_gauge(score: float, max_val: float = 100,
                               monthly=None, quarterly=None,
                               impact_label: str = None,
                               w_px: int = 620, h_px: int = 390) -> BytesIO:
    """
    Clean semicircular gauge for security risk score.
    Zones: green (0-40%) → amber (40-75%) → red (75-100%).
    Filled arc shows current score. Large value + risk label centered.
    Monthly / Quarterly comparison shown at bottom.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Wedge, FancyBboxPatch

    pct = min(max(float(score) / float(max_val), 0.0), 1.0)

    # Single colour theme: #bdecf0 (light cyan-blue)
    score_clr  = '#bdecf0'   # filled arc + marker + score text
    _txt_clr   = '#1a8fa0'   # darker shade for readable text
    if impact_label:
        risk_label = impact_label
    elif pct >= 0.75:
        risk_label = 'High Risk'
    elif pct >= 0.40:
        risk_label = 'Medium Risk'
    else:
        risk_label = 'Low Risk'

    dpi = 100
    fig, ax = plt.subplots(figsize=(w_px / dpi, h_px / dpi))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-0.60, 1.35)
    ax.set_aspect('equal')
    ax.axis('off')

    R_OUT, R_IN = 1.0, 0.68      # ring thickness
    def _deg(p): return 180.0 - p * 180.0   # pct → degrees (180=left, 0=right)

    # Zone background rings — unfilled portion colour #9a9e99
    zone_bg = [
        (0.00, 0.40, '#9a9e99'),
        (0.40, 0.75, '#9a9e99'),
        (0.75, 1.00, '#9a9e99'),
    ]
    for z0, z1, bg in zone_bg:
        ax.add_patch(Wedge((0, 0), R_OUT, _deg(z1), _deg(z0),
                           width=R_OUT - R_IN,
                           facecolor=bg, edgecolor='white', linewidth=1.8, zorder=1))

    # Gradient filled arc: green (start/0) → black (end/score position)
    # Achieved by drawing N small wedge segments with interpolated colour
    if pct > 0.005:
        N_SEGS = 60
        _c_start = np.array([0x22 / 255, 0xC5 / 255, 0x5E / 255])  # #22C55E green
        _c_end   = np.array([0x10 / 255, 0x10 / 255, 0x10 / 255])  # near-black
        for k in range(N_SEGS):
            t0 = k       / N_SEGS * pct
            t1 = (k + 1) / N_SEGS * pct
            t  = k / max(N_SEGS - 1, 1)           # 0 → 1 (green → black)
            seg_clr = tuple(_c_start * (1 - t) + _c_end * t)
            ax.add_patch(Wedge((0, 0), R_OUT, _deg(t1), _deg(t0),
                               width=R_OUT - R_IN,
                               facecolor=seg_clr, edgecolor='none',
                               linewidth=0, zorder=2))

    # Zone boundary divider lines
    for boundary in [0.0, 0.40, 0.75, 1.0]:
        ang = np.radians(_deg(boundary))
        ax.plot([R_IN * np.cos(ang), R_OUT * np.cos(ang)],
                [R_IN * np.sin(ang), R_OUT * np.sin(ang)],
                color='white', linewidth=2.0, zorder=3)

    # Score position marker — black dot at end of gradient arc
    s_ang = np.radians(_deg(pct))
    mid_r = (R_OUT + R_IN) / 2
    ax.add_patch(plt.Circle(
        (mid_r * np.cos(s_ang), mid_r * np.sin(s_ang)),
        0.058, facecolor='white', edgecolor='#101010', linewidth=2.5, zorder=4))

    # Tick labels: 0%, 25%, 50%, 75%, 100%
    for frac, lbl in [(0.0, '0%'), (0.25, '25%'), (0.5, '50%'), (0.75, '75%'), (1.0, '100%')]:
        ang  = np.radians(_deg(frac))
        r_lbl = R_OUT + 0.19
        ax.text(r_lbl * np.cos(ang), r_lbl * np.sin(ang), lbl,
                ha='center', va='center', fontsize=7.5, color='#111111',
                fontfamily='DejaVu Sans', zorder=5)

    # Large score value centered below arc
    ax.text(0, 0.10, f"{score:.1f}",
            ha='center', va='center', fontsize=34, fontweight='bold',
            color='#111111', fontfamily='DejaVu Sans', zorder=6)

    # Risk label — supports "Level\nMessage" two-line format
    if risk_label and '\n' in risk_label:
        level_txt, msg_txt = risk_label.split('\n', 1)
        ax.text(0, -0.13, level_txt,
                ha='center', va='center', fontsize=10.5, fontweight='bold',
                color='#374050', fontfamily='DejaVu Sans', zorder=6)
        ax.text(0, -0.33, msg_txt,
                ha='center', va='center', fontsize=8.0,
                color='#6B7280', fontfamily='DejaVu Sans', zorder=6)
    else:
        ax.text(0, -0.18, risk_label or '',
                ha='center', va='center', fontsize=10.5, color='#6B7280',
                fontfamily='DejaVu Sans', zorder=6)

    # Monthly / Quarterly stats removed

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def add_security_risk_score(slide, title: str, score: float,
                             monthly=None, quarterly=None,
                             impact_label: str = None,
                             breakdown_stats=None,
                             left_in=0, top_in=0, w_in=5, h_in=5,
                             pic_left_in=None, pic_top_in=None,
                             pic_w_in=None, pic_h_in=None):
    """Universal semicircle gauge — used for any meter/risk score chart in the PPT.

    breakdown_stats: optional list of (label, value) tuples rendered as a 2×2
                     grid of stat boxes below the gauge (used by Bitdefender).
    """
    if score is None:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    _add_section_title(slide, title, left_in, top_in, w_in)

    buf = _draw_security_risk_gauge(
        score, monthly=monthly, quarterly=quarterly,
        impact_label=impact_label,
        w_px=620, h_px=390
    )

    _L_PAD = 0.461
    _T_PAD = 0.72

    # When breakdown stats are present, shrink the gauge to leave room for them
    STATS_AREA_H = 1.30   # inches reserved for the 2×2 stat grid
    # When breakdown stats are shown, use tighter vertical trim and narrow the image by 2 cm
    _BOTTOM_TRIM = 0.60 if breakdown_stats else 1.31
    _R_PAD       = 0.787 if breakdown_stats else 0.0   # 2 cm right padding → narrower
    gauge_h = h_in - _BOTTOM_TRIM - (STATS_AREA_H if breakdown_stats else 0)

    _pic_l = pic_left_in if pic_left_in is not None else left_in + _L_PAD
    _pic_t = pic_top_in  if pic_top_in  is not None else top_in  + _T_PAD
    _pic_w = pic_w_in    if pic_w_in    is not None else w_in - _L_PAD - _R_PAD
    _pic_h = pic_h_in    if pic_h_in    is not None else gauge_h
    slide.shapes.add_picture(
        buf,
        _inches(_pic_l), _inches(_pic_t),
        _inches(_pic_w), _inches(_pic_h)
    )

    # ── Breakdown stat boxes (2 columns × N/2 rows) ───────────────────────
    if breakdown_stats:
        stats_top   = top_in + _T_PAD + gauge_h + 0.08
        col_w       = (w_in - 0.1) / 2
        row_h       = 0.58
        row_gap     = 0.06
        cols        = 2

        for idx, (label, value) in enumerate(breakdown_stats):
            col = idx % cols
            row = idx // cols
            bx  = left_in + 0.05 + col * (col_w + 0.05)
            by  = stats_top + row * (row_h + row_gap)

            # Stat box background
            box = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
                _inches(bx), _inches(by), _inches(col_w), _inches(row_h)
            )
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(0xF3, 0xF4, 0xF6)
            box.line.color.rgb      = RGBColor(0xE5, 0xE7, 0xEB)
            box.line.width          = Pt(0.5)

            # Label text box (top portion)
            lbl_tf = slide.shapes.add_textbox(
                _inches(bx + 0.07), _inches(by + 0.05),
                _inches(col_w - 0.14), _inches(0.22)
            ).text_frame
            lbl_tf.word_wrap = True
            lbl_p  = lbl_tf.paragraphs[0]
            lbl_r  = lbl_p.add_run()
            lbl_r.text = label
            lbl_r.font.size   = Pt(8.5)
            lbl_r.font.name   = 'Times New Roman'
            lbl_r.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
            lbl_r.font.bold   = False

            # Value text box (bottom portion)
            val_tf = slide.shapes.add_textbox(
                _inches(bx + 0.07), _inches(by + 0.27),
                _inches(col_w - 0.14), _inches(0.26)
            ).text_frame
            val_p  = val_tf.paragraphs[0]
            val_r  = val_p.add_run()
            val_r.text = str(value) if value is not None else '—'
            val_r.font.size  = Pt(13)
            val_r.font.name  = 'Times New Roman'
            val_r.font.bold  = True
            val_r.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)


# ── Score Card (Bitdefender risk display) ─────────────────────────────

def add_score_card(slide, title: str, main_value: str, impact: str,
                   breakdown: dict, left_in=0, top_in=0, w_in=5, h_in=5):
    """
    Score card for Bitdefender risk score.
    breakdown: dict of {label: value_str}
    """
    if not main_value:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    # Outer card
    card = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in)
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xF9, 0xFA, 0xFA)
    card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)

    # Title
    _add_section_title(slide, title, left_in, top_in, w_in)

    # Impact level color
    impact_lower = (impact or '').lower()
    impact_color = CLR_RED if 'high' in impact_lower else (
        CLR_YELLOW if 'medium' in impact_lower else CLR_GREEN)

    # Main score (large)
    score_box = slide.shapes.add_textbox(
        _inches(left_in + 0.1), _inches(top_in + 0.5),
        _inches(w_in - 0.2), _inches(1.2)
    )
    tf = score_box.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(main_value)
    r.font.size = Pt(42)
    r.font.bold = True
    r.font.color.rgb = _rgb(impact_color)

    # Impact label
    if impact:
        imp_box = slide.shapes.add_textbox(
            _inches(left_in + 0.1), _inches(top_in + 1.7),
            _inches(w_in - 0.2), _inches(0.35)
        )
        ip = imp_box.text_frame.paragraphs[0]
        ip.alignment = PP_ALIGN.CENTER
        ir = ip.add_run()
        ir.text = f"Impact: {impact}"
        ir.font.size = Pt(10)
        ir.font.bold = True
        ir.font.color.rgb = _rgb(impact_color)

    # Breakdown items
    if breakdown:
        n     = len(breakdown)
        item_h = min((h_in - 2.2) / n, 0.55)
        for i, (k, v) in enumerate(breakdown.items()):
            iy = top_in + 2.2 + i * item_h
            ib = slide.shapes.add_textbox(
                _inches(left_in + 0.2), _inches(iy),
                _inches(w_in - 0.4), _inches(item_h)
            )
            tp = ib.text_frame.paragraphs[0]
            tr = tp.add_run()
            tr.text = f"{k}: {v}"
            tr.font.size = Pt(9)
            tr.font.color.rgb = lm.CLR_TEXT


# ── NodeWare Summary Card ─────────────────────────────────────────────

def _draw_gauge_image(value: float, max_val: float,
                      risk_label: str, gauge_color_hex: str,
                      w_px: int = 700, h_px: int = 460) -> BytesIO:
    """
    Render a speedometer-style half-donut gauge matching the NodeWare UI reference.
    Color scheme: dark-charcoal background arc, red fill up to score, green sliver at 0.
    Returns a BytesIO PNG image (white background).
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Polygon, FancyBboxPatch, Circle

    pct = min(max(float(value) / float(max_val), 0.0), 1.0) if max_val else 0.0

    dpi = 100
    fig, ax = plt.subplots(figsize=(w_px / dpi, h_px / dpi))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_xlim(-1.40, 1.40)
    ax.set_ylim(-0.60, 1.30)
    ax.set_aspect('equal')
    ax.axis('off')

    R_OUT = 1.00
    R_IN  = 0.60   # thick arc (matches reference image)
    N     = 400

    def _wedge(t0, t1, color, zo=1):
        """Draw a filled arc wedge from angle t0 to t1."""
        t  = np.linspace(t0, t1, N)
        xs = np.concatenate([R_OUT * np.cos(t), R_IN * np.cos(t[::-1])])
        ys = np.concatenate([R_OUT * np.sin(t), R_IN * np.sin(t[::-1])])
        ax.add_patch(Polygon(np.column_stack([xs, ys]), closed=True,
                             facecolor=color, edgecolor='none', zorder=zo))

    # Arc angles: π = left/0-end, 0 = right/max-end
    A_START = np.pi          # where 0 is (bottom-left of arc)
    A_END   = 0.0            # where max_val is (bottom-right of arc)
    A_SCORE = np.pi - pct * np.pi   # current score position

    # Layer 1 — Dark charcoal background (entire arc)
    _wedge(A_START, A_END, '#2D3748', zo=1)

    # Layer 2 — Red fill from 0 to score position
    if pct > 0.025:
        _wedge(A_START, A_SCORE, '#E53E3E', zo=2)

    # Layer 3 — Green sliver at the very start (0 mark), always shown
    _wedge(A_START, A_START - 0.028 * np.pi, '#22C55E', zo=3)

    # ── Tick labels: 0, 200, 500, 700, 1000 ─────────────────────────────────
    if max_val > 10:
        ticks = [(0.000, '0'), (0.200, '200'), (0.500, '500'),
                 (0.700, '700'), (1.000, '1000')]
    else:
        ticks = [(0.000, '0'), (0.200, '2'), (0.500, '5'),
                 (0.700, '7'), (1.000, '10')]

    for frac, lbl in ticks:
        angle = np.pi - frac * np.pi
        r_lbl = R_OUT + 0.16
        ax.text(r_lbl * np.cos(angle), r_lbl * np.sin(angle),
                lbl, ha='center', va='center',
                fontsize=7.5, color='#6B7280', fontfamily='DejaVu Sans')

    # ── Small hub circle at center ───────────────────────────────────────────
    ax.add_patch(Circle((0, 0), 0.085,
                        facecolor='#E2E8F0', edgecolor='none', zorder=5))

    # ── Score number — large, bold, dark ────────────────────────────────────
    score_str = f'{int(round(value))}' if max_val > 10 else f'{value:.1f}'
    ax.text(0, 0.12, score_str, ha='center', va='center',
            fontsize=34, fontweight='bold', color='#1A202C',
            fontfamily='DejaVu Sans', zorder=6)

    # ── Risk badge — outline only with color border ──────────────────────────
    bw, bh = 0.80, 0.21
    ax.add_patch(FancyBboxPatch((-bw / 2, -0.46), bw, bh,
                                boxstyle='round,pad=0.04',
                                facecolor='white',
                                edgecolor=gauge_color_hex, linewidth=1.8, zorder=6))
    ax.text(0, -0.46 + bh / 2, risk_label, ha='center', va='center',
            fontsize=8.5, fontweight='bold', color=gauge_color_hex,
            fontfamily='DejaVu Sans', zorder=7)

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='white', pad_inches=0.08)
    plt.close(fig)
    buf.seek(0)
    return buf


def _make_icon_png(icon_type: str, color_hex: str, size: int = 64) -> BytesIO:
    """
    Generate a simple icon as a transparent PNG using Pillow.
    icon_type: 'monitor'  — screen + stand + base  (Assets)
               'barchart' — 3 vertical bars          (Unique CVEs)
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    clr = (r, g, b, 255)

    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad  = max(4, size // 10)
    lw   = max(2, size // 18)

    if icon_type == 'monitor':
        sx, sy = pad, pad
        sw = size - pad * 2
        sh = int(sw * 0.62)
        draw.rectangle([sx, sy, sx + sw - 1, sy + sh - 1], outline=clr, width=lw)
        cx2      = size // 2
        st_top   = sy + sh
        st_bot   = st_top + max(3, size // 9)
        draw.rectangle([cx2 - lw, st_top, cx2 + lw, st_bot], fill=clr)
        bw = sw // 2
        bx = cx2 - bw // 2
        draw.rectangle([bx, st_bot, bx + bw, st_bot + lw * 2], fill=clr)

    elif icon_type == 'barchart':
        avail_w = size - pad * 2
        bar_w   = max(4, avail_w // 4)
        gap     = max(2, avail_w // 8)
        total_w = 3 * bar_w + 2 * gap
        start_x = pad + (avail_w - total_w) // 2
        bot_y   = size - pad
        for j, frac in enumerate([0.40, 0.65, 1.00]):
            bx2 = start_x + j * (bar_w + gap)
            bh  = int((size - pad * 2) * frac)
            by  = bot_y - bh
            draw.rectangle([bx2, by, bx2 + bar_w - 1, bot_y - 1], fill=clr)

    elif icon_type == 'storage':
        # Server/HDD icon: box outline with 3 horizontal slot lines inside
        bx = pad
        by = pad + size // 10
        bw = size - pad * 2
        bh = size - pad * 2 - size // 10
        draw.rectangle([bx, by, bx + bw, by + bh], outline=clr, width=lw)
        # 3 horizontal slot lines evenly spaced inside the box
        slot_gap = bh // 4
        for si in range(3):
            sy = by + slot_gap * (si + 1)
            draw.line([bx + lw * 2, sy, bx + bw - lw * 2, sy], fill=clr, width=lw)

    elif icon_type == 'envelope':
        # Simple email envelope
        ex, ey = pad, pad + size // 6
        ew = size - pad * 2
        eh = size - pad * 2 - size // 6
        draw.rectangle([ex, ey, ex + ew, ey + eh], outline=clr, width=lw)
        # V flap
        mx = ex + ew // 2
        draw.line([ex, ey, mx, ey + eh // 2], fill=clr, width=lw)
        draw.line([ex + ew, ey, mx, ey + eh // 2], fill=clr, width=lw)

    elif icon_type == 'envelope_shared':
        # Envelope body (slightly smaller to leave room for share indicator)
        ex, ey = pad, pad + size // 8
        ew = size - pad * 2
        eh = int((size - pad * 2) * 0.60)
        draw.rectangle([ex, ey, ex + ew, ey + eh], outline=clr, width=lw)
        mx = ex + ew // 2
        draw.line([ex, ey, mx, ey + eh // 3], fill=clr, width=lw)
        draw.line([ex + ew, ey, mx, ey + eh // 3], fill=clr, width=lw)
        # Two person-head dots at bottom to indicate "shared"
        r_h  = max(2, size // 14)
        cy_s = ey + eh + r_h * 2 + lw
        for ox in [ew // 3, ew * 2 // 3]:
            px = ex + ox
            draw.ellipse([px - r_h, cy_s - r_h, px + r_h, cy_s + r_h], fill=clr)
            # Tiny shoulder arc
            draw.arc([px - r_h * 2, cy_s, px + r_h * 2, cy_s + r_h * 3],
                     start=210, end=330, fill=clr, width=lw)

    elif icon_type == 'cloud':
        # Solid filled cloud shape: three bumps at top + filled rectangle base
        cx2  = size // 2
        top  = size * 2 // 5
        r_c  = size // 5          # centre bump
        r_l  = int(size * 0.14)   # left bump
        r_r  = int(size * 0.16)   # right bump
        draw.ellipse([cx2 - r_c, top - r_c, cx2 + r_c, top + r_c], fill=clr)
        draw.ellipse([cx2 - r_c - r_l + 1, top - 1,
                      cx2 - r_c + r_l + 1, top + r_l * 2 - 1], fill=clr)
        draw.ellipse([cx2 + r_c - r_r - 1, top - 1,
                      cx2 + r_c + r_r - 1, top + r_r * 2 - 1], fill=clr)
        # Rectangle base to complete cloud silhouette
        bx1 = cx2 - r_c - r_l + 1
        bx2 = cx2 + r_c + r_r - 1
        by1 = top
        by2 = top + r_c + max(r_l, r_r) + pad // 2
        draw.rectangle([bx1, by1, bx2, by2], fill=clr)

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def add_nodeware_summary_card(slide, metrics: dict,
                              left_in=0, top_in=0, w_in=5, h_in=5,
                              compact_cards=False, gauge_w_override=None):
    """
    NodeWare vulnerability summary — original layout (gauge left, stat cards right)
    with the semicircle meter UI from _draw_security_risk_gauge.

    All values default to 0 via metrics.get(...) — always renders the gauge
    at 0 and stat cards at 0 rather than falling back to a placeholder box.
    """
    metrics = metrics or {}

    avg   = float(metrics.get('average_score', 0) or 0)
    MAX_S = 1000.0 if avg > 10 else 10.0

    if   avg < 450:              risk_label = "Average Score"
    elif avg <= 950:             risk_label = "Medium Score"
    else:                        risk_label = "Good Score"

    # ── Layout constants ──────────────────────────────────────────────────
    GAUGE_H_FRAC = 0.52
    GAUGE_GAP    = 0.11

    gauge_w   = gauge_w_override if gauge_w_override is not None else w_in * 0.404
    gauge_h   = h_in * GAUGE_H_FRAC + 1 / 2.54
    gauge_top = top_in + (h_in - gauge_h) / 2

    if compact_cards:
        CARD_W   = w_in - gauge_w - GAUGE_GAP
        CARD_H   = 0.52
        CARD_GAP = 0.12
        OVAL_SZ  = 0.30
        OVAL_PAD = 0.10
        ICO_SZ   = 0.17
    else:
        CARD_W   = min(w_in * 0.492, 4.72)
        CARD_H   = 0.76
        CARD_GAP = 0.22
        OVAL_SZ  = 0.42
        OVAL_PAD = 0.14
        ICO_SZ   = 0.24

    ICO_OFF = (OVAL_SZ - ICO_SZ) / 2
    TEXT_X  = OVAL_PAD + OVAL_SZ + 0.10

    # ── Gauge title ───────────────────────────────────────────────────────
    _add_section_title(slide, "Summery Metrics", left_in, top_in, gauge_w)

    # ── Gauge image — new semicircle UI, same position as before ─────────
    gauge_buf = _draw_security_risk_gauge(
        avg, max_val=MAX_S,
        impact_label=risk_label,
        w_px=700, h_px=460
    )
    slide.shapes.add_picture(
        gauge_buf,
        _inches(left_in), _inches(gauge_top),
        _inches(gauge_w), _inches(gauge_h)
    )

    # ── Stat cards (right side) ───────────────────────────────────────────
    cards_x       = left_in + gauge_w + GAUGE_GAP
    total_cards_h = 2 * CARD_H + CARD_GAP
    card1_top     = top_in + (h_in - total_cards_h) / 2
    card2_top     = card1_top + CARD_H + CARD_GAP

    card_defs = [
        ('Assets',      str(metrics.get('assets',      0)), '#DCFBE7', '#22C55E', 'monitor'),
        ('Unique CVEs', str(metrics.get('unique_cves', 0)), '#DCFBE7', '#22C55E', 'barchart'),
    ]

    for (label_text, value_text, oval_bg, icon_clr, icon_type), cy in zip(
            card_defs, [card1_top, card2_top]):
        cx = cards_x
        cw = CARD_W
        ch = CARD_H

        card_bg = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(cx), _inches(cy), _inches(cw), _inches(ch)
        )
        card_bg.fill.solid()
        card_bg.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        card_bg.line.color.rgb      = RGBColor(0xE5, 0xE7, 0xEB)
        card_bg.line.width          = Pt(1)

        oval_top = cy + (ch - OVAL_SZ) / 2
        oval = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.OVAL,
            _inches(cx + OVAL_PAD), _inches(oval_top),
            _inches(OVAL_SZ), _inches(OVAL_SZ)
        )
        oval.fill.solid()
        oval.fill.fore_color.rgb = _rgb(oval_bg)
        oval.line.fill.background()

        icon_buf = _make_icon_png(icon_type, icon_clr, size=64)
        if icon_buf:
            slide.shapes.add_picture(
                icon_buf,
                _inches(cx + OVAL_PAD + ICO_OFF),
                _inches(oval_top + ICO_OFF),
                _inches(ICO_SZ), _inches(ICO_SZ)
            )

        lbl_top = 0.07 if compact_cards else 0.10
        val_top = 0.22 if compact_cards else 0.30
        lbl_h   = 0.18 if compact_cards else 0.22
        val_h   = 0.26 if compact_cards else 0.40

        tb_lbl = slide.shapes.add_textbox(
            _inches(cx + TEXT_X), _inches(cy + lbl_top),
            _inches(cw - TEXT_X - 0.08), _inches(lbl_h)
        )
        p_lbl = tb_lbl.text_frame.paragraphs[0]
        r_lbl = p_lbl.add_run()
        r_lbl.text           = label_text
        r_lbl.font.name      = lm.FONT_NAME
        r_lbl.font.size      = Pt(7) if compact_cards else Pt(8)
        r_lbl.font.color.rgb = _rgb('#6A7280')

        tb_val = slide.shapes.add_textbox(
            _inches(cx + TEXT_X), _inches(cy + val_top),
            _inches(cw - TEXT_X - 0.08), _inches(val_h)
        )
        p_val = tb_val.text_frame.paragraphs[0]
        r_val = p_val.add_run()
        r_val.text           = value_text
        r_val.font.name      = lm.FONT_NAME
        r_val.font.size      = Pt(13) if compact_cards else Pt(18)
        r_val.font.bold      = True
        r_val.font.color.rgb = _rgb('#374050')


# ── Patch Summary (NinjaOne specific) ────────────────────────────────

def _draw_patch_panel(slide, d: dict, panel_title: str, panel_x, panel_y,
                      panel_w=4.47, panel_h=3.00, max_h=None):
    """Draw one patch summary panel matching original PPT slide 31 design."""
    s       = d.get('summary', {})
    total   = s.get('total', 0)
    success = s.get('successful', 0)
    failed  = s.get('failed', 0)
    rate    = float(s.get('success_rate', 100.0))

    failed_devs = d.get('failed_devices', [])
    top_dev = (failed_devs[0].get('device_name', failed_devs[0].get('device', 'No failed devices'))
               if failed_devs else 'No failed devices')
    status_text = 'All devices successful' if failed == 0 else f'{failed} device(s) failed'

    # ── Failed Devices list layout ────────────────────────────────────
    list_start_y = 3.14
    row_h        = 0.22
    bottom_pad   = 0.15
    BASE_H       = 3.24
    col_gap      = 0.10
    list_w       = 4.07
    device_names = [
        str(device.get('device_name', device.get('device', '')) or '')
        for device in failed_devs
    ]

    def estimated_name_width(name, font_size=8):
        return len(name) * font_size * 0.52 / 72.0

    two_column_w = (list_w - col_gap) / 2
    use_two_columns = bool(device_names) and max(
        estimated_name_width(name) for name in device_names
    ) <= two_column_w - 0.03
    columns = 2 if use_two_columns else 1
    col_w = two_column_w if use_two_columns else list_w

    devices_to_show = device_names
    truncated_count = 0

    if device_names:
        total_count = len(device_names)
        rows_needed = math.ceil(total_count / columns)
        required_panel_h = max(
            BASE_H,
            list_start_y + rows_needed * row_h + bottom_pad
        )
        panel_h = min(required_panel_h, max_h) if max_h else required_panel_h

        if max_h and required_panel_h > max_h:
            available_rows = max(
                0,
                int((panel_h - list_start_y - bottom_pad) / row_h)
            )
            capacity = available_rows * columns
            if capacity < total_count:
                visible_count = max(0, capacity - 1)
                devices_to_show = device_names[:visible_count]
                truncated_count = total_count - visible_count

    px, py = panel_x, panel_y

    # ── Panel background ──────────────────────────────────────────────
    bg = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(px), _inches(py), _inches(panel_w), _inches(panel_h)
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    bg.line.color.rgb      = RGBColor(0xE2, 0xE8, 0xF0)
    bg.line.width          = Pt(1)

    # ── Title row ─────────────────────────────────────────────────────
    tb_title = slide.shapes.add_textbox(
        _inches(px + 0.20), _inches(py + 0.20),
        _inches(2.30), _inches(0.28)
    )
    p = tb_title.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = panel_title
    r.font.name  = lm.FONT_NAME
    r.font.size  = Pt(9)
    r.font.bold  = True
    r.font.color.rgb = _rgb('#374050')

    tb_status = slide.shapes.add_textbox(
        _inches(px + 2.57), _inches(py + 0.20),
        _inches(1.70), _inches(0.28)
    )
    ps = tb_status.text_frame.paragraphs[0]
    ps.alignment = PP_ALIGN.RIGHT
    rs = ps.add_run()
    rs.text = status_text
    rs.font.name  = lm.FONT_NAME
    rs.font.size  = Pt(8)
    rs.font.color.rgb = _rgb('#16A34A') if failed == 0 else _rgb('#DC2626')

    # ── Divider 1 ─────────────────────────────────────────────────────
    def _divider(y_off):
        div = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            _inches(px + 0.20), _inches(py + y_off),
            _inches(4.07), _inches(0.01)
        )
        div.fill.solid()
        div.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
        div.line.fill.background()

    _divider(0.55)

    # ── Stat boxes ────────────────────────────────────────────────────
    box_w = 1.985
    box_h = 0.90

    # Successful box
    sb_shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(px + 0.20), _inches(py + 0.59),
        _inches(box_w), _inches(box_h)
    )
    sb_shape.fill.solid()
    sb_shape.fill.fore_color.rgb = RGBColor(0xF0, 0xFD, 0xF4)
    sb_shape.line.color.rgb      = RGBColor(0xE2, 0xE8, 0xF0)

    tb_s_num = slide.shapes.add_textbox(
        _inches(px + 0.25), _inches(py + 0.69),
        _inches(box_w - 0.10), _inches(0.42)
    )
    p_sn = tb_s_num.text_frame.paragraphs[0]
    p_sn.alignment = PP_ALIGN.CENTER
    r_sn = p_sn.add_run()
    r_sn.text = str(success)
    r_sn.font.name  = lm.FONT_NAME
    r_sn.font.size  = Pt(22)
    r_sn.font.bold  = True
    r_sn.font.color.rgb = _rgb('#16A34A')

    tb_s_lbl = slide.shapes.add_textbox(
        _inches(px + 0.25), _inches(py + 1.17),
        _inches(box_w - 0.10), _inches(0.24)
    )
    p_sl = tb_s_lbl.text_frame.paragraphs[0]
    p_sl.alignment = PP_ALIGN.CENTER
    r_sl = p_sl.add_run()
    r_sl.text = 'Successful'
    r_sl.font.name  = lm.FONT_NAME
    r_sl.font.size  = Pt(8)
    r_sl.font.color.rgb = _rgb('#6A7280')

    # Failed box
    fail_box_x = px + 0.20 + box_w + 0.10
    fb_fill = '#FEF2F2' if failed > 0 else '#F8FAFC'
    fb_border = '#FECACA' if failed > 0 else '#E2E8F0'
    fb_shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(fail_box_x), _inches(py + 0.59),
        _inches(box_w), _inches(box_h)
    )
    fb_shape.fill.solid()
    fb_shape.fill.fore_color.rgb = _rgb(fb_fill)
    fb_shape.line.color.rgb      = _rgb(fb_border)

    tb_f_num = slide.shapes.add_textbox(
        _inches(fail_box_x + 0.05), _inches(py + 0.69),
        _inches(box_w - 0.10), _inches(0.42)
    )
    p_fn = tb_f_num.text_frame.paragraphs[0]
    p_fn.alignment = PP_ALIGN.CENTER
    r_fn = p_fn.add_run()
    r_fn.text = str(failed)
    r_fn.font.name  = lm.FONT_NAME
    r_fn.font.size  = Pt(22)
    r_fn.font.bold  = True
    r_fn.font.color.rgb = _rgb('#DC2626')

    tb_f_lbl = slide.shapes.add_textbox(
        _inches(fail_box_x + 0.05), _inches(py + 1.17),
        _inches(box_w - 0.10), _inches(0.24)
    )
    p_fl = tb_f_lbl.text_frame.paragraphs[0]
    p_fl.alignment = PP_ALIGN.CENTER
    r_fl = p_fl.add_run()
    r_fl.text = 'Failed'
    r_fl.font.name  = lm.FONT_NAME
    r_fl.font.size  = Pt(8)
    r_fl.font.color.rgb = _rgb('#6A7280')

    # ── Divider 2 ─────────────────────────────────────────────────────
    _divider(1.63)

    # ── Info row 1: Total Patches ─────────────────────────────────────
    def _info_row(label, value, y_off):
        tbl = slide.shapes.add_textbox(
            _inches(px + 0.20), _inches(py + y_off),
            _inches(2.0), _inches(0.26)
        )
        pl = tbl.text_frame.paragraphs[0]
        rl = pl.add_run()
        rl.text = label
        rl.font.name  = lm.FONT_NAME
        rl.font.size  = Pt(8.5)
        rl.font.color.rgb = _rgb('#374050')

        tbv = slide.shapes.add_textbox(
            _inches(px + 2.32), _inches(py + y_off),
            _inches(1.95), _inches(0.26)
        )
        pv = tbv.text_frame.paragraphs[0]
        rv = pv.add_run()
        rv.text = str(value)
        rv.font.name  = lm.FONT_NAME
        rv.font.size  = Pt(8.5)
        rv.font.bold  = True
        rv.font.color.rgb = _rgb('#374050')

    _info_row('Total Patches:', total, 1.69)
    _divider(1.95)

    # ── Info row 2: Top Failed Device ────────────────────────────────
    top_label_w = 1.25
    top_value_x = 1.55
    top_value_w = list_w - (top_value_x - 0.20)
    tbl2 = slide.shapes.add_textbox(
        _inches(px + 0.20), _inches(py + 1.97),
        _inches(top_label_w), _inches(0.26)
    )
    pl2 = tbl2.text_frame.paragraphs[0]
    rl2 = pl2.add_run()
    rl2.text = 'Top Failed Device:'
    rl2.font.name  = lm.FONT_NAME
    rl2.font.size  = Pt(8.5)
    rl2.font.color.rgb = _rgb('#374050')

    tbv2 = slide.shapes.add_textbox(
        _inches(px + top_value_x), _inches(py + 1.97),
        _inches(top_value_w), _inches(0.26)
    )
    tbv2.text_frame.word_wrap = False
    pv2 = tbv2.text_frame.paragraphs[0]
    rv2 = pv2.add_run()
    top_font_size = min(
        8.5,
        (top_value_w - 0.06) * 72.0 / max(1, len(top_dev) * 0.52)
    )
    top_font_size = max(6.0, top_font_size)
    top_dev_display = top_dev
    if estimated_name_width(top_dev_display, top_font_size) > top_value_w - 0.06:
        max_chars = max(4, int((top_value_w - 0.06) * 72.0 / (top_font_size * 0.52)))
        top_dev_display = f"{top_dev[:max_chars - 3].rstrip()}..."
    rv2.text = top_dev_display
    rv2.font.name  = lm.FONT_NAME
    rv2.font.size  = Pt(top_font_size)
    rv2.font.color.rgb = _rgb('#374050')

    _divider(2.33)

    # ── Progress section ─────────────────────────────────────────────
    tb_sr_lbl = slide.shapes.add_textbox(
        _inches(px + 0.20), _inches(py + 2.39),
        _inches(3.0), _inches(0.26)
    )
    p_sr = tb_sr_lbl.text_frame.paragraphs[0]
    r_sr = p_sr.add_run()
    r_sr.text = 'Success Rate'
    r_sr.font.name  = lm.FONT_NAME
    r_sr.font.size  = Pt(8.5)
    r_sr.font.color.rgb = _rgb('#374050')

    tb_sr_val = slide.shapes.add_textbox(
        _inches(px + 3.57), _inches(py + 2.39),
        _inches(0.70), _inches(0.26)
    )
    p_sv = tb_sr_val.text_frame.paragraphs[0]
    p_sv.alignment = PP_ALIGN.RIGHT
    r_sv = p_sv.add_run()
    r_sv.text = f'{rate:.0f}%'
    r_sv.font.name  = lm.FONT_NAME
    r_sv.font.size  = Pt(8.5)
    r_sv.font.bold  = True
    r_sv.font.color.rgb = _rgb('#374050')

    # Progress track
    track = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(px + 0.20), _inches(py + 2.63),
        _inches(4.07), _inches(0.13)
    )
    track.fill.solid()
    track.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
    track.line.fill.background()

    # Progress fill
    fill_w = 4.07 * max(0.0, min(1.0, rate / 100.0))
    if fill_w > 0.01:
        fill = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(px + 0.20), _inches(py + 2.63),
            _inches(fill_w), _inches(0.13)
        )
        fill.fill.solid()
        fill.fill.fore_color.rgb = RGBColor(0x3B, 0x82, 0xF6)
        fill.line.fill.background()

    # ── Failed Devices list ───────────────────────────────────────────
    if failed_devs:
        _divider(2.82)

        tb_fd_lbl = slide.shapes.add_textbox(
            _inches(px + 0.20), _inches(py + 2.88),
            _inches(3.87), _inches(0.24)
        )
        p_fd = tb_fd_lbl.text_frame.paragraphs[0]
        r_fd = p_fd.add_run()
        r_fd.text = 'Failed Devices:'
        r_fd.font.name  = lm.FONT_NAME
        r_fd.font.size  = Pt(8.5)
        r_fd.font.bold  = True
        r_fd.font.color.rgb = _rgb('#374050')

        display_items = list(devices_to_show)
        if truncated_count > 0:
            display_items.append(f'+{truncated_count} more')

        n_display    = len(display_items)
        rows_per_col = max(1, math.ceil(n_display / columns))

        for i, dev in enumerate(display_items):
            col = i % columns
            row = i // columns
            item_x = px + 0.20 + col * (col_w + col_gap)
            item_y = py + list_start_y + row * row_h

            tb_dev = slide.shapes.add_textbox(
                _inches(item_x), _inches(item_y),
                _inches(col_w), _inches(row_h)
            )
            tb_dev.text_frame.word_wrap = False
            p_dev = tb_dev.text_frame.paragraphs[0]
            r_dev = p_dev.add_run()
            r_dev.text = dev
            if dev.startswith('+') and dev.endswith(' more'):
                r_dev.font.italic = True
                r_dev.font.color.rgb = _rgb('#6B7280')
            else:
                r_dev.font.color.rgb = _rgb('#374050')
                if not use_two_columns:
                    fitted_size = (col_w - 0.03) * 72.0 / max(1, len(dev) * 0.52)
                    r_dev.font.size = Pt(min(8, fitted_size))
            r_dev.font.name  = lm.FONT_NAME
            if r_dev.font.size is None:
                r_dev.font.size = Pt(8)


def add_patch_summary(slide, title: str, os_data: dict, tp_data: dict,
                      left_in=0, top_in=0, w_in=5, h_in=5):
    if not os_data and not tp_data:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    panel_w = 4.47
    panel_h = 3.00

    left_panel_x  = left_in + 0.22
    right_panel_x = left_in + 0.22 + panel_w + 0.22

    # ~1cm gap between the panel and whatever sits above it (e.g. the slide
    # header) — top_in already accounts for the header's own height, so this
    # is just the small extra breathing room below it.
    TOP_OFFSET = 0.29
    panel_y    = top_in + TOP_OFFSET

    # Real vertical room left in the slot below the panel's top offset,
    # minus a small bottom margin so the panel never touches the footer.
    max_panel_h = h_in - TOP_OFFSET - 0.10

    _draw_patch_panel(
        slide, os_data or {},
        "Status of OS patches",
        left_panel_x, panel_y, panel_w, panel_h, max_h=max_panel_h
    )
    _draw_patch_panel(
        slide, tp_data or {},
        "Status of 3rd Party Patches",
        right_panel_x, panel_y, panel_w, panel_h, max_h=max_panel_h
    )

# ── Info Card (text-only metric display) ─────────────────────────────

def add_info_card(slide, title: str, message: str, sub: str = '',
                  color: str = CLR_GREEN, left_in=0, top_in=0, w_in=5, h_in=5):
    """Simple full-area info card (e.g., 'All devices successful')."""
    bg = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in)
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0xF0, 0xFD, 0xF4)
    bg.line.color.rgb = _rgb(CLR_GREEN)

    _add_section_title(slide, title, left_in, top_in, w_in)

    msg_box = slide.shapes.add_textbox(
        _inches(left_in + 0.2), _inches(top_in + h_in / 2 - 0.4),
        _inches(w_in - 0.4), _inches(0.6)
    )
    mp = msg_box.text_frame.paragraphs[0]
    mp.alignment = PP_ALIGN.CENTER
    mr = mp.add_run()
    mr.text = message
    mr.font.size = Pt(14)
    mr.font.bold = True
    mr.font.color.rgb = _rgb(color)

    if sub:
        p2 = msg_box.text_frame.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = sub
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)


# ── Stacked Horizontal Bar (Issue / Sub-Issue breakdown) ─────────────

def add_stacked_issue_bar(slide, title: str, issue_data: list,
                          left_in=0, top_in=0, w_in=5, h_in=5,
                          show_legend=True):
    """
    Native BAR_STACKED chart for open_tickets_by_issue_type.
    issue_data : list of {issue_type, total_count, sub_issues:[{sub_issue_type, count}]}
    Y-axis = issue_type labels (truncated to fit), each bar split by sub_issue colour.
    show_legend: set False to hide the sub-issue legend (e.g. on dense combined slides).

    There is no fixed taxonomy of issue types to fall back on (unlike
    priority levels), so when issue_data is empty we still render the full
    chart frame — title, axes — using a single placeholder "No Data"
    category/series at value 0, instead of a generic placeholder box.
    """
    if not issue_data:
        issue_data = [{'issue_type': 'No Data', 'total_count': 0, 'sub_issues': []}]

    # Collect unique sub-issue names
    all_subs = []
    for item in issue_data:
        for si in item.get('sub_issues', []):
            sn = si.get('sub_issue_type', 'Other')
            if sn not in all_subs:
                all_subs.append(sn)
    if not all_subs:
        all_subs = ['No Data']

    # Truncate long category labels so they don't overflow the chart frame
    MAX_CAT = 20
    categories = []
    for item in issue_data:
        raw = item.get('issue_type', '')
        categories.append(raw[:MAX_CAT] + '\u2026' if len(raw) > MAX_CAT else raw)

    title_h = 0.38
    _add_section_title(slide, title, left_in, top_in, w_in)
    chart_top = top_in + title_h
    chart_h   = h_in - title_h          # full remaining height — legend is inside chart

    # Generate exactly len(all_subs) unique colors — dark green → light green (brand theme).
    # Interpolation guarantees no repetition regardless of sub-issue count.
    def _green_shades(n: int) -> list:
        if n <= 0:
            return []
        # Brand green anchors: dark #3e7564 → light #c5e364
        r1, g1, b1 = 0x3E, 0x75, 0x64   # #3e7564  dark green
        r2, g2, b2 = 0xC5, 0xE3, 0x64   # #c5e364  light green
        if n == 1:
            return [f'#{r1:02X}{g1:02X}{b1:02X}']
        return [
            f'#{int(r1+(r2-r1)*i/(n-1)):02X}'
            f'{int(g1+(g2-g1)*i/(n-1)):02X}'
            f'{int(b1+(b2-b1)*i/(n-1)):02X}'
            for i in range(n)
        ]

    sub_colors = _green_shades(len(all_subs))

    chart_data = CategoryChartData()
    chart_data.categories = categories
    for sub_name in all_subs:
        vals = []
        for item in issue_data:
            sub_map = {si['sub_issue_type']: si['count']
                       for si in item.get('sub_issues', [])}
            vals.append(float(sub_map.get(sub_name, 0)))
        chart_data.add_series(sub_name, vals)

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_STACKED,
        _inches(left_in), _inches(chart_top), _inches(w_in), _inches(chart_h),
        chart_data
    )
    _remove_chart_background(chart_frame)
    chart = chart_frame.chart
    chart.has_title = False

    # Auto-scale gap width: fewer gaps as more categories, so bars stay readable
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        for bar_el in plot_area.findall(qn('c:barChart')):
            gw = bar_el.find(qn('c:gapWidth'))
            if gw is None:
                gw = etree.SubElement(bar_el, qn('c:gapWidth'))
            gw.set('val', '150')
    except Exception:
        pass

    # Native corner legend — inside chart frame, no overflow risk
    if show_legend:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.CORNER
        chart.legend.include_in_layout = False
        try:
            chart.legend.font.size = Pt(7)
            chart.legend.font.name = lm.FONT_NAME
        except Exception:
            pass
    else:
        chart.has_legend = False

    # Color each series
    for i, series in enumerate(chart.series):
        try:
            clr = sub_colors[i % len(sub_colors)]
            _color_series(series, clr)
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = _rgb(clr)
        except Exception:
            pass

    # Data labels: black 7pt, suppress zeros via per-point XML delete
    # OOXML schema requires <c:dLbl> elements BEFORE <c:showXxx> in <c:dLbls>
    try:
        plot = chart.plots[0]
        plot.has_data_labels = True
        dls = plot.data_labels
        dls.show_value       = True
        dls.show_percentage  = False
        dls.show_series_name = False
        _LABEL_SZ = 670   # 6.7pt in hundredths-of-a-point (OOXML unit)
        dls.font.size        = Pt(6.7)
        dls.font.bold        = True
        dls.font.color.rgb   = RGBColor(0x00, 0x00, 0x00)

        _ADRAWNS = 'http://schemas.openxmlformats.org/drawingml/2006/main'

        for i, ser in enumerate(chart.series):
            sub_name = all_subs[i] if i < len(all_subs) else ''
            ser_el   = ser._element
            dLbls_ser = etree.SubElement(ser_el, qn('c:dLbls'))
            # 1. dLbl delete entries FIRST (schema order)
            for j, item in enumerate(issue_data):
                sub_map = {si['sub_issue_type']: si['count']
                           for si in item.get('sub_issues', [])}
                if sub_map.get(sub_name, 0) == 0:
                    dLbl   = etree.SubElement(dLbls_ser, qn('c:dLbl'))
                    idx_el = etree.SubElement(dLbl, qn('c:idx'))
                    idx_el.set('val', str(j))
                    del_el = etree.SubElement(dLbl, qn('c:delete'))
                    del_el.set('val', '1')
            # 2. txPr with explicit font size (overrides chart-level default)
            txPr = etree.SubElement(dLbls_ser, qn('c:txPr'))
            bodyPr = etree.SubElement(txPr, f'{{{_ADRAWNS}}}bodyPr')
            etree.SubElement(txPr, f'{{{_ADRAWNS}}}lstStyle')
            p_el = etree.SubElement(txPr, f'{{{_ADRAWNS}}}p')
            pPr  = etree.SubElement(p_el, f'{{{_ADRAWNS}}}pPr')
            defRPr = etree.SubElement(pPr, f'{{{_ADRAWNS}}}defRPr')
            defRPr.set('sz', str(_LABEL_SZ))   # 6.7pt
            defRPr.set('b', '1')
            # 3. showXxx flags AFTER txPr
            for _tag, _val in [('c:showLegendKey', '0'), ('c:showVal', '1'),
                                ('c:showCatName', '0'),  ('c:showSerName', '0'),
                                ('c:showPercent', '0'),  ('c:showBubbleSize', '0')]:
                _e = etree.SubElement(dLbls_ser, qn(_tag))
                _e.set('val', _val)
    except Exception:
        pass

    try:
        _style_axis(chart.category_axis, font_size=8)
        _style_axis(chart.value_axis,    font_size=8)
        _set_axis_title(chart.value_axis,    'Number of Tickets', font_size=8)
        _set_axis_title(chart.category_axis, 'Issue Type',        font_size=8)
        _remove_gridlines(chart)
    except Exception:
        pass


# ── Bitdefender Half-Gauge (Company Risk Score) ───────────────────────

def _draw_bitdefender_gauge(value: int, impact: str,
                            findings_pct, app_vuln_pct, human_risk_pct,
                            w_px=640, h_px=420) -> BytesIO:
    """
    Half-circle meter gauge exactly matching the Bitdefender Risk Score UI image.

    Design:
    - Outer thick ring + inner thin ring (two concentric arcs)
    - Base colors: green (0-50%), amber (50-75%), red (75-100%) — always visible
    - Dark charcoal overlay covers ONLY the unlit portion within the lit zone
      (i.e. from score% up to the boundary of the current colour zone)
    - Score value centered in the arc
    - Tick labels: 0%, 25%, 50%, 75%, 100%
    - Impact badge with rounded border below the score
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Wedge, FancyBboxPatch, Circle

    # ── geometry constants ────────────────────────────────────────────────
    R_O1  = 1.08   # outer ring outer radius
    R_O2  = 0.76   # outer ring inner radius  (ring width = 0.32)
    R_I1  = 0.70   # inner ring outer radius
    R_I2  = 0.55   # inner ring inner radius  (ring width = 0.15)

    # angle mapping: 180° = 0 (left), 0° = 100 (right)
    # pct → degrees: angle = 180 - pct * 180
    def pct_to_deg(pct):
        return 180.0 - float(pct) * 180.0

    # ── colour zones (always drawn, never hidden) ─────────────────────────
    #   green:  0% – 50%   → 180° – 90°
    #   amber: 50% – 75%   →  90° – 45°
    #   red:   75% – 100%  →  45° –  0°
    ZONES = [
        (0.00, 0.50, '#22C55E'),   # green
        (0.50, 0.75, '#F59E0B'),   # amber
        (0.75, 1.00, '#EF4444'),   # red
    ]

    dpi = 100
    fig, ax = plt.subplots(figsize=(w_px / dpi, h_px / dpi))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_xlim(-1.55, 1.55)
    ax.set_ylim(-0.70, 1.45)
    ax.set_aspect('equal')
    ax.axis('off')

    def _ring(t1_deg, t2_deg, R_out, R_in, color, alpha=1.0, zo=1, ew=0.8):
        """Draw one wedge (arc segment) of a ring."""
        if abs(t2_deg - t1_deg) < 0.1:
            return
        w = Wedge((0, 0), R_out, t1_deg, t2_deg, width=R_out - R_in,
                  facecolor=color, edgecolor='white',
                  linewidth=ew, alpha=alpha, zorder=zo)
        ax.add_patch(w)

    score_pct = min(max(float(value) / 100.0, 0.0), 1.0)

    # Nicer colour palette
    C_GREEN = '#00C47A'   # vibrant teal-green
    C_AMBER = '#FFB020'   # warm golden-amber
    C_RED   = '#F04438'   # clear coral-red
    C_DARK  = '#4B5563'   # neutral slate (unlit zone)
    C_INNER = '#E5E7EB'   # light gray for inner ring base

    # ── Step 1: full neutral background arc ───────────────────────────────
    _ring(0, 180, R_O1, R_O2, C_DARK, zo=1)
    _ring(0, 180, R_I1, R_I2, C_INNER, alpha=0.55, zo=1, ew=0)

    # ── Step 2: bright green lit portion (0 → score) ──────────────────────
    if score_pct > 0.005:
        a_end   = pct_to_deg(0.0)
        a_start = pct_to_deg(score_pct)
        _ring(a_start, a_end, R_O1, R_O2, C_GREEN, zo=2)
        _ring(a_start, a_end, R_I1, R_I2, C_GREEN, alpha=0.35, zo=2, ew=0)

    # ── Step 3: amber (50–75%) and red (75–100%) always on top ────────────
    _ring(pct_to_deg(0.75), pct_to_deg(0.50), R_O1, R_O2, C_AMBER, zo=3)
    _ring(pct_to_deg(0.75), pct_to_deg(0.50), R_I1, R_I2, C_AMBER, alpha=0.35, zo=3, ew=0)
    _ring(pct_to_deg(1.00), pct_to_deg(0.75), R_O1, R_O2, C_RED,   zo=3)
    _ring(pct_to_deg(1.00), pct_to_deg(0.75), R_I1, R_I2, C_RED,   alpha=0.35, zo=3, ew=0)

    # ── White divider lines between segments ──────────────────────────────
    for boundary_pct in [0.0, 0.50, 0.75, 1.0]:
        ang = np.radians(pct_to_deg(boundary_pct))
        ax.plot([R_I2 * np.cos(ang), R_O1 * np.cos(ang)],
                [R_I2 * np.sin(ang), R_O1 * np.sin(ang)],
                color='white', linewidth=1.5, zorder=4)

    # ── Score notch (white dot at current position) ───────────────────────
    score_ang_rad = np.radians(pct_to_deg(score_pct))
    notch_r = (R_O1 + R_I2) / 2
    ax.add_patch(Circle(
        (notch_r * np.cos(score_ang_rad), notch_r * np.sin(score_ang_rad)),
        0.045, facecolor='white', edgecolor='#D1D5DB', linewidth=0.8, zorder=5
    ))

    # ── Tick labels: 0%, 25%, 50%, 75%, 100% ─────────────────────────────
    for frac, lbl in [(0.0, '0%'), (0.25, '25%'), (0.50, '50%'),
                      (0.75, '75%'), (1.0, '100%')]:
        ang = np.radians(pct_to_deg(frac))
        r_lbl = R_O1 + 0.18
        ax.text(r_lbl * np.cos(ang), r_lbl * np.sin(ang), lbl,
                ha='center', va='center', fontsize=7,
                color='#9CA3AF', fontfamily='DejaVu Sans', zorder=6)

    # ── Score number centered in arc ──────────────────────────────────────
    ax.text(0, 0.10, str(int(round(value))),
            ha='center', va='center', fontsize=36, fontweight='bold',
            color='#111827', fontfamily='DejaVu Sans', zorder=7)

    # ── Impact badge (smaller, compact) ───────────────────────────────────
    impact_lower = (impact or '').lower()
    if   'high'   in impact_lower: badge_fg, badge_bg = '#F04438', '#FEF2F2'
    elif 'medium' in impact_lower: badge_fg, badge_bg = '#FFB020', '#FFFBEB'
    else:                          badge_fg, badge_bg = '#00C47A', '#ECFDF5'

    bw, bh = 0.84, 0.19
    ax.add_patch(FancyBboxPatch((-bw / 2, -0.30), bw, bh,
                                boxstyle='round,pad=0.04',
                                facecolor=badge_bg, edgecolor=badge_fg,
                                linewidth=1.6, zorder=7))
    ax.text(0, -0.30 + bh / 2, impact or 'Low Impact',
            ha='center', va='center', fontsize=7.5, fontweight='bold',
            color=badge_fg, fontfamily='DejaVu Sans', zorder=8)

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='white', pad_inches=0.06)
    plt.close(fig)
    buf.seek(0)
    return buf


def add_bitdefender_gauge(slide, title: str,
                          value: int, impact: str,
                          findings_pct=None, app_vuln_pct=None, human_risk_pct=None,
                          left_in=0, top_in=0, w_in=5, h_in=5):
    """
    Company Risk Score card: half-circle gauge + impact badge + breakdown stats.
    Matches the Bitdefender UI design shown in the reference images.
    """
    if value is None:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    # Card background
    card = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in)
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)

    # Title (top-left)
    _add_section_title(slide, title, left_in, top_in, w_in)

    # Gauge image (matplotlib)
    GAUGE_H_FRAC = 0.58
    gauge_w = w_in * 0.72
    gauge_h = h_in * GAUGE_H_FRAC
    gauge_l = left_in + (w_in - gauge_w) / 2
    gauge_t = top_in + 0.38

    try:
        buf = _draw_bitdefender_gauge(
            value, impact,
            findings_pct, app_vuln_pct, human_risk_pct,
            w_px=600, h_px=380
        )
        slide.shapes.add_picture(
            buf, _inches(gauge_l), _inches(gauge_t),
            _inches(gauge_w), _inches(gauge_h)
        )
    except Exception:
        pass

    # Breakdown stats below the gauge
    stats = []
    if findings_pct  is not None: stats.append(('Findings',           findings_pct))
    if app_vuln_pct  is not None: stats.append(('App Vulnerabilities', app_vuln_pct))
    if human_risk_pct is not None: stats.append(('Human Risks',        human_risk_pct))

    stat_top = gauge_t + gauge_h + 0.08
    for i, (lbl, pct_val) in enumerate(stats):
        sy = stat_top + i * 0.30
        tb = slide.shapes.add_textbox(
            _inches(left_in + 0.25), _inches(sy),
            _inches(w_in - 0.5), _inches(0.28)
        )
        p = tb.text_frame.paragraphs[0]
        r1 = p.add_run()
        r1.text = f"{lbl}: "
        r1.font.size = Pt(9)
        r1.font.bold = True
        r1.font.name = lm.FONT_NAME
        r1.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
        r2 = p.add_run()
        r2.text = f"{pct_val}%"
        r2.font.size = Pt(9)
        r2.font.bold = False
        r2.font.name = lm.FONT_NAME
        r2.font.color.rgb = RGBColor(0x37, 0x41, 0x51)


# ── Bitdefender Inventory Donut + KV Card ────────────────────────────

def add_inventory_donut_card(slide, title: str,
                             summary: dict, count: dict,
                             left_in=0, top_in=0, w_in=5, h_in=5):
    """
    Bitdefender Inventory Summary.
    Left side : key-value stats (Managed Endpoints, Physical Machines, Virtual Machines).
    Right side: donut chart showing OS breakdown (WindowsWorkstations, WindowsServers, …).

    KV cards always render (using '—' for any missing value). If the OS
    breakdown has no non-zero values, an empty donut ring is shown with the
    fixed OS category legend (WindowsWorkstations/WindowsServers/MacOS/Linux)
    and "Total 0" instead of leaving that area blank.
    """
    summary = summary or {}
    count = count or {}

    _add_section_title(slide, title, left_in, top_in, w_in)
    TITLE_H = 0.38

    # Layout: left KV panel (36%) | right donut (64%)
    KV_W     = w_in * 0.36
    DONUT_W  = w_in - KV_W - 0.12
    DONUT_L  = left_in + KV_W + 0.12
    SLOT_TOP = top_in + TITLE_H
    SLOT_H   = h_in - TITLE_H

    # ── Left KV cards (nice rounded rectangles) ───────────────────────────
    kv_items = [
        ('Managed Endpoints', count.get('managedendpoints', '—'), '#3e7564', '#FFFFFF'),
        ('Physical Machines', count.get('physicalmachines', '—'), '#4ca88c', '#FFFFFF'),
        ('Virtual Machines',  count.get('virtualmachines',  '—'), '#65cfae', '#FFFFFF'),
    ]
    CARD_GAP = 0.12
    CARD_H   = min((SLOT_H - CARD_GAP * (len(kv_items) + 1)) / len(kv_items), 1.10)
    cards_block_h = len(kv_items) * CARD_H + (len(kv_items) - 1) * CARD_GAP
    card_start_y  = SLOT_TOP + (SLOT_H - cards_block_h) / 2   # vertically centred

    for i, (lbl, val, clr, bg) in enumerate(kv_items):
        cy = card_start_y + i * (CARD_H + CARD_GAP)
        cx = left_in + 0.06

        # Card background (rounded rect)
        card = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(cx), _inches(cy),
            _inches(KV_W - 0.06), _inches(CARD_H)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        card.line.color.rgb      = RGBColor(0xFF, 0xFF, 0xFF)
        try: card.adjustments[0] = 0.05
        except Exception: pass

        # Left accent bar — #daf3f7
        accent = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(cx), _inches(cy),
            _inches(0.06), _inches(CARD_H)
        )
        accent.fill.solid()
        accent.fill.fore_color.rgb = RGBColor(0xC5, 0xE3, 0x64)
        accent.line.fill.background()

        # Value (large, bold)
        vb = slide.shapes.add_textbox(
            _inches(cx + 0.12), _inches(cy + 0.06),
            _inches(KV_W - 0.22), _inches(CARD_H * 0.55)
        )
        vp = vb.text_frame.paragraphs[0]
        vr = vp.add_run()
        vr.text = str(val)
        vr.font.size = Pt(20)
        vr.font.bold = True
        vr.font.name = lm.FONT_NAME
        vr.font.color.rgb = _rgb(clr)

        # Label (small, gray)
        lb = slide.shapes.add_textbox(
            _inches(cx + 0.12), _inches(cy + CARD_H * 0.55),
            _inches(KV_W - 0.22), _inches(CARD_H * 0.38)
        )
        lp = lb.text_frame.paragraphs[0]
        lr = lp.add_run()
        lr.text = lbl
        lr.font.size = Pt(10)
        lr.font.name = lm.FONT_NAME
        lr.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

    # ── Right donut chart ─────────────────────────────────────────────────
    # Build label/color/value lists from JSON — skip any with value == 0
    _all_os = [
        ('WindowsWorkstations', '#3e7564'),
        ('WindowsServers',      '#4ca88c'),
        ('MacOS',               '#65cfae'),
        ('Linux',               '#c5e364'),
    ]
    os_labels, os_colors, os_values = [], [], []
    for key, clr in _all_os:
        v = int(summary.get(key.lower(), 0) or 0)
        if v > 0:
            os_labels.append(key)
            os_colors.append(clr)
            os_values.append(v)

    if os_values:
        total_managed = sum(os_values)
        LEGEND_H = 0.42
        donut_h  = SLOT_H - LEGEND_H

        chart_data = CategoryChartData()
        chart_data.categories = os_labels
        chart_data.add_series('', [float(v) for v in os_values])

        chart_frame = slide.shapes.add_chart(
            XL_CHART_TYPE.DOUGHNUT,
            _inches(DONUT_L), _inches(SLOT_TOP),
            _inches(DONUT_W), _inches(donut_h),
            chart_data
        )
        _remove_chart_background(chart_frame)
        chart = chart_frame.chart
        chart.has_title  = False
        chart.has_legend = False

        plot = chart.plots[0]
        try: plot.doughnut_hole_size = 55
        except Exception: pass

        # Per-point colors
        try:
            ser = chart.series[0]
            for j, pt in enumerate(ser.points):
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = _rgb(os_colors[j])
        except Exception: pass

        # Data labels: white, show value only
        try:
            plot.has_data_labels = True
            dls = plot.data_labels
            dls.show_value         = True
            dls.show_percentage    = False
            dls.show_category_name = False
            dls.font.size          = Pt(9)
            dls.font.bold          = True
            dls.font.color.rgb     = RGBColor(0xFF, 0xFF, 0xFF)
        except Exception: pass

        # Center overlay — perfectly centred in the donut hole
        # The donut chart visual area sits inside the frame with ~8% internal margin.
        # With no title/legend the visual centre ≈ frame centre.
        TB_W = 1.40
        TB_H = 0.64
        # Horizontal: frame centre minus half textbox width
        cx = DONUT_L + (DONUT_W - TB_W) / 2
        # Vertical: frame centre minus half textbox height
        # PPTX donut charts leave ~4% top padding so nudge slightly up
        cy = SLOT_TOP + (donut_h - TB_H) / 2 - donut_h * 0.04

        tbc = slide.shapes.add_textbox(
            _inches(cx), _inches(cy), _inches(TB_W), _inches(TB_H)
        )
        tf = tbc.text_frame
        tf.word_wrap = False

        p1 = tf.paragraphs[0]
        p1.alignment = PP_ALIGN.CENTER
        r1 = p1.add_run()
        r1.text = 'Total'
        r1.font.size = Pt(8)
        r1.font.name = lm.FONT_NAME
        r1.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = str(total_managed)
        r2.font.size = Pt(18)
        r2.font.bold = True
        r2.font.name = lm.FONT_NAME
        r2.font.color.rgb = RGBColor(0x11, 0x18, 0x27)

        # Legend below donut (only non-zero labels)
        legend_top = SLOT_TOP + donut_h + 0.04
        _draw_auto_legend(slide, os_labels, os_colors,
                          DONUT_L, legend_top, DONUT_W)
    else:
        # No OS breakdown data — show the empty ring + the fixed OS category
        # legend + "Total 0" instead of leaving this area blank.
        _fixed_labels = [k for k, _ in _all_os]
        _fixed_colors = [c for _, c in _all_os]
        _add_empty_donut_chart(
            slide, '', _fixed_labels, _fixed_colors,
            DONUT_L, SLOT_TOP, DONUT_W, SLOT_H,
            show_title=False, show_legend=True,
        )


# ── Devices & Storage Summary Card Grid ──────────────────────────────

def add_devices_storage_card(slide, title: str, stats: list,
                              left_in=0, top_in=0, w_in=5, h_in=5):
    """
    2-column grid of stat cards matching the Cove "Devices & Storage Summary" UI.
    stats: list of (label, value, icon_type, icon_color, icon_bg)
    Each card: white rounded rect + colored icon square + label (gray) + value (bold black).
    """
    if not stats:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    _add_section_title(slide, title, left_in, top_in, w_in)
    TITLE_H = 0.38
    SLOT_TOP = top_in + TITLE_H
    SLOT_H   = h_in - TITLE_H

    COLS     = 2
    GAP_X    = 0.14
    GAP_Y    = 0.12
    n        = len(stats)
    n_rows   = math.ceil(n / COLS)

    card_w = (w_in - GAP_X * (COLS + 1)) / COLS
    card_h = min((SLOT_H - GAP_Y * (n_rows + 1)) / n_rows, 1.0)

    ICO_SZ   = min(card_h * 0.72, 0.55)   # icon square size
    ICO_PAD  = (card_h - ICO_SZ) / 2      # vertical padding to centre icon

    for idx, (label, value, icon_type, icon_color, icon_bg) in enumerate(stats):
        row = idx // COLS
        col = idx % COLS

        cx = left_in + GAP_X + col * (card_w + GAP_X)

        cy = SLOT_TOP + GAP_Y + row * (card_h + GAP_Y)

        # ── Card background (white rounded rect with subtle border) ──────
        card = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(cx), _inches(cy), _inches(card_w), _inches(card_h)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
        try: card.adjustments[0] = 0.06
        except Exception: pass

        # ── Icon background square (rounded) ─────────────────────────────
        ico_x = cx + ICO_PAD * 0.8
        ico_y = cy + ICO_PAD
        ico_sq = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(ico_x), _inches(ico_y), _inches(ICO_SZ), _inches(ICO_SZ)
        )
        ico_sq.fill.solid()
        ico_sq.fill.fore_color.rgb = _rgb(icon_bg)
        ico_sq.line.fill.background()
        try: ico_sq.adjustments[0] = 0.15
        except Exception: pass

        # ── Icon image (PIL-drawn) ────────────────────────────────────────
        try:
            ico_buf = _make_icon_png(icon_type, icon_color, size=80)
            if ico_buf:
                img_pad = ICO_SZ * 0.18
                slide.shapes.add_picture(
                    ico_buf,
                    _inches(ico_x + img_pad), _inches(ico_y + img_pad),
                    _inches(ICO_SZ - img_pad * 2), _inches(ICO_SZ - img_pad * 2)
                )
        except Exception:
            pass

        # ── Text area (label + value) to the right of icon ───────────────
        txt_x = ico_x + ICO_SZ + ICO_PAD * 0.5
        txt_w = max(0.5, cx + card_w - txt_x - 0.06)

        # Label (gray, small, word-wrapped)
        lb = slide.shapes.add_textbox(
            _inches(txt_x), _inches(cy + card_h * 0.08),
            _inches(txt_w), _inches(card_h * 0.44)
        )
        lb.text_frame.word_wrap = True
        lp = lb.text_frame.paragraphs[0]
        lr = lp.add_run()
        lr.text = label
        lr.font.size = Pt(9)
        lr.font.name = lm.FONT_NAME
        lr.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

        # Value (black, bold, word-wrapped)
        vb = slide.shapes.add_textbox(
            _inches(txt_x), _inches(cy + card_h * 0.50),
            _inches(txt_w), _inches(card_h * 0.44)
        )
        vb.text_frame.word_wrap = True
        vp = vb.text_frame.paragraphs[0]
        vr = vp.add_run()
        vr.text = str(value)
        vr.font.size = Pt(9)
        vr.font.bold = True
        vr.font.name = lm.FONT_NAME
        vr.font.color.rgb = RGBColor(0x11, 0x18, 0x27)


# ── LIVE badge ────────────────────────────────────────────────────────

def add_live_badge(slide, left_in: float, top_in: float,
                   w_in: float = 0.611, h_in: float = 0.190):
    """
    Add a "Live Data" status badge:
      • Rounded-rectangle filled with #92D050 (light green), pill-shaped, no border
      • Small white circle (dot) near the left edge
      • Bold white "Live Data" text centred — Calibri 8pt
    Parameters left_in / top_in are the top-left corner of the badge in inches.
    """
    _GREEN = RGBColor(0xA9, 0xD1, 0x8E)   # light sage green
    _WHITE = RGBColor(0xFF, 0xFF, 0xFF)

    left = Inches(left_in)
    top  = Inches(top_in)
    w    = Inches(w_in)
    h    = Inches(h_in)

    # ── Rounded rectangle (badge body) ───────────────────────────────
    badge = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        left, top, w, h
    )
    _set_shape_adj(badge, 50000)          # pill / fully rounded
    badge.fill.solid()
    badge.fill.fore_color.rgb = _GREEN
    badge.line.fill.background()          # no border

    from pptx.enum.text import MSO_ANCHOR
    tf = badge.text_frame
    tf.word_wrap = False
    tf.vertical_anchor  = MSO_ANCHOR.MIDDLE   # vertically centre the text
    tf.margin_left   = Inches(0.18)           # leave room for the dot
    tf.margin_right  = Inches(0.06)
    tf.margin_top    = Inches(0.0)
    tf.margin_bottom = Inches(0.0)

    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.CENTER
    run = para.add_run()
    run.text = "Live Data"
    run.font.bold      = True
    run.font.size      = Pt(8)
    run.font.color.rgb = _WHITE
    run.font.name      = "Calibri"

    # ── White dot — vertically aligned to badge middle, same as text ──
    dot_d    = Inches(0.055)
    dot_left = left + Inches(0.07)            # centred in the 0.18" left margin
    dot_top  = top  + (h - dot_d) // 2       # badge middle − half dot height
    dot = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.OVAL,
        dot_left, dot_top, dot_d, dot_d
    )
    dot.fill.solid()
    dot.fill.fore_color.rgb = _WHITE
    dot.line.fill.background()


# ── Bitdefender Module Status Table (paginated multi-slide) ──────────

def build_module_status_slides(prs, section_name: str, title: str,
                                module_data: list):
    """
    Security Module Enablement Status — paginated 3-column table.
    Creates as many slides as needed so NO rows are ever omitted.
    Columns: Module | Enable | Not Enabled  (plain text headers, no squares)
    Data rows: white background, black text, 8pt font.
    """
    import app.services.ppt.slide_builder as _sb

    # Only show modules that have at least one endpoint enabled — modules
    # with Enable == 0 are dropped entirely (not just the Disabled column).
    module_data = [
        m for m in (module_data or [])
        if int(m.get('enable', m.get('enabled', 0)) or 0) > 0
    ]

    if not module_data:
        slide = _sb.new_content_slide(prs, section_name, title)
        add_no_data(slide, title,
                    lm.CONTENT_LEFT_IN, lm.CONTENT_TOP_IN,
                    lm.CONTENT_W_IN, lm.CONTENT_H_IN)
        return

    # ── Layout constants ──────────────────────────────────────────────
    LEFT     = lm.CONTENT_LEFT_IN
    TOP      = lm.CONTENT_TOP_IN + 0.10   # small gap below header
    W        = lm.CONTENT_W_IN
    FOOTER_Y = lm.FOOTER_TOP_IN
    SAFE_GAP = 0.12                        # gap before footer

    TITLE_H  = 0.34
    ROW_H    = 0.30   # fixed — never reduced
    FONT_SZ  = 8

    # Available height per slide for the table body
    # Subtract header row height so total table (header + data rows) never crosses footer
    avail_h   = FOOTER_Y - TOP - TITLE_H - SAFE_GAP
    rows_pp   = max(1, int((avail_h - ROW_H) / ROW_H))   # data rows per page (header excluded)

    COL_MOD_W = W * 0.62
    COL_EN_W  = (W - COL_MOD_W)  #removing "Disabled column" so [removed  COL_EN_W  = (W - COL_MOD_W)/2 becoz we don't have to divide into 2 columns]

    CLR_HDR_BG  = RGBColor(0xF5, 0xF7, 0xFA)
    CLR_HDR_TXT = RGBColor(0x37, 0x41, 0x51)
    CLR_BLACK   = RGBColor(0x11, 0x18, 0x27)
    CLR_WHITE   = RGBColor(0xFF, 0xFF, 0xFF)

    def _ct(cell, text, bold=False, align=PP_ALIGN.LEFT, color=None):
        tf = cell.text_frame
        tf.word_wrap = False
        p  = tf.paragraphs[0]
        p.alignment = align
        r  = p.add_run()
        r.text = text
        r.font.size = Pt(FONT_SZ)
        r.font.bold = bold
        r.font.name = lm.FONT_NAME
        r.font.color.rgb = color or CLR_BLACK

    # ── Paginate ──────────────────────────────────────────────────────
    pages = [module_data[i:i + rows_pp]
             for i in range(0, len(module_data), rows_pp)]
    n_pages = len(pages)

    for pg_idx, page_rows in enumerate(pages):
        slide = _sb.new_content_slide(prs, section_name, title)

        # LIVE badge — top-right of content area
        add_live_badge(slide, LEFT + W - 0.85, TOP + 0.03)

        # Title bar
        _add_section_title(slide, title, LEFT, TOP, W)
        tbl_top  = TOP + TITLE_H
        n_rows   = len(page_rows) + 1   # +1 header
        tbl_h    = ROW_H * n_rows

        tbl_frame = slide.shapes.add_table(
            n_rows, 2,  #table column count changed from 3 to 2 now 
            _inches(LEFT), _inches(tbl_top),
            _inches(W), _inches(tbl_h)
        )
        tbl = tbl_frame.table
        tbl.columns[0].width = _inches(COL_MOD_W)
        tbl.columns[1].width = _inches(COL_EN_W)
        #tbl.columns[2].width = _inches(COL_EN_W) delete this line entirely (3rd column width assignment)

        # Header row — plain text only, no squares, no color data
        for c in range(2): #header fill loop
            tbl.cell(0, c).fill.solid()
            tbl.cell(0, c).fill.fore_color.rgb = CLR_HDR_BG
        _ct(tbl.cell(0, 0), 'Module',      bold=True, color=CLR_HDR_TXT)
        _ct(tbl.cell(0, 1), 'Enable',      bold=True, align=PP_ALIGN.CENTER, color=CLR_HDR_TXT)
        #_ct(tbl.cell(0, 2), 'Not Enabled', bold=True, align=PP_ALIGN.CENTER, color=CLR_HDR_TXT) need to delete this line entirely ("Not Enabled" header cell)

        # Data rows
        for i, mod in enumerate(page_rows):
            ri   = i + 1
            name = (mod.get('displayname') or mod.get('displayName') or
                    mod.get('name') or mod.get('module') or mod.get('Module', ''))
            en   = int(mod.get('enable',    mod.get('enabled', 0)) or 0)
            # ne   = int(mod.get('notenable', mod.get('notEnabled',
            #            (mod.get('disabled', 0) or 0) + (mod.get('notInstalled', 0) or 0))) or 0)

            for c in range(2):  #data row fill loop
                tbl.cell(ri, c).fill.solid()
                tbl.cell(ri, c).fill.fore_color.rgb = CLR_WHITE

            _ct(tbl.cell(ri, 0), name)
            _ct(tbl.cell(ri, 1), str(en), bold=True, align=PP_ALIGN.CENTER)
           # _ct(tbl.cell(ri, 2), str(ne), bold=True, align=PP_ALIGN.CENTER) delete this line entirely (data cell for "Not Enabled")

        # Page indicator — fixed at bottom of slide, just above footer
        if n_pages > 1:
            pg_top = lm.FOOTER_TOP_IN - 0.26   # always at bottom, never over table
            pg_box = slide.shapes.add_textbox(
                _inches(LEFT + W - 1.2), _inches(pg_top),
                _inches(1.2), _inches(0.25)
            )
            pr = pg_box.text_frame.paragraphs[0]
            pr.alignment = PP_ALIGN.RIGHT
            rr = pr.add_run()
            rr.text = f'Page {pg_idx + 1} of {n_pages}'
            rr.font.size = Pt(7)
            rr.font.name = lm.FONT_NAME
            rr.font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)


# ── (kept for backward compat — not used for module table any more) ───
def add_module_status_table(slide, title: str, module_data: list,
                             left_in=0, top_in=0, w_in=5, h_in=5):
    """Stub — use build_module_status_slides() instead."""
    if not module_data:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    CLR_ENABLED     = '#5B8FF9'   # blue square
    CLR_NOT_ENABLED = '#E86DC3'   # pink square
    CLR_HEADER_BG   = RGBColor(0xF5, 0xF7, 0xFA)
    CLR_BLACK       = RGBColor(0x11, 0x18, 0x27)
    CLR_HDR_TEXT    = RGBColor(0x37, 0x41, 0x51)

    TITLE_H  = 0.38
    LEGEND_H = 0.28
    SQ_SIZE  = 0.12
    PAD      = 0.06    # gap between table and legend

    _add_section_title(slide, title, left_in, top_in, w_in)

    # ── Available space ───────────────────────────────────────────────────
    # Hard ceiling: table must never go past (footer - legend - padding).
    max_table_bot = top_in + h_in - LEGEND_H - PAD * 2
    table_top     = top_in + TITLE_H
    max_table_h   = max_table_bot - table_top

    # Font is always fixed at 8pt — never reduced to squeeze more rows.
    font_sz  = 8
    MIN_ROW_H = 0.26   # minimum acceptable row height for 8pt font

    n_data = len(module_data)
    n_rows = n_data + 1   # header + data rows

    # Calculate natural row height that fits all rows in the available space.
    natural_row_h = max_table_h / n_rows

    if natural_row_h >= MIN_ROW_H:
        # All rows fit — use natural (spread to fill) with a cap at 0.34"
        row_h = min(natural_row_h, 0.34)
    else:
        # Rows would be too tight at MIN_ROW_H — clip data, never compress.
        row_h = MIN_ROW_H
        max_rows_fit = max(1, int(max_table_h / row_h))
        n_data = max(1, max_rows_fit - 1)
        module_data = module_data[:n_data]
        n_rows = n_data + 1

    table_h = row_h * n_rows

    # Column widths
    COL_MOD_W = w_in * 0.62
    COL_EN_W  = (w_in - COL_MOD_W) / 2

    # ── Build native PPTX table ───────────────────────────────────────────
    tbl_frame = slide.shapes.add_table(
        n_rows, 3,
        _inches(left_in), _inches(table_top),
        _inches(w_in), _inches(table_h)
    )
    tbl = tbl_frame.table
    tbl.columns[0].width = _inches(COL_MOD_W)
    tbl.columns[1].width = _inches(COL_EN_W)
    tbl.columns[2].width = _inches(COL_EN_W)

    def _ct(cell, text, bold=False, align=PP_ALIGN.LEFT, fsize=None, color=None):
        tf = cell.text_frame
        tf.word_wrap = False
        p  = tf.paragraphs[0]
        p.alignment = align
        r  = p.add_run()
        r.text = text
        r.font.size = Pt(fsize or font_sz)
        r.font.bold = bold
        r.font.name = lm.FONT_NAME
        r.font.color.rgb = color or CLR_BLACK

    # ── Header row (light background, "Module" text + no text in count cols) ─
    for c in range(3):
        cell = tbl.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = CLR_HEADER_BG

    _ct(tbl.cell(0, 0), 'Module', bold=True, color=CLR_HDR_TEXT, fsize=font_sz)
    # Count columns in header: leave text empty — squares are drawn as shapes above

    # Blue and pink colour squares overlaid on the header count cells
    for col_idx, sq_clr in [(1, CLR_ENABLED), (2, CLR_NOT_ENABLED)]:
        col_off = COL_MOD_W + (col_idx - 1) * COL_EN_W
        sq_x = left_in + col_off + (COL_EN_W - SQ_SIZE) / 2
        sq_y = table_top + (row_h - SQ_SIZE) / 2
        sq = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            _inches(sq_x), _inches(sq_y),
            _inches(SQ_SIZE), _inches(SQ_SIZE)
        )
        sq.fill.solid()
        sq.fill.fore_color.rgb = _rgb(sq_clr)
        sq.line.fill.background()

    # ── Data rows: plain white background, black text ─────────────────────
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    for i, mod in enumerate(module_data):
        ri = i + 1
        name = (mod.get('displayname') or mod.get('displayName') or
                mod.get('name') or mod.get('module') or mod.get('Module', ''))
        en  = int(mod.get('enable',    mod.get('enabled', 0)) or 0)
        ne  = int(mod.get('notenable', mod.get('notEnabled',
                   (mod.get('disabled', 0) or 0) + (mod.get('notInstalled', 0) or 0))) or 0)

        for c in range(3):
            tbl.cell(ri, c).fill.solid()
            tbl.cell(ri, c).fill.fore_color.rgb = WHITE

        _ct(tbl.cell(ri, 0), name)
        _ct(tbl.cell(ri, 1), str(en),  bold=True, align=PP_ALIGN.CENTER)
        _ct(tbl.cell(ri, 2), str(ne),  bold=True, align=PP_ALIGN.CENTER)

    # ── Legend (colour squares + labels) below the table ─────────────────
    legend_y = table_top + table_h + PAD
    x_cur    = left_in + 0.10
    for sq_clr, lbl_text in [(CLR_ENABLED,     'Enabled'),
                              (CLR_NOT_ENABLED, 'Not Enabled (Disabled + Not Installed)')]:
        sq = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            _inches(x_cur), _inches(legend_y + 0.05),
            _inches(0.10), _inches(0.10)
        )
        sq.fill.solid()
        sq.fill.fore_color.rgb = _rgb(sq_clr)
        sq.line.fill.background()
        lt = slide.shapes.add_textbox(
            _inches(x_cur + 0.14), _inches(legend_y),
            _inches(w_in * 0.46), _inches(0.24)
        )
        lp = lt.text_frame.paragraphs[0]
        lr = lp.add_run()
        lr.text = lbl_text
        lr.font.size = Pt(7)
        lr.font.name = lm.FONT_NAME
        lr.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
        x_cur += 0.14 + w_in * 0.47


# ── Internal helper ───────────────────────────────────────────────────

def _add_section_title(slide, title: str, left_in, top_in, w_in):
    tb = slide.shapes.add_textbox(
        _inches(left_in), _inches(top_in + 0.04),
        _inches(w_in), _inches(0.32)
    )
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    r.font.bold = True
    r.font.size = Pt(10)
    r.font.name = lm.FONT_NAME
    r.font.color.rgb = RGBColor(0x24, 0x27, 0x2B)



# ── Circular KPI (SLA % display) ─────────────────────────────────────

def add_circular_kpi(slide, title: str, value: float, target: float = 100,
                     left_in=0, top_in=0, w_in=5, h_in=5, color: str = None):
    """
    Full-circle donut KPI for SLA percentages matching original PPT design.
    Shows value% filled ring + large percentage text + target text in center.
    color: optional hex override (e.g. '#0D2B1A'); if None, auto-picks by pct.
    """
    pct = min(1.0, float(value) / float(target)) if target else 0.0
    if color is None:
        if   pct >= 0.90: color = CLR_GREEN
        elif pct >= 0.70: color = CLR_YELLOW
        else:             color = CLR_RED

    # Title label above chart
    _add_section_title(slide, title, left_in, top_in, w_in)

    TITLE_H = 0.38
    chart_top = top_in + TITLE_H
    chart_h   = h_in - TITLE_H

    # Donut: value segment + remaining
    remaining = float(target) - float(value)
    chart_data = CategoryChartData()
    chart_data.categories = ['Met', 'Remaining']
    chart_data.add_series('', [float(value), max(0.0, remaining)])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.DOUGHNUT,
        _inches(left_in), _inches(chart_top), _inches(w_in), _inches(chart_h),
        chart_data
    )
    _remove_chart_background(chart_frame)
    chart = chart_frame.chart
    chart.has_title  = False
    chart.has_legend = False

    plot = chart.plots[0]
    try: plot.doughnut_hole_size = 65
    except Exception: pass
    try:
        pts = plot.series[0].points
        pts[0].format.fill.solid()
        pts[0].format.fill.fore_color.rgb = _rgb(color)
        pts[1].format.fill.solid()
        pts[1].format.fill.fore_color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
    except Exception: pass

    # Center overlay: large % value
    val_str = f"{value:.1f}%"
    cx = left_in + (w_in - 2.5) / 2
    cy = chart_top + chart_h * 0.42
    tb1 = slide.shapes.add_textbox(_inches(cx), _inches(cy), _inches(2.5), _inches(0.55))
    p1  = tb1.text_frame.paragraphs[0]
    p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run()
    r1.text = val_str
    r1.font.size = Pt(22)
    r1.font.bold = True
    r1.font.color.rgb = _rgb(color)

    # Center overlay: target text
    tb2 = slide.shapes.add_textbox(_inches(cx), _inches(cy + 0.35), _inches(2.5), _inches(0.28))
    p2  = tb2.text_frame.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = f"Target: {target:.0f}%"
    r2.font.size = Pt(8)
    r2.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)
 

 #### This is for Infima#####

def _lock_shape(shape):
    """
    Marks a shape/picture as not selectable, movable, resizable, or
    rotatable in PowerPoint (noSelect/noMove/noResize/noRot etc. on
    the shape's <a:spLocks>/<a:picLocks> element) — same raw-XML
    approach already used in table_builder.py's _set_cell_border.
    """
    el = shape._element
    nv_sp  = el.find(qn('p:nvSpPr'))
    nv_pic = el.find(qn('p:nvPicPr'))

    if nv_sp is not None:
        cnv = nv_sp.find(qn('p:cNvSpPr'))
        lock_tag = qn('a:spLocks')
    elif nv_pic is not None:
        cnv = nv_pic.find(qn('p:cNvPicPr'))
        lock_tag = qn('a:picLocks')
    else:
        return

    if cnv is None:
        return

    locks = cnv.find(lock_tag)
    if locks is None:
        locks = etree.SubElement(cnv, lock_tag)

    for attr in ('noGrp', 'noSelect', 'noRot', 'noChangeAspect',
                 'noMove', 'noResize', 'noEditPoints', 'noAdjustHandles',
                 'noChangeArrowheads', 'noChangeShapeType'):
        locks.set(attr, '1')


def _make_target_icon_png(color_hex: str, size: int = 64) -> BytesIO:
    """Bullseye / target glyph only (transparent background)."""
    from PIL import Image, ImageDraw

    r = int(color_hex[1:3], 16); g = int(color_hex[3:5], 16); b = int(color_hex[5:7], 16)
    clr = (r, g, b, 255)

    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad  = max(4, size // 10)
    lw   = max(2, size // 18)

    cx2, cy2 = size // 2, size // 2
    outer_r  = (size - pad * 2) // 2
    ring_gap = max(2, outer_r // 3)
    for rr in [outer_r, outer_r - ring_gap, outer_r - ring_gap * 2]:
        if rr <= 0:
            continue
        draw.ellipse([cx2 - rr, cy2 - rr, cx2 + rr, cy2 + rr], outline=clr, width=lw)
    dot_r = max(2, ring_gap // 2)
    draw.ellipse([cx2 - dot_r, cy2 - dot_r, cx2 + dot_r, cy2 + dot_r], fill=clr)

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def _make_icon_badge_png(icon_type: str, color_hex: str, size: int = 160) -> BytesIO:
    """
    Renders the tinted circle background AND the icon glyph into ONE
    flattened PNG (instead of a separate oval shape + separate icon
    picture). This is what fixes both the "editable icon" complaint
    (one locked picture instead of two movable shapes) and guarantees
    'target' always renders (dispatch happens here, not inside the
    original _make_icon_png).
    """
    from PIL import Image

    r = int(color_hex[1:3], 16); g = int(color_hex[3:5], 16); b = int(color_hex[5:7], 16)
    tint = (
        min(255, int(r + (255 - r) * 0.82)),
        min(255, int(g + (255 - g) * 0.82)),
        min(255, int(b + (255 - b) * 0.82)),
        255,
    )

    badge = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(badge).ellipse([0, 0, size - 1, size - 1], fill=tint)

    glyph_size = int(size * 0.55)
    glyph_buf = (_make_target_icon_png(color_hex, size=glyph_size) if icon_type == 'target'
                else _make_icon_png(icon_type, color_hex, size=glyph_size))

    if glyph_buf:
        glyph_img = Image.open(glyph_buf).convert('RGBA')
        off = (size - glyph_size) // 2
        badge.alpha_composite(glyph_img, (off, off))

    buf = BytesIO()
    badge.save(buf, format='PNG')
    buf.seek(0)
    return buf


def add_infima_metric_card(slide, title: str, value_text: str, subtitle: str,
                           pct: float, min_label: str, max_label: str,
                           icon_type: str, color_hex: str,
                           left_in=0, top_in=0, w_in=4.7, h_in=4.55,
                           live_badge: bool = True):
    """
    Infima metric card — matches the app.inputiv.com dashboard card design:
    a single locked icon badge (top-left), title, "Live Data" pill
    (top-right), large value, colored risk/status subtitle, and a
    horizontal progress bar with min/max scale labels underneath.

    color_hex MUST be one of the approved on-theme colors (CLR_GREEN /
    CLR_YELLOW / CLR_RED from this module) so the card never introduces
    an off-palette color.

    icon_type: 'envelope' (phishing / email metrics) or 'target'
               (training / on-track metrics).
    pct: 0.0–1.0 fill fraction for the progress bar.
    """
    PAD = 0.22

    # ── Card background ────────────────────────────────────────────────
    card = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in)
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
    card.line.width = Pt(1)

    # ── Title (top-left) ───────────────────────────────────────────────
    title_w = w_in - PAD * 2 - (0.85 if live_badge else 0)
    title_box = slide.shapes.add_textbox(
        _inches(left_in + PAD), _inches(top_in + PAD),
        _inches(title_w), _inches(0.32)
    )
    tp = title_box.text_frame.paragraphs[0]
    tr = tp.add_run()
    tr.text = title
    tr.font.name = lm.FONT_NAME
    tr.font.size = Pt(12)
    tr.font.bold = True
    tr.font.color.rgb = RGBColor(0x1E, 0x3D, 0x2F)

    # ── "Live Data" pill (top-right) ─────────────────────────────────
    if live_badge:
        add_live_badge(slide, left_in + w_in - PAD - 0.611, top_in + PAD - 0.02)

    # ── Icon badge: ONE flattened, locked picture ──────────────────────
    icon_row_top = top_in + PAD + 0.55
    ICON_SZ = 0.62

    badge_buf = _make_icon_badge_png(icon_type, color_hex, size=160)
    pic = slide.shapes.add_picture(
        badge_buf,
        _inches(left_in + PAD), _inches(icon_row_top),
        _inches(ICON_SZ), _inches(ICON_SZ)
    )
    _lock_shape(pic)

    # ── Big value (right of icon) ────────────────────────────────────
    val_x = left_in + PAD + ICON_SZ + 0.18
    val_box = slide.shapes.add_textbox(
        _inches(val_x), _inches(icon_row_top - 0.08),
        _inches(w_in - PAD - (val_x - left_in)), _inches(0.6)
    )
    vp = val_box.text_frame.paragraphs[0]
    vr = vp.add_run()
    vr.text = value_text
    vr.font.name = lm.FONT_NAME
    vr.font.size = Pt(30)
    vr.font.bold = True
    vr.font.color.rgb = RGBColor(0x1E, 0x3D, 0x2F)

    # ── Subtitle (risk / status label, colored) ────────────────────────
    sub_box = slide.shapes.add_textbox(
        _inches(val_x), _inches(icon_row_top + ICON_SZ - 0.28),
        _inches(w_in - PAD - (val_x - left_in)), _inches(0.3)
    )
    sp = sub_box.text_frame.paragraphs[0]
    sr = sp.add_run()
    sr.text = subtitle
    sr.font.name = lm.FONT_NAME
    sr.font.size = Pt(10)
    sr.font.bold = True
    sr.font.color.rgb = _rgb(color_hex)

    # ── Progress bar (bottom) ────────────────────────────────────────
    bar_w    = w_in - PAD * 2
    bar_h    = 0.14
    bar_top  = top_in + h_in - PAD - 0.42
    bar_left = left_in + PAD

    track = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(bar_left), _inches(bar_top), _inches(bar_w), _inches(bar_h)
    )
    _set_shape_adj(track, 50000)
    track.fill.solid()
    track.fill.fore_color.rgb = RGBColor(0xEE, 0xEE, 0xEE)
    track.line.fill.background()

    fill_pct = max(0.0, min(1.0, pct))
    if fill_pct > 0:
        fill_w = max(bar_h, bar_w * fill_pct)   # keep pill rounded at small values
        fg = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            _inches(bar_left), _inches(bar_top), _inches(fill_w), _inches(bar_h)
        )
        _set_shape_adj(fg, 50000)
        fg.fill.solid()
        fg.fill.fore_color.rgb = _rgb(color_hex)
        fg.line.fill.background()

    # ── Scale labels (min / max) ────────────────────────────────────────
    lbl_top = bar_top + bar_h + 0.04
    min_box = slide.shapes.add_textbox(
        _inches(bar_left), _inches(lbl_top), _inches(bar_w / 2), _inches(0.22)
    )
    mp = min_box.text_frame.paragraphs[0]
    mr = mp.add_run()
    mr.text = min_label
    mr.font.name = lm.FONT_NAME
    mr.font.size = Pt(8)
    mr.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)

    max_box = slide.shapes.add_textbox(
        _inches(bar_left + bar_w / 2), _inches(lbl_top), _inches(bar_w / 2), _inches(0.22)
    )
    xp = max_box.text_frame.paragraphs[0]
    xp.alignment = PP_ALIGN.RIGHT
    xr = xp.add_run()
    xr.text = max_label
    xr.font.name = lm.FONT_NAME
    xr.font.size = Pt(8)
    xr.font.color.rgb = RGBColor(0x6A, 0x72, 0x80)

"""
=====================================================================
This is for Axcient
=====================================================================
One new function. It's NOT a duplicate of add_line_chart — it reuses
add_line_chart's own internal helpers directly (_add_section_title,
_draw_auto_legend, _set_series_line, _style_axis, _remove_gridlines,
_set_axis_title, brand_palette) — the only genuinely new code is the
~15-line orchestration at the top. It exists as a separate function
because add_line_chart always renders a native (internal) chart title
and only supports a numeric-totals legend — neither fits a 6-series
plain-label legend drawn above the chart, which is what the Axcient
dashboard's "backup performance trend" card needs.
=====================================================================
"""


def add_multi_series_trend_chart(slide, title: str, x_labels: list, series_data: dict,
                                 colors: list = None, left_in=0, top_in=0, w_in=5, h_in=5,
                                 x_axis_title: str = None, y_axis_title: str = None):
    """
    Multi-series line chart, title-then-legend-then-chart layout:
      1. Title drawn externally via _add_section_title (same convention
         add_column_chart already uses).
      2. Plain dot+label legend via _draw_auto_legend — the same
         legend already used under every donut chart in this file.
      3. The line chart itself, placed below both.
    """
    if not x_labels:
        add_no_data(slide, title, left_in, top_in, w_in, h_in)
        return

    if not series_data:
        series_data = {'No Data': [0.0] * len(x_labels)}

    colors = colors or brand_palette(len(series_data))
    series_names = list(series_data.keys())

    TITLE_H  = 0.38
    _add_section_title(slide, title, left_in, top_in, w_in)

    LEGEND_H = 0.30
    _draw_auto_legend(slide, series_names, colors, left_in, top_in + TITLE_H, w_in)

    chart_top = top_in + TITLE_H + LEGEND_H
    chart_h   = h_in - TITLE_H - LEGEND_H

    chart_data = CategoryChartData()
    chart_data.categories = x_labels
    for name, vals in series_data.items():
        chart_data.add_series(name, [float(v) for v in vals])

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        _inches(left_in), _inches(chart_top), _inches(w_in), _inches(chart_h),
        chart_data
    )
    chart = chart_frame.chart
    chart.has_title  = False
    chart.has_legend = False

    for i, series in enumerate(chart.series):
        try:
            _set_series_line(series, colors[i % len(colors)], 1.5)
        except Exception:
            pass

    try:
        _style_axis(chart.category_axis, font_size=7)
        _style_axis(chart.value_axis, font_size=8)
        _remove_gridlines(chart)
        if x_axis_title:
            _set_axis_title(chart.category_axis, x_axis_title, font_size=8)
        if y_axis_title:
            _set_axis_title(chart.value_axis, y_axis_title, font_size=8)
    except Exception:
        pass


def add_backup_health_donut_card(
    slide, title: str, breakdown: dict,
    order: list, labels: dict, colors: dict,
    total_key: str = None,
    total_label: str = None,
    last_backup_on: str = None,
    last_backup_align: str = 'left',
    left_in=0, top_in=0, w_in=5, h_in=5
):
    """
    Hand-drawn donut (see add_donut_chart) — status breakdown with
    PERCENTAGE data labels (not counts) and a "<total_label> / N" center
    overlay. Only statuses with a non-zero value are drawn, in both the
    ring and the legend.

    last_backup_on: optional text (e.g. "last Backup On: 24 August 2026")
    drawn on the SAME row as the legend — 8pt, gray, not bold, Times New
    Roman. last_backup_align picks which edge of the card it hugs
    ('left' or 'right'), so two side-by-side cards can each keep it on
    their outer edge, away from the shared gap between them.
    """
    breakdown = breakdown or {}

    drawn_labels, drawn_colors, values = [], [], []
    for key in order:
        v = breakdown.get(key, 0) or 0
        if v > 0:
            drawn_labels.append(labels[key])
            drawn_colors.append(colors[key])
            values.append(v)

    if not values:
        _add_empty_donut_chart(
            slide, title,
            [labels[k] for k in order],
            [colors[k] for k in order],
            left_in, top_in, w_in, h_in,
        )
        return

    total = breakdown.get(total_key, 0) if total_key else 0
    if not total:
        total = sum(values)

    TITLE_H = 0.30 if title else 0.0
    if title:
        title_box = slide.shapes.add_textbox(
            _inches(left_in), _inches(top_in), _inches(w_in), _inches(TITLE_H)
        )
        title_box.text_frame.word_wrap = False
        tp = title_box.text_frame.paragraphs[0]
        tp.alignment = PP_ALIGN.CENTER
        tr = tp.add_run()
        tr.text = title
        tr.font.name = lm.FONT_NAME
        tr.font.size = Pt(10)
        tr.font.bold = True
        tr.font.color.rgb = _rgb(CLR_DARK)

    LEGEND_ROW_H, LEGEND_ROW_PAD, LEGEND_TOP_PAD = 0.24, 0.04, 0.06
    n_rows = _count_legend_rows(drawn_labels, w_in)
    legend_h = LEGEND_TOP_PAD + n_rows * (LEGEND_ROW_H + LEGEND_ROW_PAD)

    ring_top    = top_in + TITLE_H
    ring_area_h = max(0.4, h_in - TITLE_H - legend_h)
    ring_area_w = w_in

    diameter = max(0.5, min(ring_area_w, ring_area_h) * 0.90)
    r_outer  = diameter / 2
    r_inner  = r_outer * 0.5
    cx = left_in + ring_area_w / 2
    cy = ring_top + ring_area_h / 2

    total_drawn = sum(values)
    cum = 0.0
    for v, color in zip(values, drawn_colors):
        a_start = cum / total_drawn * 360.0
        cum += v
        a_end = cum / total_drawn * 360.0
        _add_donut_wedge_shape(slide, cx, cy, r_outer, r_inner, a_start, a_end, color)

        # Percentage data label at the wedge's mid-angle/mid-radius
        mid_a = (a_start + a_end) / 2.0
        mid_r = (r_outer + r_inner) / 2.0
        lx, ly = _donut_polar_xy(cx, cy, mid_r, mid_a)
        pct = round(v / total_drawn * 100)
        lbl_box = slide.shapes.add_textbox(
            _inches(lx - 0.35), _inches(ly - 0.11), _inches(0.7), _inches(0.22)
        )
        lbl_box.text_frame.word_wrap = False
        lp = lbl_box.text_frame.paragraphs[0]
        lp.alignment = PP_ALIGN.CENTER
        lr = lp.add_run()
        lr.text = f"{pct}%"
        lr.font.name = lm.FONT_NAME
        lr.font.size = Pt(8)
        lr.font.bold = True
        lr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    legend_top = ring_top + ring_area_h + 0.05
    _draw_auto_legend(slide, drawn_labels, drawn_colors, left_in, legend_top, w_in)

    if last_backup_on:
        from pptx.enum.text import MSO_ANCHOR

        # The legend block is horizontally CENTERED within w_in — compute
        # its actual width (same math _draw_auto_legend uses for a single
        # row, which covers our 1-2 item legends) so the last-backup text
        # sits in the genuinely free space beside it, never overlapping.
        _CHAR_W, _DOT, _GAP, _IPAD = 0.062, 0.10, 0.04, 0.18
        _item_ws = [_DOT + _GAP + len(str(l).replace('_', ' ')) * _CHAR_W for l in drawn_labels]
        legend_w = sum(_item_ws) + _IPAD * max(0, len(_item_ws) - 1)
        legend_x = left_in + (w_in - legend_w) / 2

        SIDE_GAP = 0.12
        if last_backup_align == 'left':
            avail_w = max(0.6, legend_x - left_in - SIDE_GAP)
            lb_left = left_in
        else:
            avail_w = max(0.6, (left_in + w_in) - (legend_x + legend_w) - SIDE_GAP)
            lb_left = left_in + w_in - avail_w

 #This line decides the text size of last Backup On: 25 August 2026 for the "Sharepoint/User backup execution health" 
        
        size_pt = 6
        per_char_in = lambda s: s * 0.50 / 72.0   # regular (not bold) TNR estimate
        while size_pt > 5.5 and len(last_backup_on) * per_char_in(size_pt) > avail_w:
            size_pt -= 0.5

        lb_box = slide.shapes.add_textbox(
            _inches(lb_left), _inches(legend_top), _inches(avail_w), _inches(LEGEND_ROW_H)
        )
        lb_box.text_frame.word_wrap = False
        lb_box.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        lbp = lb_box.text_frame.paragraphs[0]
        lbp.alignment = PP_ALIGN.LEFT if last_backup_align == 'left' else PP_ALIGN.RIGHT
        lbr = lbp.add_run()
        lbr.text = last_backup_on
        lbr.font.name = lm.FONT_NAME
        lbr.font.size = Pt(size_pt)
        lbr.font.bold = False
        lbr.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

    _draw_donut_center_block(slide, cx, cy, r_inner, [
        (total_label or 'Total', 9, False, '#6B7280'),
        (str(int(total)), 18, True, '#111827'),
    ])




# ── Deterministic donut plot-area layout (fixes cross-renderer centering) ──
# PowerPoint and LibreOffice can auto-layout a native chart title with
# slightly different heights, which shifts where the ring's own visual
# center actually lands. Pinning the plot area to a FIXED fractional
# rectangle makes the ring's position deterministic — identical in every
# renderer — so a center-label overlay computed from these same numbers
# is always aligned to the real ring, not an assumption about it.
DONUT_PLOT_X, DONUT_PLOT_Y, DONUT_PLOT_W, DONUT_PLOT_H = 0.05, 0.18, 0.90, 0.80



def _set_manual_plot_layout(chart, x: float, y: float, w: float, h: float):
    """Pin a chart's plot area to an exact fractional rect (0.0-1.0, relative
    to the chart frame) instead of leaving it to renderer auto-layout.

    IMPORTANT (two real bugs fixed here):
    1. c:plotArea is NOT a direct child of the chartSpace root element —
       it's nested at chartSpace/c:chart/c:plotArea. The previous version
       used .find(qn('c:plotArea')) directly on chart._element, which
       only searches immediate children and therefore always silently
       returned None — caught by the bare except below, so this function
       has never actually applied a manual layout in ANY renderer. Fixed
       by searching descendants with './/'.
    2. wMode/hMode must be set explicitly to 'edge' alongside xMode/yMode
       — they default to 'factor' (a scaling multiplier, not an absolute
       fraction) when omitted per the OOXML spec.
    """
    try:
        plot_area = chart._element.find('.//' + qn('c:plotArea'))
        if plot_area is None:
            return
        old_layout = plot_area.find(qn('c:layout'))
        if old_layout is not None:
            plot_area.remove(old_layout)
        layout = etree.Element(qn('c:layout'))
        plot_area.insert(0, layout)
        manual = etree.SubElement(layout, qn('c:manualLayout'))
        etree.SubElement(manual, qn('c:layoutTarget')).set('val', 'inner')
        etree.SubElement(manual, qn('c:xMode')).set('val', 'edge')
        etree.SubElement(manual, qn('c:yMode')).set('val', 'edge')
        etree.SubElement(manual, qn('c:wMode')).set('val', 'edge')
        etree.SubElement(manual, qn('c:hMode')).set('val', 'edge')
        etree.SubElement(manual, qn('c:x')).set('val', str(x))
        etree.SubElement(manual, qn('c:y')).set('val', str(y))
        etree.SubElement(manual, qn('c:w')).set('val', str(w))
        etree.SubElement(manual, qn('c:h')).set('val', str(h))
    except Exception:
        pass


def donut_center_point(left_in: float, top_in: float, w_in: float, chart_h: float) -> tuple:
    """Returns (hole_cx, hole_cy) for the donut ring's TRUE center, computed
    from the same DONUT_PLOT_* fractions passed to _set_manual_plot_layout —
    always matches the ring exactly, regardless of renderer."""
    hole_cx = left_in + w_in * (DONUT_PLOT_X + DONUT_PLOT_W / 2)
    hole_cy = top_in + chart_h * (DONUT_PLOT_Y + DONUT_PLOT_H / 2)
    return hole_cx, hole_cy


def add_donut_center_label(slide, lines: list, hole_cx: float, hole_cy: float, w_in: float):
    """
    Multi-line donut center overlay with per-line font control — each item
    in `lines` is (text, size_pt, bold, color_hex). Position with
    donut_center_point() so it lines up with a plot pinned via
    _set_manual_plot_layout(chart, DONUT_PLOT_X, DONUT_PLOT_Y, DONUT_PLOT_W, DONUT_PLOT_H).
    """
    tb_h = sum(0.30 if size >= 16 else 0.20 for _, size, _, _ in lines)
    tb_w = w_in * 0.6
    tb = slide.shapes.add_textbox(
        _inches(hole_cx - tb_w / 2), _inches(hole_cy - tb_h / 2),
        _inches(tb_w), _inches(tb_h)
    )
    tb.text_frame.word_wrap = False
    for idx, (text, size, bold, color) in enumerate(lines):
        p = tb.text_frame.paragraphs[0] if idx == 0 else tb.text_frame.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = text
        r.font.name  = lm.FONT_NAME
        r.font.size  = Pt(size)
        r.font.bold  = bold
        r.font.color.rgb = _rgb(color)



def add_disabled_info_card(slide, title: str, message: str,
                           left_in=0, top_in=0, w_in=5, h_in=5):
    """
    'Disabled' state card — matches the Infima dashboard's Dark Web
    Exposures disabled view: left-aligned title with a small 'Disabled'
    pill inline right after it (not top-right like the Live Data badge),
    and the API's message text centered in the card body.

    Pill uses CLR_RED — this theme's approved 'red' (a yellow-green PMS
    shade, not literal red/pink) — so it stays within the brand palette
    even though the reference screenshot shows a literal pink/red pill.
    """
    PAD = 0.24

    # Card background — plain white, light gray border (no colored
    # border like add_info_card, which is a different visual language).
    card = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(left_in), _inches(top_in), _inches(w_in), _inches(h_in)
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    card.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
    card.line.width = Pt(1)

    # Title (left-aligned, bold, dark)
    TITLE_SIZE = 13
    title_box = slide.shapes.add_textbox(
        _inches(left_in + PAD), _inches(top_in + PAD),
        _inches(3.0), _inches(0.32)
    )
    title_box.text_frame.word_wrap = False
    tp = title_box.text_frame.paragraphs[0]
    tr = tp.add_run()
    tr.text = title
    tr.font.name = lm.FONT_NAME
    tr.font.size = Pt(TITLE_SIZE)
    tr.font.bold = True
    tr.font.color.rgb = RGBColor(0x1E, 0x2A, 0x3A)

    # "Disabled" pill, positioned right after the measured title width.
    # Estimate is deliberately generous (wide) — better a slightly bigger
    # gap than a clipped/overlapping title.
    title_w_in = len(title) * TITLE_SIZE * 0.70 / 72.0
    pill_left  = left_in + PAD + title_w_in + 0.22
    pill_w, pill_h = 0.85, 0.27

    r = int(CLR_RED[1:3], 16); g = int(CLR_RED[3:5], 16); b = int(CLR_RED[5:7], 16)
    tint_hex = '#%02X%02X%02X' % (
        min(255, int(r + (255 - r) * 0.85)),
        min(255, int(g + (255 - g) * 0.85)),
        min(255, int(b + (255 - b) * 0.85)),
    )

    pill = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        _inches(pill_left), _inches(top_in + PAD + 0.01),
        _inches(pill_w), _inches(pill_h)
    )
    _set_shape_adj(pill, 50000)
    pill.fill.solid()
    pill.fill.fore_color.rgb = _rgb(tint_hex)
    pill.line.fill.background()

    ptf = pill.text_frame
    ptf.margin_left = Inches(0.02); ptf.margin_right = Inches(0.02)
    ptf.margin_top = Inches(0.01); ptf.margin_bottom = Inches(0.01)
    pp = ptf.paragraphs[0]
    pp.alignment = PP_ALIGN.CENTER
    pr = pp.add_run()
    pr.text = 'Disabled'
    pr.font.name = lm.FONT_NAME
    pr.font.size = Pt(8)
    pr.font.bold = False
    pr.font.color.rgb = _rgb(CLR_RED)

    # Message — centered in the card body
    msg_box = slide.shapes.add_textbox(
        _inches(left_in + 0.4), _inches(top_in + h_in * 0.42),
        _inches(w_in - 0.8), _inches(0.6)
    )
    msg_box.text_frame.word_wrap = True
    mp = msg_box.text_frame.paragraphs[0]
    mp.alignment = PP_ALIGN.CENTER
    mr = mp.add_run()
    mr.text = message
    mr.font.name = lm.FONT_NAME
    mr.font.size = Pt(11)
    mr.font.color.rgb = RGBColor(0xA0, 0xA8, 0xB8)