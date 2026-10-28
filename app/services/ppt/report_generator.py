"""
Report Generator — Orchestrates the full universal PPT report.

Flow:
  1. Cover slide
  2. For each integration key present in json_data AND registered in REGISTRY:
       a. Section divider slide
       b. Integration-specific chart + table slides
  3. Returns BytesIO with the complete .pptx

Missing data handling:
  - If an integration key is absent from json_data → its slides are skipped entirely.
  - If a specific chart's data is missing within a section → chart_builder shows
    a "Data Not Available" placeholder in that slot.
"""
import logging
import math
import os
from io import BytesIO
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

import app.services.ppt.layout_manager as lm
import app.services.ppt.slide_builder  as sb
from app.services.ppt.slide_registry   import REGISTRY

logger = logging.getLogger(__name__)


# ── Content-area layout constants ─────────────────────────────────────────────
# Slide: 10" × 5.625"  |  Header bottom: 0.45"  |  Footer top: 5.35"
# Vertical: start 2.5 cm below header, end 3 cm above footer
# Horizontal: 0.40" symmetric left/right margins
_C_LEFT = 0.40
_C_TOP  = 0.60
_C_W    = 9.20
_C_H    = 5.35 - (1.0 / 2.54) - _C_TOP   # footer_top - 1 cm - top  ≈ 4.36"


def _parse_items(raw) -> list:
    """
    Parse the 'content' field into a normalised list of tuples:
      ('bullet', text, level) — for {text, level?} items and plain strings
      ('hd',     heading, detail) — for {"label": "heading", "detail": "body"} or legacy single-key items
      ('plain',  text)        — for {"label": "", "detail": "..."} — no bullet, no bold

    label/detail format (preferred):
      - label non-empty + detail non-empty  → ('hd', label, detail)   bold heading + body
      - label empty     + detail non-empty  → ('plain', detail)        plain paragraph, no bullet
    """
    if not raw:
        return []
    if isinstance(raw, str):
        return [('bullet', p.strip(), 0) for p in raw.split('\n') if p.strip()]
    if not isinstance(raw, list):
        return [('bullet', str(raw), 0)]

    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        keys = list(item.keys())

        if 'text' in item:
            text  = item['text'].strip()
            level = item.get('level', 0)
            extras = [str(v) for k, v in item.items()
                      if k not in ('text', 'level') and v]
            if extras:
                text = f"{text}  ·  {'  ·  '.join(extras)}"
            if text:
                result.append(('bullet', text, level))

        elif 'label' in item or 'detail' in item:
            label  = str(item.get('label', '')).strip()
            detail = str(item.get('detail', '')).strip()
            if detail:
                if label:
                    result.append(('hd', label, detail))
                else:
                    result.append(('plain', detail))

        elif len(keys) == 1:
            # Legacy single-key format: {"Heading": "detail"} — kept for backward compatibility
            heading = keys[0].strip()
            detail  = str(item[keys[0]]).strip()
            if detail:
                result.append(('hd', heading, detail))

    return result


def _paginate_items(items: list, font_pt: float, area_w: float = None, area_h: float = None) -> list:
    """
    Split parsed content items into page-sized buckets that fit within area_h.
    bullet items  → wrapped lines of text
    hd items      → 1 heading line + wrapped detail lines
    area_w / area_h override _C_W / _C_H (used for narrow text columns, e.g. AI slide).
    """
    w = area_w if area_w is not None else _C_W
    h = area_h if area_h is not None else _C_H
    line_h_in      = (font_pt + 4) / 72.0
    chars_main     = max(40, int(w * 72 / (font_pt * 0.38)))
    chars_detail   = max(40, int((w - 0.35) * 72 / (font_pt * 0.38)))
    max_lines      = max(3, int(h / line_h_in))

    pages, current, used = [], [], 0
    for item in items:
        if item[0] == 'bullet':
            n = max(1, math.ceil(len(item[1]) / chars_main))
        elif item[0] == 'plain':
            n = max(1, math.ceil(len(item[1]) / chars_main))
        else:   # 'hd'
            n = 1 + max(1, math.ceil(len(item[2]) / chars_detail))
        if used + n > max_lines and current:
            pages.append(current)
            current, used = [item], n
        else:
            current.append(item)
            used += n
    if current:
        pages.append(current)
    return pages or [[]]


