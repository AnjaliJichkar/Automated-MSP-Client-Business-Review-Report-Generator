"""Axcient section — License Optimization, Account Protection, Backup Performance
& Backup Execution Health slides."""
from datetime import datetime
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.table_builder as tb
import app.services.ppt.layout_manager as lm

SECTION = "Axcient"

# Six distinct, on-theme colors spanning the palette's full darkness range
# (deep forest -> vivid lime) so all 6 lines stay easily distinguishable
# while every color still comes from the approved PMS-green constants.
_BACKUP_SERIES = [
    ('successful',          'Successful',          cb.CLR_SUCCESS),   # PMS 361
    ('unavailable',         'Unavailable',         cb.CLR_DANGER),    # PMS 356 (darkest)
    ('onboarding',          'Onboarding',          cb.CLR_BLUE),      # PMS 354 (primary)
    ('failed_or_partial',   'Failed or partial',   '#008C40'),        # PMS 355
    ('in_progress',         'In progress',         cb.CLR_YELLOW),    # PMS 381 (brightest/lime)
    ('troubled_onboarding', 'Troubled onboarding', cb.CLR_RED),       # PMS 375
]

# Same six statuses, reused for the SharePoint/User "backup execution
# health" donuts. Order fixed so a given status always gets the same
# color slide-to-slide; colors spread across the wheel (green / dark
# green / lime / gray / red / blue) rather than shades of one branch
# color, so adjacent slices never read as "the same" shade. Lives here
# (not in chart_builder.py) because it's pure Axcient business data —
# the rendering function it feeds is generic.
BACKUP_HEALTH_ORDER = [
    'successful', 'failed_or_partial', 'in_progress',
    'unavailable', 'troubled_onboarding', 'onboarding',
]

BACKUP_HEALTH_LABELS = {
    'successful':          'Successful',
    'failed_or_partial':   'Failed or partial',
    'in_progress':         'In progress',
    'unavailable':         'Unavailable',
    'troubled_onboarding': 'Troubled onboarding',
    'onboarding':          'Onboarding',
}

BACKUP_HEALTH_COLORS = {
    'successful':          cb.CLR_SUCCESS,   # PMS 361 — medium vivid green
    'failed_or_partial':   cb.CLR_DANGER,    # PMS 356 — dark green
    'in_progress':         cb.CLR_YELLOW,    # PMS 381 — vivid lime
    'unavailable':         '#3B5B35',        # neutral gray
    'troubled_onboarding': cb.CLR_RED,       # PMS 375 — yellow-green accent
    'onboarding':          cb.CLR_BLUE,      # PMS 354 — deep vivid green (primary)
}


def _fmt_date(iso_ts: str) -> str:
    """'2026-07-01T23:00:43Z' -> 'Jul 1'"""
    try:
        dt = datetime.strptime(iso_ts, '%Y-%m-%dT%H:%M:%SZ')
        return f"{dt.strftime('%b')} {dt.day}"
    except Exception:
        return str(iso_ts)[:10]

def _fmt_backup_date(iso_ts: str) -> str:
    """'2026-08-24T04:01:51Z' -> 'last Backup On: 24 August 2026'"""
    try:
        dt = datetime.strptime(iso_ts, '%Y-%m-%dT%H:%M:%SZ')
        return f"last Backup On: {dt.day} {dt.strftime('%B')} {dt.year}"
    except Exception:
        return ""


def _add_subtitle(slide, text: str, left_in: float, top_in: float, w_in: float):
    """Bold black subtitle line under a card title, e.g. 'Total protected users: 92'."""
    box = slide.shapes.add_textbox(
        Inches(left_in + 0.02), Inches(top_in + 0.20), Inches(w_in - 0.1), Inches(0.2)
    )
    p = box.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.name   = lm.FONT_NAME
    r.font.size   = Pt(8)
    r.font.bold   = True
    r.font.color.rgb = RGBColor(0x00, 0x00, 0x00)


def _estimate_text_width_in(text: str, size_pt: float, bold: bool = True) -> float:
    """
    Conservative Times New Roman width estimate (bold chars run wider
    than regular) — good enough to guarantee a safety margin without
    pulling in a full per-glyph metrics table.
    """
    per_char_em = 0.56 if bold else 0.50
    return len(text) * size_pt * per_char_em / 72.0


