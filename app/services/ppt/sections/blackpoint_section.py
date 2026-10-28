"""
Blackpoint section — Managed Detection & Response (MDR).

Slides:
    1. Section Divider
    2. SOC Escalations Activity (Table)
"""

from datetime import datetime

import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.table_builder as tb
import app.services.ppt.layout_manager as lm


SECTION = "Blackpoint"

# Month ordering map for chronological sorting (1..12)
_MONTH_ORDER = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

def _month_sort_key(k: str) -> int:
    """Return numeric month index for key k (case-insensitive). Unknowns sort last."""
    if not isinstance(k, str):
        return 999
    return _MONTH_ORDER.get(k.lower(), 999)


def build_slides(prs, data: dict):
    """
    Build all Blackpoint slides.

    Current implementation:
        • Section Divider
        • SOC Escalations Activity Table

    Future:
        • Monthly Endpoint Alerts
        • Monthly Cloud Alerts
    """

    sb.add_section_slide(
        prs,
        SECTION,
        "Managed Detection & Response"
    )

    data = lm.normalize(data)

    charts = data.get("charts", {}) or {}
    tables = data.get("tables", {}) or {}

    #
    # ------------------------------------------------------------
    # SOC Escalations Activity
    # ------------------------------------------------------------
    #

    soc_rows = tables.get("soc_escalations_activity", [])
    show_soc_table = "soc_escalations_activity" in tables

    monthly_data = charts.get("monthly_data", {}) or {}
    endpoint_alerts = monthly_data.get("monthly_endpoint_alerts", {}) or {}
    cloud_alerts = monthly_data.get("monthly_cloud_alerts", {}) or {}

    quarterly = charts.get("quaterly_data", {}) or charts.get("Quaterly_data", {}) or {}
    cloud_responses = quarterly.get("cloud_responses", []) or []
    soc_trend = quarterly.get("soc_response_activity_trend", {}) or {}

    if endpoint_alerts:
        _build_monthly_endpoint_alerts_slide(prs, endpoint_alerts)

    if cloud_alerts:
        _build_monthly_cloud_alerts_slide(prs, cloud_alerts)

    if cloud_responses and soc_trend:
        _build_quarterly_activity_slide(prs, cloud_responses, soc_trend)
    elif cloud_responses:
        _build_quarterly_cloud_response_activity_slide(prs, cloud_responses)
    elif soc_trend:
        _build_quarterly_soc_activity_slide(prs, soc_trend)

    if show_soc_table:
        soc_rows = _prepare_soc_rows(soc_rows)

        tb.build_table_slides(
            prs,
            SECTION,
            "SOC Escalations Activity",
            soc_rows,
            lm.BLACKPOINT_SOC_COLUMNS,
            live_badge=False,
        )


def _build_monthly_endpoint_alerts_slide(prs, endpoint_alerts: dict):
    """Draw the monthly endpoint alerts line chart on its own slide."""
    slide = sb.new_content_slide(prs, SECTION, "Monthly Endpoint Alerts")
    dates = sorted(endpoint_alerts.keys())
    cb.add_area_line_chart(
        slide,
        "Monthly Endpoint Alerts",
        dates,
        [endpoint_alerts.get(d, 0) for d in dates],
        line_color=cb.CLR_BLUE,
        fill_color="#E0F5EA",
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.4,
    )


def _build_monthly_cloud_alerts_slide(prs, cloud_alerts: dict):
    """Draw the monthly cloud alerts line chart on its own slide."""
    slide = sb.new_content_slide(prs, SECTION, "Monthly Cloud Alerts")
    dates = sorted(cloud_alerts.keys())
    cb.add_area_line_chart(
        slide,
        "Monthly Cloud Alerts",
        dates,
        [cloud_alerts.get(d, 0) for d in dates],
        line_color=cb.CLR_YELLOW,
        fill_color="#FEF9C3",
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.4,
    )