def _render_items(slide, items: list, font_pt: float,
                  area_left: float = None, area_top: float = None,
                  area_w: float = None, area_h: float = None):
    """
    Render parsed content items into the slide content area.
      bullet (level 0) → •   text
      bullet (level 1) →     ▪   text  (indented)
      hd               → •   Heading (bold) + indented detail paragraph
    area_left/top/w/h override defaults (used for custom layouts like AI slide).
    """
    if not items:
        return
    left = area_left if area_left is not None else _C_LEFT
    top  = area_top  if area_top  is not None else _C_TOP
    w    = area_w    if area_w    is not None else _C_W
    h    = area_h    if area_h    is not None else _C_H
    tb = slide.shapes.add_textbox(
        Inches(left), Inches(top),
        Inches(w),    Inches(h)
    )
    tf = tb.text_frame
    tf.word_wrap     = True
    tf.margin_left   = Inches(0)
    tf.margin_right  = Inches(0)
    tf.margin_top    = Inches(0)
    tf.margin_bottom = Inches(0)

    _INDENT_EMU = int(0.30 * 914400)   # 0.30" paragraph indent for detail lines
    para_idx = 0

    for item in items:
        itype = item[0]

        if itype == 'bullet':
            _, text, level = item
            p = tf.paragraphs[0] if para_idx == 0 else tf.add_paragraph()
            para_idx += 1
            p.alignment   = PP_ALIGN.JUSTIFY
            p.space_after = Pt(4)
            run = p.add_run()
            run.text           = f"\u2022   {text}" if level == 0 else f"    \u25aa   {text}"
            run.font.size      = Pt(font_pt)
            run.font.bold      = False
            run.font.name      = lm.FONT_NAME
            run.font.color.rgb = lm.CLR_TEXT

        elif itype == 'hd':
            _, heading, detail = item

            # ── Heading line (bold bullet) ────────────────────────────────
            p1 = tf.paragraphs[0] if para_idx == 0 else tf.add_paragraph()
            para_idx += 1
            p1.alignment   = PP_ALIGN.LEFT
            p1.space_after = Pt(2)
            r1 = p1.add_run()
            r1.text           = f"\u2022   {heading}"
            r1.font.size      = Pt(font_pt)
            r1.font.bold      = True
            r1.font.name      = lm.FONT_NAME
            r1.font.color.rgb = lm.CLR_TEXT

            # ── Detail paragraph (normal weight, indented) ────────────────
            if detail:
                p2 = tf.add_paragraph()
                para_idx += 1
                p2.alignment   = PP_ALIGN.JUSTIFY
                p2.space_after = Pt(7)
                pPr = p2._p.get_or_add_pPr()
                pPr.set('marL', str(_INDENT_EMU))
                pPr.set('indent', '0')
                r2 = p2.add_run()
                r2.text           = detail
                r2.font.size      = Pt(font_pt)
                r2.font.bold      = False
                r2.font.name      = lm.FONT_NAME
                r2.font.color.rgb = lm.CLR_TEXT

        elif itype == 'plain':
            _, text = item
            p = tf.paragraphs[0] if para_idx == 0 else tf.add_paragraph()
            para_idx += 1
            p.alignment   = PP_ALIGN.JUSTIFY
            p.space_after = Pt(7)
            run = p.add_run()
            run.text           = text
            run.font.size      = Pt(font_pt)
            run.font.bold      = False
            run.font.name      = lm.FONT_NAME
            run.font.color.rgb = lm.CLR_TEXT


# ── Slide content helpers ──────────────────────────────────────────────────────

_SLIDE5_FIXED_LABELS = [
    "Workstations and Laptops",
    "Physical Servers",
    "Virtual Servers",
    "Locations",
    "Users",
]


