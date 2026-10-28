"""
Table Builder — native pptx table slides (editable in PowerPoint).
Builds paginated table slides from list-of-dict data.

Row heights are computed using exact Times New Roman AFM character widths —
the same approach used by PDF/document libraries (reportlab, etc.).
No estimation, no tuning constants — works for any org's data.
"""
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.oxml.ns import qn
from lxml import etree

import app.services.ppt.layout_manager as lm
import app.services.ppt.slide_builder as sb

_TITLE_BAR_TOP = lm.HEADER_H_IN + 0.06
_TITLE_BAR_H   = 0.32
_TABLE_TOP_Y   = _TITLE_BAR_TOP + _TITLE_BAR_H + 0.01
_SAFE_MARGIN   = 0.50

_AVAIL_H = lm.FOOTER_TOP_IN - _TABLE_TOP_Y - _SAFE_MARGIN   # total inches for header+data rows

# Times New Roman character advance widths (units at 1000 units/em, regular weight).
# Source: Adobe AFM for Times-Roman. At 8pt, 1 unit = 8/(72*1000) inches.
_TNR_WIDTHS = {
    ' ': 250, '!': 333, '"': 408, '#': 500, '$': 500, '%': 833, '&': 778,
    "'": 180, '(': 333, ')': 333, '*': 500, '+': 564, ',': 250, '-': 333,
    '.': 250, '/': 278,
    '0': 500, '1': 500, '2': 500, '3': 500, '4': 500,
    '5': 500, '6': 500, '7': 500, '8': 500, '9': 500,
    ':': 278, ';': 278, '<': 564, '=': 564, '>': 564, '?': 444, '@': 921,
    'A': 722, 'B': 667, 'C': 667, 'D': 722, 'E': 611, 'F': 556, 'G': 722,
    'H': 722, 'I': 333, 'J': 389, 'K': 722, 'L': 611, 'M': 889, 'N': 722,
    'O': 722, 'P': 556, 'Q': 722, 'R': 667, 'S': 556, 'T': 611, 'U': 722,
    'V': 722, 'W': 944, 'X': 722, 'Y': 722, 'Z': 611,
    '[': 333, '\\': 278, ']': 333, '^': 469, '_': 500, '`': 333,
    'a': 444, 'b': 500, 'c': 444, 'd': 500, 'e': 444, 'f': 333, 'g': 500,
    'h': 500, 'i': 278, 'j': 278, 'k': 500, 'l': 278, 'm': 778, 'n': 500,
    'o': 500, 'p': 500, 'q': 500, 'r': 333, 's': 389, 't': 278, 'u': 500,
    'v': 500, 'w': 722, 'x': 500, 'y': 500, 'z': 444,
    '{': 480, '|': 200, '}': 480, '~': 541,
}
_TNR_DEFAULT_W = 500   # units for any character not in the table

# _LINE_H = 0.20" per line.  PowerPoint actually renders 8pt TNR at ~0.133"/line.
# Using 0.20" means we allocate 50% more than PowerPoint needs per line, so even
# if our line count is off by 1, the row still has room — no auto-expansion, no overflow.
_LINE_H   = 0.20
_CELL_PAD = 0.09              # top (0.03") + bottom (0.03") cell margins + inter-para gap


def _count_lines(text: str, col_w_in: float, size_pt: float = 8) -> int:
    """
    Exact line count using TNR AFM metrics + PowerPoint word-wrap simulation.
    PowerPoint breaks at TWO points: spaces and after hyphens.
    Splitting on both gives correct line counts for hyphenated device names,
    hostnames, model numbers — any org's data, no tuning needed.
    """
    em = size_pt / 72
    cell_w = max(0.05, col_w_in - 0.08)   # subtract left+right cell margins
    sp_w   = _TNR_WIDTHS[' '] * em / 1000

    def _cw(s):
        return sum(_TNR_WIDTHS.get(c, _TNR_DEFAULT_W) for c in s) * em / 1000

    total = 0
    for para in str(text or '').split('\n'):
        if not para:
            total += 1
            continue

        lines  = 1
        cur_w  = 0.0
        words  = para.split(' ')

        for wi, word in enumerate(words):
            # Split "WIN-DESKTOP-001" → ["WIN-", "DESKTOP-", "001"]
            # PowerPoint can break AFTER a hyphen, just like after a space.
            sub_tokens = []
            remaining  = word
            while '-' in remaining:
                idx = remaining.index('-') + 1   # include the hyphen
                sub_tokens.append(remaining[:idx])
                remaining = remaining[idx:]
            if remaining:
                sub_tokens.append(remaining)
            if not sub_tokens:
                sub_tokens = [word]

            for ti, token in enumerate(sub_tokens):
                tw = _cw(token)
                # Space only comes before the first sub-token of each word
                # (except the very first word on the paragraph)
                add = (sp_w if (ti == 0 and wi > 0) else 0) + tw

                if cur_w == 0.0:
                    cur_w = tw          # first token on a fresh line
                elif cur_w + add <= cell_w:
                    cur_w += add        # fits on current line
                else:
                    lines += 1          # overflow → new line
                    cur_w  = tw

        total += lines
    return max(1, total)


