"""Bitdefender section — Endpoint Security slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.table_builder as tb
import app.services.ppt.layout_manager as lm

SECTION = "Bitdefender"


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "Endpoint Security")

    data   = lm.normalize(data)
    charts = data.get('charts', {})
    tables = data.get('tables', {})

    # ── Slide 1: Risk Score + Inventory Summary ───────────────────────────────
    rs          = charts.get('riskscore_bitdefender') or {}
    inv         = charts.get('inventory_summary_bitdefender') or {}
    inv_summary = inv.get('summary', {}) or {}
    inv_count   = inv.get('count', {})   or {}

    # Parse value — may be an int or a string like '45%'
    def _parse_pct(v):
        if v is None: return None
        try: return float(str(v).replace('%', '').strip())
        except: return None

    rs_value     = _parse_pct(rs.get('value', 0)) or 0
    rs_impact    = rs.get('impact', 'Low Impact') or 'Low Impact'
    # Breakdown: all numeric fields in rs except value/impact/industrymodifier
    _skip = {'value', 'impact', 'industrymodifier'}
    _label_map = {
        'misconfigurations':  'Findings',
        'appvulnerabilities': 'App Vulnerabilities',
        'humanrisks':         'Human Risks',
    }
    _rs_breakdown = [
        (_label_map.get(k, k.replace('_', ' ').title()), v)
        for k, v in rs.items()
        if k.lower() not in _skip
    ]

    def _risk_fn(s, l, t, w, h):
        cb.add_security_risk_score(
            s, "Company Risk Score",
            score=rs_value, impact_label=rs_impact,
            breakdown_stats=_rs_breakdown,
            left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.85, t + 0.05)

    def _inv_fn(s, l, t, w, h):
        cb.add_inventory_donut_card(
            s, "Inventory Summary",
            summary=inv_summary, count=inv_count,
            left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.85, t + 0.05)

    has_rs  = bool(rs)
    has_inv = bool(inv_summary or inv_count)

    if has_rs or has_inv:
        # Bitdefender-specific exception: unlike other sections, a missing
        # chart here does NOT let the remaining one expand to fill the
        # slide — the two fixed half-slots always stay the same size, and
        # a missing chart just leaves its slot blank. Slide is skipped
        # only if both are missing.
        slide = sb.new_content_slide(prs, SECTION, "Risk Score & Inventory")
        l, r = sb.left_slot(), sb.right_slot()

        if has_rs:
            _risk_fn(slide, *l)
        if has_inv:
            _inv_fn(slide, *r)

    # ── Slide(s): Security Module Enablement Status (paginated) ──────────────
    module_raw = tables.get('networkinventory_bitdefender', [])
    if module_raw:
        cb.build_module_status_slides(
            prs, SECTION, "Security Module Enablement Status", module_raw
        )