def _parse_slide5_items(raw) -> list:
    """
    Parse slide 5 content into stat + plain items.
      Non-empty label  → ('stat', value_or_0, label)   value shown red before label
      Empty label      → ('plain', detail)              plain paragraph, no bullet
    Falls back to fixed labels with '0' when no stat items are found.
    """
    result = []
    if raw and isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            label  = str(item.get('label', '')).strip()
            detail = str(item.get('detail', '')).strip()
            if label:
                result.append(('stat', detail if detail else '0', label))
            elif detail:
                result.append(('plain', detail))
    if not any(it[0] == 'stat' for it in result):
        fixed  = [('stat', '0', lbl) for lbl in _SLIDE5_FIXED_LABELS]
        plains = [it for it in result if it[0] == 'plain']
        result = fixed + plains
    return result


def _render_slide5_items(slide, items: list, font_pt: float = 12.0):
    """
    Render slide 5 content area.
      stat  → ▪ [red bold value]   label text
      plain → plain justified paragraph, no bullet
    A blank spacer line separates the stat block from the first plain paragraph.
    """
    if not items:
        return
    tb = slide.shapes.add_textbox(
        Inches(_C_LEFT), Inches(_C_TOP),
        Inches(_C_W),    Inches(_C_H)
    )
    tf = tb.text_frame
    tf.word_wrap     = True
    tf.margin_left   = Inches(0)
    tf.margin_right  = Inches(0)
    tf.margin_top    = Inches(0)
    tf.margin_bottom = Inches(0)

    para_idx  = 0
    had_stat  = False
    added_gap = False

    for item in items:
        itype = item[0]

        if itype == 'stat':
            had_stat = True
            _, value, label = item
            p = tf.paragraphs[0] if para_idx == 0 else tf.add_paragraph()
            para_idx += 1
            p.alignment   = PP_ALIGN.LEFT
            p.space_after = Pt(3)

            r_bullet = p.add_run()
            r_bullet.text           = "▪   "
            r_bullet.font.size      = Pt(font_pt)
            r_bullet.font.bold      = False
            r_bullet.font.name      = lm.FONT_NAME
            r_bullet.font.color.rgb = lm.HEADER_BG       # dark green square

            r_val = p.add_run()
            r_val.text           = value
            r_val.font.size      = Pt(font_pt)
            r_val.font.bold      = True
            r_val.font.name      = lm.FONT_NAME
            r_val.font.color.rgb = lm.CLR_TEXT

            r_lbl = p.add_run()
            r_lbl.text           = f"   {label}"
            r_lbl.font.size      = Pt(font_pt)
            r_lbl.font.bold      = False
            r_lbl.font.name      = lm.FONT_NAME
            r_lbl.font.color.rgb = lm.CLR_TEXT

        elif itype == 'plain':
            if had_stat and not added_gap:
                p_gap = tf.add_paragraph()
                para_idx += 1
                p_gap.space_after = Pt(6)
                r_gap = p_gap.add_run()
                r_gap.text           = ""
                r_gap.font.size      = Pt(font_pt)
                r_gap.font.name      = lm.FONT_NAME
                added_gap = True

            p = tf.paragraphs[0] if para_idx == 0 else tf.add_paragraph()
            para_idx += 1
            p.alignment   = PP_ALIGN.JUSTIFY
            p.space_after = Pt(10)
            run = p.add_run()
            run.text           = item[1]
            run.font.size      = Pt(font_pt)
            run.font.bold      = False
            run.font.name      = lm.FONT_NAME
            run.font.color.rgb = lm.CLR_TEXT


def _add_slide5(prs, content_entry: dict = None):
    """Build the Current Management and Maintenance slide with stat + plain layout."""
    slide = _make_slide(prs, "Current Management and Maintenance", "")
    raw   = content_entry.get('content') if content_entry else None
    _render_slide5_items(slide, _parse_slide5_items(raw))
    return slide


def _normalize_rows(rows: list) -> list:
    """
    Ensure all rows have the same set of keys.
    Handles the case where each row uses its heading as the column name
    (e.g. {"number":"1", "Core Security Controls...": "detail text"}).
    Those are collapsed into a consistent {"number": X, "detail": "Heading: value"} form.
    """
    if not rows:
        return rows
    all_key_sets = [set(r.keys()) for r in rows]
    common_keys  = set.intersection(*all_key_sets)
    # Already consistent — nothing to do
    if all(set(r.keys()) == set(rows[0].keys()) for r in rows):
        return rows
    # Normalize: keep common keys, merge unique keys into a 'detail' field
    normalized = []
    for row in rows:
        new_row = {k: row[k] for k in common_keys if k in row}
        unique_pairs = [(k, row[k]) for k in row if k not in common_keys]
        if unique_pairs:
            # Combine heading + value: "Heading Title: value text"
            new_row['detail'] = '\n'.join(f"{k}: {v}" for k, v in unique_pairs)
        normalized.append(new_row)
    return normalized