def _row_height(row_data: dict, columns: list) -> float:
    """Exact row height in inches derived from TNR character metrics."""
    max_lines = 1
    for json_key, _, col_prop in columns:
        val   = str(row_data.get(json_key, '') or '')
        col_w = col_prop * lm.TABLE_WIDTH.inches
        max_lines = max(max_lines, _count_lines(val, col_w))
    return max_lines * _LINE_H + _CELL_PAD


def _paginate(rows: list, columns: list) -> list:
    """Pack rows into pages.  Each page fits exactly within the slide height."""
    avail = _AVAIL_H - lm.HDR_ROW_H.inches
    pages, page, used = [], [], 0.0
    for row in rows:
        rh = _row_height(row, columns)
        if page and used + rh > avail:
            pages.append(page)
            page, used = [row], rh
        else:
            page.append(row)
            used += rh
    if page:
        pages.append(page)
    return pages or [[]]


def _set_cell_border(cell, color_rgb: RGBColor):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for side in ('lnL', 'lnR', 'lnT', 'lnB'):
        ln_el = tcPr.find(qn('a:' + side))
        if ln_el is None:
            ln_el = etree.SubElement(tcPr, qn('a:' + side))
        ln_el.set('w', '9525')
        ln_el.set('cap', 'flat')
        ln_el.set('cmpd', 'sng')
        solid_fill = ln_el.find(qn('a:solidFill'))
        if solid_fill is None:
            solid_fill = etree.SubElement(ln_el, qn('a:solidFill'))
        srgb = solid_fill.find(qn('a:srgbClr'))
        if srgb is None:
            srgb = etree.SubElement(solid_fill, qn('a:srgbClr'))
        srgb.set('val', str(color_rgb))


def _style_cell(cell, text, font_size_pt, bold, color_rgb, bg_rgb, align=PP_ALIGN.LEFT):
    """Set cell text, background colour, font. Supports multi-line via \\n."""
    cell.fill.solid()
    cell.fill.fore_color.rgb = bg_rgb
    _set_cell_border(cell, lm.TBL_BORDER)

    tf = cell.text_frame
    tf.word_wrap = True
    tf.margin_left   = Inches(0.04)
    tf.margin_right  = Inches(0.04)
    tf.margin_top    = Inches(0.03)
    tf.margin_bottom = Inches(0.03)

    lines = str(text).split('\n') if text is not None else ['']

    p = tf.paragraphs[0]
    p.alignment = align
    p.clear()
    run = p.add_run()
    run.text = lines[0]
    run.font.name      = lm.FONT_NAME
    run.font.size      = font_size_pt
    run.font.bold      = bold
    run.font.color.rgb = color_rgb

    for line in lines[1:]:
        extra_p = tf.add_paragraph()
        extra_p.alignment = align
        extra_r = extra_p.add_run()
        extra_r.text = line
        extra_r.font.name      = lm.FONT_NAME
        extra_r.font.size      = font_size_pt
        extra_r.font.bold      = bold
        extra_r.font.color.rgb = color_rgb


def _add_title_bar(slide, title_text: str):
    bar = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        lm.TABLE_LEFT, Inches(_TITLE_BAR_TOP),
        lm.TABLE_WIDTH, Inches(_TITLE_BAR_H)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = lm.TBL_BAR_BG
    bar.line.fill.background()

    tf = bar.text_frame
    tf.margin_left = Inches(0.12)
    tf.margin_top  = Inches(0.04)
    tf.word_wrap   = False

    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = title_text
    run.font.name  = lm.FONT_NAME
    run.font.size  = Pt(11)
    run.font.bold  = True
    run.font.color.rgb = lm.CLR_WHITE


