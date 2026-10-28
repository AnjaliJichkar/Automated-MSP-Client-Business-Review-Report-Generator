"""Theory slides — AI-generated text slides inserted after the cover slide."""
import app.services.ppt.slide_builder as sb
from app.services.ppt.report_generator import _parse_items, _paginate_items, _render_items


def _new_slide(prs, title: str):
    slide = sb._blank_slide(prs)
    sb.add_header(slide, title)
    sb.add_footer(slide)
    return slide


def _build_slides(prs, title: str, raw_content, font_pt: float = 12.0):
    """Build one or more slides for a given title + content (any supported format)."""
    first = _new_slide(prs, title)
    items = _parse_items(raw_content)
    if not items:
        return
    pages = _paginate_items(items, font_pt)
    _render_items(first, pages[0], font_pt)
    for page in pages[1:]:
        _render_items(_new_slide(prs, title), page, font_pt)


def build_slides(prs, data: dict, agenda_entry: dict = None, industry_entry: dict = None):
    """
    Builds theory slides right after the cover slide.
      Slide(s): Agenda          — 12pt, level-aware bullets if structured content
      Slide(s): Industry Trends — 12pt bullets (plain or hd format)
      Slide:    Service Review  — full green section divider
    """
    agenda_raw   = agenda_entry.get('content')   if agenda_entry   else None
    industry_raw = industry_entry.get('content') if industry_entry else None

    _build_slides(prs, "Agenda",          agenda_raw,   font_pt=12.0)
    _build_slides(prs, "Industry Trends", industry_raw, font_pt=12.0)

    sb.add_section_slide(prs, "Service Review", "")