def _fill_table(slide, rows: list) -> list:
    """
    Render a list-of-dict table onto the slide within the safe content area.
    - Auto-detects narrow columns (number/id) and gives them less width.
    - Estimates each row's height from its text content so nothing overflows.
    - Returns any rows that did not fit (caller should continue on a new slide).
    """
    if not rows:
        return []

    rows      = _normalize_rows(rows)
    cols      = list(rows[0].keys())
    n_cols    = len(cols)
    font_pt   = 12.0
    HDR_H_IN  = 0.32   # fixed header row height

    # ── Column widths ─────────────────────────────────────────────────────────
    _NARROW  = {'no', 'num', 'number', '#', 'id', 'nr', 'sl'}

    # Move number/id columns to front — only for takeaways table (number+label+detail)
    if {'number', 'label', 'detail'}.issubset(set(cols)):
        cols = [c for c in cols if c.lower() in _NARROW] + \
               [c for c in cols if c.lower() not in _NARROW]

    _FIXED_W = {'age': 0.80, 'os_version': 1.20, 'device_name': 2.00}
    narrow_w = 0.50
    narrow_cols = [c for c in cols if c.lower() in _NARROW]
    fixed_cols  = [c for c in cols if c.lower() in _FIXED_W]
    wide_cols   = [c for c in cols if c.lower() not in _NARROW and c.lower() not in _FIXED_W]
    fixed_total = sum(_FIXED_W[c.lower()] for c in fixed_cols)
    wide_w      = (_C_W - narrow_w * len(narrow_cols) - fixed_total) / max(1, len(wide_cols))
    col_w = {}
    for c in cols:
        cl = c.lower()
        if cl in _NARROW:
            col_w[c] = narrow_w
        elif cl in _FIXED_W:
            col_w[c] = _FIXED_W[cl]
        else:
            col_w[c] = wide_w

    # ── Row height estimation ─────────────────────────────────────────────────
    def _row_h(row: dict) -> float:
        max_lines = 1
        for c, v in row.items():
            cpl   = max(10, int(col_w[c] * 72 / (font_pt * 0.48)))
            text  = '' if v is None else str(v).strip()
            lines = max(1, math.ceil(len(text) / cpl))
            max_lines = max(max_lines, lines)
        # per-line height + cell padding
        return max(0.28, max_lines * (font_pt + 3) / 72 + 0.10)

    # ── Fit rows within available height ─────────────────────────────────────
    available = _C_H - HDR_H_IN
    batch, used, remainder = [], 0.0, []
    for i, row in enumerate(rows):
        rh = _row_h(row)
        if used + rh <= available + 0.01:
            batch.append((row, rh))
            used += rh
        else:
            remainder = rows[i:]
            break

    if not batch:
        return rows   # nothing fits; caller must handle

    # ── Build table ───────────────────────────────────────────────────────────
    total_h = HDR_H_IN + used
    tbl = slide.shapes.add_table(
        len(batch) + 1, n_cols,
        Inches(_C_LEFT), Inches(_C_TOP),
        Inches(_C_W),    Inches(total_h)
    ).table

    # Set column widths
    for ci, c in enumerate(cols):
        tbl.columns[ci].width = int(col_w[c] * 914400)

    # Header row
    tbl.rows[0].height = int(HDR_H_IN * 914400)
    _HDR_NAMES = {
        'number': 'No.',
        'device_name': 'Device Name',
        'os_version': 'OS Version',
        'reason_for_upgrade': 'Reason for Upgrade',
        'reason_for_replacement': 'Reason for Replacement',
        'age': 'Age',
    }
    for ci, col in enumerate(cols):
        cell = tbl.cell(0, ci)
        cell.text = _HDR_NAMES.get(col.lower(), col.replace('_', ' ').title())
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0xA8, 0xD5, 0xB5)
        p   = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.runs[0] if p.runs else p.add_run()
        run.font.bold      = True
        run.font.size      = Pt(12)
        run.font.color.rgb = lm.CLR_DARK
        run.font.name      = lm.FONT_NAME

    # Data rows
    for ri, (row, rh) in enumerate(batch):
        tbl.rows[ri + 1].height = int(rh * 914400)
        fill = RGBColor(0xF5, 0xF5, 0xF5) if ri % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF)
        for ci, col in enumerate(cols):
            cell = tbl.cell(ri + 1, ci)
            val = row.get(col)
            cell.text = '' if val is None else str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = fill
            p   = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.JUSTIFY
            run = p.runs[0] if p.runs else p.add_run()
            run.font.size      = Pt(font_pt)
            run.font.name      = lm.FONT_NAME
            run.font.color.rgb = lm.CLR_TEXT

    return remainder