def _build_quarterly_cloud_response_activity_slide(prs, cloud_responses: list):
    """Quarterly Cloud Response Activity chart from Blackpoint JSON."""
    slide = sb.new_content_slide(prs, SECTION, "Quarterly Cloud Response Activity")
    # The cloud_responses list contains a single object with two maps.
    source = cloud_responses[0] if cloud_responses else {}
    responded = source.get("cloud_responses_responded", {}) or {}
    investigated = source.get("cloud_responses_investigated", {}) or {}

    # Keep a lowercase key list for lookups, but present titled labels
    keys_sorted = sorted(set(responded) | set(investigated), key=_month_sort_key)
    labels = [k.title() for k in keys_sorted]
    values_responded = [responded.get(k, 0) for k in keys_sorted]
    values_investigated = [investigated.get(k, 0) for k in keys_sorted]

    cb.add_grouped_bar_chart(
        slide,
        "Quarterly Cloud Response Activity",
        labels,
        {
            "Cloud Responses Investigated": values_investigated,
            "Cloud Responses Responded": values_responded,
        },
        colors=cb.brand_palette(2),
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.4,
        horizontal=False,
        x_axis_title="Month",
        y_axis_title="Number of Responses",
    )


def _build_quarterly_soc_activity_slide(prs, soc_trend: dict):
    """Quarterly SOC Activity chart from Blackpoint JSON."""
    slide = sb.new_content_slide(prs, SECTION, "Quarterly SOC Activity")
    soc_keys = sorted(soc_trend.keys(), key=_month_sort_key)
    labels = [k.title() for k in soc_keys]
    values = [soc_trend.get(k, 0) for k in soc_keys]

    cb.add_column_chart(
        slide,
        "Quarterly SOC Activity",
        labels,
        values,
        colors=cb.brand_palette(len(labels)) if labels else None,
        left_in=lm.CONTENT_LEFT_IN,
        top_in=lm.CHART2_TOP_IN,
        w_in=lm.CONTENT_W_IN,
        h_in=4.4,
        x_axis_title="Month",
        y_axis_title="Number of Activities",
    )


def _build_quarterly_activity_slide(prs, cloud_responses: list, soc_trend: dict):
    """Combined slide showing Quarterly Response Activity and SOC Activity charts."""
    slide = sb.new_content_slide(prs, SECTION, "Quarterly Response & SOC Activity")
    left_in, top_in, w_in, h_in = sb.left_slot()
    right_in, _, right_w, right_h = sb.right_slot()

    source = cloud_responses[0] if cloud_responses else {}
    responded = source.get("cloud_responses_responded", {}) or {}
    investigated = source.get("cloud_responses_investigated", {}) or {}
    # As above, preserve lookup keys but display titled labels
    response_keys = sorted(set(responded) | set(investigated), key=_month_sort_key)
    response_labels = [k.title() for k in response_keys]
    response_values_responded = [responded.get(k, 0) for k in response_keys]
    response_values_investigated = [investigated.get(k, 0) for k in response_keys]

    cb.add_grouped_bar_chart(
        slide,
        "Quarterly Cloud Response Activity",
        response_labels,
        {
            "Cloud Responses Investigated": response_values_investigated,
            "Cloud Responses Responded": response_values_responded,
        },
        colors=cb.brand_palette(2),
        left_in=left_in,
        top_in=top_in,
        w_in=w_in,
        h_in=h_in,
        horizontal=False,
        x_axis_title="Month",
        y_axis_title="Number of Responses",
    )

    soc_keys = sorted(soc_trend.keys(), key=_month_sort_key)
    soc_labels = [k.title() for k in soc_keys]
    soc_values = [soc_trend.get(k, 0) for k in soc_keys]
    cb.add_column_chart(
        slide,
        "Quarterly SOC Activity",
        soc_labels,
        soc_values,
        colors=cb.brand_palette(len(soc_labels)) if soc_labels else None,
        left_in=right_in,
        top_in=top_in,
        w_in=right_w,
        h_in=right_h,
        x_axis_title="Month",
        y_axis_title="Number of Activities",
    )


def _prepare_soc_rows(rows: list) -> list:
    """
    Prepare SOC Escalations Activity rows for presentation.

    This helper:
        • Formats the date.
        • Ensures every expected key exists.
        • Converts None values to empty strings.
    """

    prepared = []

    for row in rows:
        prepared.append({
            "date": _format_date(row.get("date")),
            "ticketId": row.get("ticketid", "") or row.get("ticketId", ""),
            "action": row.get("action", ""),
            "riskScore": row.get("riskscore", "") or row.get("riskScore", ""),
            "target": row.get("target", ""),
            "status": (row.get("status") or "").title(),
            "sourceLocation": row.get("sourcelocation", "") or row.get("sourceLocation", ""),
        })

    return prepared


def _format_date(value: str) -> str:
    """
    Format ISO date into a user-friendly format.

    Example:
        2026-05-27
            ↓
        27 May 2026

    Falls back to the original value if parsing fails.
    """

    if not value:
        return ""

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).strftime("%d %b %Y")
    except Exception:
        return value