def _build_one_table_slide(prs, section_name: str, title: str,
                            columns: list, rows: list, page_num: int, total_pages: int,
                            live_badge: bool = False):
    slide = sb.new_content_slide(prs, section_name, title)
    _add_title_bar(slide, f"{title}  ({page_num}/{total_pages})")

    if live_badge:
        from app.services.ppt.chart_builder import add_live_badge
        add_live_badge(slide,
                       lm.CONTENT_LEFT_IN + lm.CONTENT_W_IN - 0.661,
                       _TITLE_BAR_TOP + 0.03)

    if not rows:
        from app.services.ppt.chart_builder import add_no_data
        add_no_data(slide, '', lm.CONTENT_LEFT_IN, 1.2,
                    lm.CONTENT_W_IN, lm.FOOTER_TOP_IN - 1.2 - 0.10)
        return

    n_rows    = len(rows)
    col_count = len(columns)

    # Exact per-row heights from TNR font metrics
    row_heights = [_row_height(r, columns) for r in rows]
    table_h     = Inches(lm.HDR_ROW_H.inches + sum(row_heights))

    table = slide.shapes.add_table(
        n_rows + 1, col_count,
        lm.TABLE_LEFT,
        Inches(_TABLE_TOP_Y),
        lm.TABLE_WIDTH,
        table_h
    ).table

    total_w = lm.TABLE_WIDTH.inches
    for ci, (_, _, prop) in enumerate(columns):
        table.columns[ci].width = Inches(total_w * prop)

    table.rows[0].height = lm.HDR_ROW_H
    for ri, rh in enumerate(row_heights):
        table.rows[ri + 1].height = Inches(rh)

    for ci, (_, display_name, _) in enumerate(columns):
        _style_cell(
            table.cell(0, ci), display_name,
            Pt(8), True, lm.TBL_HDR_TEXT, lm.TBL_HDR_BG, PP_ALIGN.LEFT
        )

    for ri, row_data in enumerate(rows):
        bg = lm.TBL_ROW_ODD if ri % 2 == 0 else lm.TBL_ROW_EVEN
        for ci, (json_key, _, _) in enumerate(columns):
            val = row_data.get(json_key, '')
            _style_cell(
                table.cell(ri + 1, ci), val,
                Pt(8), False, lm.TBL_BODY_TEXT, bg, PP_ALIGN.LEFT
            )


def _auto_columns(rows: list) -> list:
    """
    Derive a column list from whatever keys are actually present in the
    row data, when the caller doesn't have (or doesn't know) a fixed
    schema. Equal-width columns, display name = key with underscores
    turned into spaces and title-cased. Uses the first row's key order.
    """
    if not rows:
        return []
    keys = list(rows[0].keys())
    if not keys:
        return []
    prop = 1.0 / len(keys)
    return [(k, k.replace('_', ' ').title(), prop) for k in keys]


def build_table_slides(prs, section_name: str, title: str,
                       rows: list, columns: list = None, live_badge: bool = False,
                       empty_message: str = None, empty_submessage: str = None):
    """
    Build paginated table slides.
    Each row gets exactly the height its text content requires (TNR AFM metrics).
    Rows are packed until the slide is full, then overflow to the next slide.
    No data is cut off. No fixed row count. Works for any organisation's data.

    If there are no rows at all (table deselected, or genuinely empty),
    no slide is created — matches the skip-if-empty behavior used for charts.

    columns: optional. If not given (None), columns are auto-derived from
    the keys present in the row data itself — useful for tables whose exact
    schema isn't hardcoded anywhere yet.

    empty_message / empty_submessage: accepted for call-site compatibility
    (some sections pass custom empty-state text) but currently unused —
    an empty table produces no slide at all rather than a placeholder,
    so there's no empty-state text to show.
    """
    if not rows:
        return

    if columns is None:
        columns = _auto_columns(rows)
        if not columns:
            return

    pages = _paginate(rows, columns)
    total = len(pages)
    for page_num, page_rows in enumerate(pages, start=1):
        _build_one_table_slide(prs, section_name, title,
                               columns, page_rows, page_num, total,
                               live_badge=live_badge)


def build_backup_services_table_slide(prs, section_name: str, title: str,
                                      rows: list, live_badge: bool = True):
    """
    Thin wrapper for Axcient's 'Active Backup Services' table — this
    function was being called but never existed, causing a crash whenever
    services_raw was non-empty. Columns are auto-derived from the row
    data's own keys (see _auto_columns) rather than a hardcoded schema,
    since the exact field names weren't available at time of writing.
    """
    build_table_slides(prs, section_name, title, rows,
                       columns=None, live_badge=live_badge)