def _make_slide(prs, section_name: str, slide_title: str):
    """Create a blank slide with header + footer, ready for content."""
    slide = sb._blank_slide(prs)
    sb.add_header(slide, section_name, slide_title=slide_title,
                  font_size=25, header_height_in=0.46)
    sb.add_footer(slide)
    return slide


def _add_template_slide(prs, section_name: str, slide_title: str = '',
                        content_entry: dict = None, font_pt: float = 12.0,
                        force_empty_table: bool = False, default_row: dict = None):
    """
    Create a content slide, adding continuation slides automatically if text
    overflows the safe content area (0.40" symmetric margins, above footer).
    Tables are placed on the last slide in their own block.
    force_empty_table=True renders the table even when all data rows are empty
    (shows header + blank rows instead of skipping the table entirely).
    Returns the first slide created.
    """
    first = _make_slide(prs, section_name, slide_title)
    if not content_entry:
        return first

    items  = _parse_items(content_entry.get('content'))
    tables = content_entry.get('tables') or {}

    last_slide = first
    if items:
        pages = _paginate_items(items, font_pt)
        _render_items(first, pages[0], font_pt)
        for page in pages[1:]:
            cont = _make_slide(prs, section_name, slide_title)
            _render_items(cont, page, font_pt)
            last_slide = cont

    for rows in tables.values():
        # Skip rows where only sequence-number fields are non-empty (e.g. {"number":"1","label":"","detail":""})
        _SEQ_KEYS = {'no', 'num', 'number', '#', 'id', 'nr', 'sl'}
        filled_rows = [r for r in rows if any(
            v is not None and str(v).strip()
            for k, v in r.items() if k.lower() not in _SEQ_KEYS
        )]
        # Use filled rows when data exists; fall back to raw rows (empty) only
        # when force_empty_table is set — shows table skeleton instead of nothing.
        # If rows is empty [] but default_row provided, use 3 blank template rows.
        if force_empty_table and not rows and default_row:
            rows = [dict(default_row), dict(default_row), dict(default_row)]
        rows_to_render = filled_rows or (rows if force_empty_table and rows else [])

        # When force_empty_table: re-apply the template row's key schema so every
        # column (e.g. "age") appears even if the LLM omitted it from its response.
        if force_empty_table and rows and rows_to_render:
            template_keys = list(rows[0].keys())
            rows_to_render = [
                {k: r.get(k, '') for k in template_keys}
                for r in rows_to_render
            ]

        if rows_to_render:
            tbl_slide = last_slide
            if items:
                tbl_slide = _make_slide(prs, section_name, slide_title)
                last_slide = tbl_slide
            remaining = _fill_table(tbl_slide, rows_to_render)
            while remaining:
                tbl_slide  = _make_slide(prs, section_name, slide_title)
                last_slide = tbl_slide
                remaining  = _fill_table(tbl_slide, remaining)

    return first