def _add_left_title(slide, title: str, left_in: float, top_in: float, w_in: float, badge_clearance: float = 0.95):
    """
    Left-aligned card title, width-limited to stop clear of the 'Live Data'
    badge — same visual convention as the native donut-chart titles
    (_set_chart_title uses PP_ALIGN.LEFT), so all three card titles in a
    row sit on the same baseline and never collide with the badge.

    Font size auto-shrinks (10pt floor 8pt) if the measured text would
    still reach into the badge's zone — guarantees no overlap regardless
    of small font-metric differences between PowerPoint and LibreOffice,
    rather than relying on a single fixed clearance guess.
    """
    available_w = w_in - badge_clearance
    size_pt = 10
    while size_pt > 8 and _estimate_text_width_in(title, size_pt) > available_w:
        size_pt -= 0.5

    box = slide.shapes.add_textbox(
        Inches(left_in), Inches(top_in + 0.04), Inches(available_w), Inches(0.32)
    )
    p = box.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.bold = True
    r.font.size = Pt(size_pt)
    r.font.name = lm.FONT_NAME
    r.font.color.rgb = RGBColor(0x24, 0x27, 0x2B)


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "License Optimization, Account Protection & Backup Performance")

    data   = lm.normalize(data)
    charts = data.get('charts', {})
    tables = data.get('tables', {})

    # ── Slide 1: License / Status / Coverage cards (3 across) ──────────────
    lic  = charts.get('license_optimization_overview') or {}
    stat = charts.get('protected_accounts_by_status') or {}
    cov  = charts.get('account_protection_coverage') or {}

    def _license_fn(s, l, t, w, h):
        billable = lic.get('billable_seats', 0)
        retained = lic.get('retained_free_accounts', 0)
        total    = lic.get('total_protected_users', billable + retained)
        cb.add_column_chart(
            s, "",   # title suppressed here — drawn below as a left-aligned
                      # textbox instead, so it can't collide with the badge
            labels=["Billable seats", "Retained free accounts"],
            values=[billable, retained],
            colors=[cb.CLR_BLUE, cb.CLR_GREEN],
            left_in=l, top_in=t, w_in=w, h_in=h
        )
        _add_left_title(s, "License optimization overview", l, t, w)
        _add_subtitle(s, f"Total protected users: {total}", l, t, w)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _status_fn(s, l, t, w, h):
        active   = stat.get('active', 0)
        deleted  = stat.get('deleted', 0)
        inactive = stat.get('inactive', 0)
        total    = stat.get('total', active + deleted + inactive)
        cb.add_donut_chart(
            s, "Protected accounts by status",
            labels=["Active", "Deleted", "Inactive"],
            values=[active, deleted, inactive],
            colors=[cb.CLR_GREEN, cb.CLR_RED, cb.CLR_BLUE],
            show_title=False,   # native PPTX title auto-position isn't guaranteed to
                                 # land on the same row as the badge — draw it manually
                                 # instead, same convention as _license_fn below
            center_label=[
                ("Total Protected", 9, False, '#6B7280'),
                ("Account",         9, False, '#6B7280'),
                (str(int(total)),  20, True,  '#000000'),
            ],
            left_in=l, top_in=t, w_in=w, h_in=h
        )
        _add_left_title(s, "Protected accounts by status", l, t, w)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _coverage_fn(s, l, t, w, h):
        protected   = cov.get('protected_users', 0)
        unprotected = cov.get('unprotected_users', 0)
        total       = cov.get('total_users', protected + unprotected)
        cb.add_donut_chart(
            s, "Account protection coverage",
            labels=["Protected users", "Unprotected users"],
            values=[protected, unprotected],
            colors=[cb.CLR_RED, cb.CLR_GREEN],
            show_title=False,   # same reasoning as _status_fn above
            center_label=[
                ("Total users",    9, False, '#6B7280'),   # was hardcoded bold via
                                                            # the string-API's idx==0
                                                            # rule — now explicit + unbold
                (str(int(total)), 20, True,  '#000000'),
            ],
            left_in=l, top_in=t, w_in=w, h_in=h
        )
        _add_left_title(s, "Account protection coverage", l, t, w)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Account & License Overview", [
        (lambda: bool(lic),  _license_fn,  "License Optimization Overview"),
        (lambda: bool(stat), _status_fn,   "Protected Accounts by Status"),
        (lambda: bool(cov),  _coverage_fn, "Account Protection Coverage"),
    ])

    # ── Slide 2:  backup performance trend (own slide) ───────────────
    trend_rows = charts.get('monthly_backup_trend') or []

    def _trend_fn(s, l, t, w, h):
        x_labels = []
        for i, row in enumerate(trend_rows):
            label = _fmt_date(row.get('timestamp', ''))
            x_labels.append(label if i % 3 == 0 else '')   # thin ticks to every 3rd day

        # Only include a series if it has at least one value > 0
        series_data = {}
        colors = []

        for key, display_name, color in _BACKUP_SERIES:
            values = [
                float(row.get(key, 0) or 0)
                for row in trend_rows
            ]

            # Do not draw completely empty/zero series
            if any(value > 0 for value in values):
                series_data[display_name] = values
                colors.append(color)

        cb.add_multi_series_trend_chart(
            s,
            "Backup performance trend",
            x_labels=x_labels,
            series_data=series_data,
            colors=colors,
            x_axis_title="Time Period",
            y_axis_title="Accounts",
            left_in=l,
            top_in=t,
            w_in=w,
            h_in=h
        )

     

    sb.build_dynamic_slide(prs, SECTION, "Backup Performance Trend", [
        (lambda: bool(trend_rows), _trend_fn, "Backup Performance Trend"),
    ])

    # ── Slide 3: SharePoint + User Backup Execution Health (2 donuts) ──────
    sp_breakdown   = charts.get('sharepoint_backup_execution_health') or {}
    user_breakdown = charts.get('user_backup_execution_health') or {}
    sp_last_backup = _fmt_backup_date(
               sp_breakdown.get('timestamp', ''))

    user_last_backup = _fmt_backup_date(
            user_breakdown.get('timestamp', ''))
    

    def _sp_health_fn(s, l, t, w, h):
        cb.add_backup_health_donut_card(
           s, "SharePoint backup execution health", sp_breakdown,
           order=BACKUP_HEALTH_ORDER,
           labels=BACKUP_HEALTH_LABELS,
           colors=BACKUP_HEALTH_COLORS,
           total_key='total_backed_up_sites',
           total_label = 'Total SharePoint Backup',
           last_backup_on=sp_last_backup,
           last_backup_align='left',
           left_in=l,
           top_in=t,
           w_in=w,
           h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _user_health_fn(s, l, t, w, h):
        cb.add_backup_health_donut_card(
            s, "User backup execution health", user_breakdown,
            order=BACKUP_HEALTH_ORDER,
            labels=BACKUP_HEALTH_LABELS,
            colors=BACKUP_HEALTH_COLORS,
            total_key='total_backed_up_users',
            total_label='Total User Backup',
            last_backup_on=user_last_backup,
            last_backup_align='right',
            left_in=l,
            top_in=t,
            w_in=w,
            h_in=h
             )
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Backup Execution Health", [
        (lambda: bool(sp_breakdown),   _sp_health_fn,   "SharePoint backup execution health"),
        (lambda: bool(user_breakdown), _user_health_fn, "User backup execution health"),
    ])

    # ── Slide 4: Active Backup Services (paginated table) ──────────────────
    services_raw = tables.get('active_backup_services', [])
    if services_raw:
        tb.build_backup_services_table_slide(
            prs, SECTION, "Active Backup Services", services_raw
        )

    # ── Slide 5: Backup Alerts & Failures — only when there IS data ────────
    # Explicit request: an empty backup_alerts list means "don't show this
    # slide at all" (not even an empty-state placeholder), unlike every
    # other table in this deck.
    alert_rows = tables.get('backup_alerts', [])
    if alert_rows:
        tb.build_table_slides(
            prs, SECTION, "Backup Alerts & Failures",
            rows=alert_rows, columns=None, live_badge=True
        )