def generate_pptx(json_data: dict, slide_content: list = None) -> BytesIO:
    """
    Generate a complete PowerPoint report from the standardised JSON data.

    Args:
        json_data: Full JSON dict — same structure produced by FrontendTransformer.

    Returns:
        BytesIO containing the .pptx file (seek position at 0).
    """
    prs = Presentation()
    prs.slide_width  = lm.SLIDE_WIDTH
    prs.slide_height = lm.SLIDE_HEIGHT

    org = json_data.get('organization', {})
    org_name  = org.get('name', 'Unknown Organisation')
    company   = org.get('company', '')
    period    = org.get('reporting_period', '')
    # Fix "Last 3" → "Last 3 Months" if reporting_period was not formatted correctly upstream
    if period.strip().lower().startswith('last ') and not period.strip().lower().endswith('months'):
        period = period.strip() + ' Months'
    exec_info = json_data.get('execution_info', {})
    gen_at    = exec_info.get('generated_at', org.get('report_date', ''))

    if gen_at:
        try:
            dt = datetime.fromisoformat(gen_at.replace('Z', '+00:00'))
            gen_display = dt.strftime('%B %d, %Y')
        except Exception:
            gen_display = gen_at
    else:
        gen_display = datetime.utcnow().strftime('%B %d, %Y')

    # ── Build content lookup by title (for LLM-generated slide content) ────────
    # Auto-extract llm_data.slides from json_data if not explicitly passed
    if slide_content is None:
        slide_content = (json_data.get('llm_data') or {}).get('slides')

    _cmap = {}
    if slide_content:
        for entry in slide_content:
            key = entry.get('title', '').lower().strip()
            _cmap[key] = entry

    def _c(title: str) -> dict:
        """Look up content entry by title (case-insensitive)."""
        return _cmap.get(title.lower().strip())

    logger.info(f"Building PPT for org='{org_name}' period='{period}'")
    sb.add_cover_slide(prs, org_name, company, period, gen_display)

    # ── Theory slides (AI-generated, fetched from Supabase in future) ─
    from app.services.ppt.sections import theory_section
    theory_section.build_slides(prs, json_data.get('theory', {}),
                                 agenda_entry=_c('agenda'),
                                 industry_entry=_c('industry trends'))

    # ── Slide 5: Current Management and Maintenance ──────────────────────────
    _add_slide5(prs, content_entry=_c('current management and maintenance'))

    # ── Slide 6: Customer Success Dashboard | Observations ───────────────────
    _add_template_slide(prs, "Customer Success Dashboard", "Observations",
                        content_entry=_c('customer success dashboard'))

    # ── Autotask charts under Customer Success Dashboard ─────────────────────
    _autotask_data = json_data.get('Autotask')
    if _autotask_data:
        from app.services.ppt.sections import autotask_section
        logger.info("  Building Customer Success Dashboard (Autotask charts)")
        try:
            autotask_section.build_slides(
                prs, _autotask_data,
                section_override='Customer Success Dashboard',
                skip_section_slide=True,
            )
        except Exception as exc:
            logger.error(f"  ERROR building Customer Success Dashboard: {exc}", exc_info=True)

    # ── Slides 7–23: Static template slides (native, no file dependency) ─────
    _add_template_slide(prs, "Management Summary Report", "Key Takeaways",
                        content_entry=_c('management summary report key takeaways'))  # 7
    _add_template_slide(prs, "Recent Accomplishments",
                        content_entry=_c('recent accomplishments'))                   # 8
    _add_template_slide(prs, "CX Metrics",
                        content_entry=_c('cx metrics'))                               # 9
    sb.add_section_slide(prs, "Open Technical Items", "")                             # 10
    _add_template_slide(prs, "Current Project Review",
                        content_entry=_c('current project review'))                   # 11
    _add_template_slide(prs, "Devices Under Management", "Recommended for Upgrade",
                        content_entry=_c('devices under management recommended for upgrade'),
                        force_empty_table=True)   # 12
    _add_template_slide(prs, "Devices Under Management", "Recommended for Replacement",
                        content_entry=_c('devices under management recommended for replacement'),
                        force_empty_table=True,
                        default_row={'device_name': '', 'age': '', 'os_version': '', 'reason_for_replacement': ''})  # 13
    _add_template_slide(prs, "Cybersecurity",
                        content_entry=_c('cybersecurity'))                            # 14
    _add_template_slide(prs, "Backup / Business Continuity",
                        content_entry=_c('backup / business continuity'))             # 15
    sb.add_section_slide(prs, "Strategic Initiatives", "")                            # 16
    _add_template_slide(prs, "Scheduled Projects",
                        content_entry=_c('scheduled projects'))                       # 17
    _add_template_slide(prs, "Recommended Services",
                        content_entry=_c('recommended services'))                     # 18
    _add_template_slide(prs, "Near-Term Priorities",
                        content_entry=_c('near-term priorities'))                     # 19

    # ── Slide 20: AI Essentials — text LEFT half, image RIGHT half ──────────────
    _CM       = 1 / 2.54
    _IMG_W    = 5.591 - 2 * _CM          # ~4.80"
    _IMG_TOP  = 0.46
    _IMG_H    = 5.35 - _IMG_TOP          # ~4.89"
    _IMG_LEFT = 0.0                          # image on LEFT half
    _TXT_LEFT = _IMG_LEFT + _IMG_W + 0.15   # ~4.95" — text starts right of image
    _TXT_W    = 10.0 - _TXT_LEFT - 0.30     # ~4.75" — right margin 0.30"

    # PIL imports at block level — always available regardless of image existence
    try:
        from PIL import Image as _PILImage
        from io import BytesIO as _AIBuf
        _pil_available = True
    except ImportError:
        _pil_available = False
        logger.warning("PIL not available — AI Essentials image will be skipped")

    def _place_ai_image(slide):
        """Place AI image on left half of slide. Safe no-op if image/PIL unavailable."""
        if not _pil_available or not os.path.exists(_img20_path):
            return
        try:
            with _PILImage.open(_img20_path) as _pil:
                _buf = _AIBuf()
                _pil.convert('RGB').save(_buf, format='PNG')
                _buf.seek(0)
            slide.shapes.add_picture(
                _buf,
                Inches(_IMG_LEFT), Inches(_IMG_TOP),
                Inches(_IMG_W),    Inches(_IMG_H)
            )
        except Exception as exc:
            logger.warning(f"Could not place AI image: {exc}")

    _slide20    = _make_slide(prs, "AI Essentials", "")
    _img20_path = os.path.join(os.path.dirname(__file__), 'assets', 'slide_20_AI_image.webp')
    _place_ai_image(_slide20)

    _ai_entry = _c('ai essentials')
    if _ai_entry:
        _ai_items = _parse_items(_ai_entry.get('content'))
        if _ai_items:
            _ai_pages = _paginate_items(_ai_items, 10.0, area_w=_TXT_W, area_h=_C_H)
            _render_items(_slide20, _ai_pages[0], 10.0,
                          area_left=_TXT_LEFT, area_top=_C_TOP,
                          area_w=_TXT_W, area_h=_C_H)

    _add_template_slide(prs, "Implementation Timeline",
                        content_entry=_c('implementation timeline'))                    # 21
    _add_template_slide(prs, "Budget and Timeline",
                        content_entry=_c('budget and timeline'))                       # 22
    _add_template_slide(prs, "Thank you for our continued partnership!",
                        content_entry=_c('thank you for our continued partnership!'))  # 23

    sb.add_section_slide(prs, "Appendix", "Detailed Integration Reports")

    def _has_section_data(value):
        """Return True only when an integration contains meaningful PPT data."""
        if isinstance(value, dict):
            return any(_has_section_data(item) for item in value.values())
        if isinstance(value, list):
            return any(_has_section_data(item) for item in value)
        return value not in (None, '', 0, False)

    for integration_key, build_fn in REGISTRY:
        section_data = json_data.get(integration_key)
        if not _has_section_data(section_data):
            logger.info(f"  Skipping {integration_key} — no meaningful data in JSON")
            continue

        # ConnectSecure needs reporting_period to decide live vs quarterly data
        if integration_key == 'ConnectSecure':
            section_data = {**section_data, 'reporting_period': period}

        logger.info(f"  Building section: {integration_key}")
        try:
            build_fn(prs, section_data)
        except Exception as exc:
            logger.error(f"  ERROR building {integration_key}: {exc}", exc_info=True)
            err_slide = sb.new_content_slide(prs, integration_key, "Error")
            from app.services.ppt.chart_builder import add_no_data
            add_no_data(err_slide, f"{integration_key} — rendering error: {exc}",
                        lm.CONTENT_LEFT_IN, lm.CONTENT_TOP_IN,
                        lm.CONTENT_W_IN, lm.CONTENT_H_IN)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    logger.info("PPT generation complete.")
    return buf
