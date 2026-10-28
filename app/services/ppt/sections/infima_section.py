"""Infima section — Security Awareness Training & Dark Web Exposure slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.table_builder as tb
import app.services.ppt.layout_manager as lm

SECTION = "Infima"

_CM_TO_IN = 0.3937007874
_CARD_HEIGHT_REDUCTION_IN = 5 * _CM_TO_IN   # shrink cards by 5cm per request


def _phishing_risk(value: float):
    """
    Lower click-rate = better.
    Bands are not specified by the client anywhere in the JSON — these are
    reasonable defaults matching the dashboard's "Low risk" label at 1.23%.
    Adjust if TeamLogic has exact approved cutoffs.
    """
    if value < 3:
        return cb.CLR_GREEN, "Low risk"
    elif value < 8 and value >=3:
        return cb.CLR_YELLOW, "Moderate risk"
    else:
        return cb.CLR_RED, "High risk"


def _training_status(value: float):
    """
    Higher on-track rate = better.
    Bands are not specified by the client anywhere in the JSON — these are
    reasonable defaults matching the dashboard's "Behind schedule" label at 25%.
    Adjust if TeamLogic has exact approved cutoffs.
    """
    if value >= 75 and value <=100 :
        return cb.CLR_GREEN, "On track"
    elif value < 75 and value >= 40 :
        return cb.CLR_YELLOW, "Needs attention"
    else:
        return cb.CLR_RED, "Behind schedule"


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "Security Awareness Training & Dark Web Exposure")

    data   = lm.normalize(data)
    charts = data.get('charts', {})
    tables = data.get('tables', {})

    # ── Slide 1: Phishing Click Rate + Training On-Track Rate cards ────────
    rates         = charts.get('training_rates') or {}
    phishing_rate = float(rates.get('phishing_click_rate_total', 0) or 0)
    training_rate = float(rates.get('training_on_track_rate', 0) or 0)

    def _phishing_fn(s, l, t, w, h):
        color, label = _phishing_risk(phishing_rate)
        pct = min(phishing_rate / 10.0, 1.0)   # scale caps at "10%+"
        card_h = max(2.0, h - _CARD_HEIGHT_REDUCTION_IN)
        cb.add_infima_metric_card(
            s, "Phishing click rate", f"{phishing_rate:g}%", label,
            pct=pct, min_label="0%", max_label="10%+",
            icon_type="envelope", color_hex=color,
            left_in=l, top_in=t, w_in=w, h_in=card_h
        )

    def _training_fn(s, l, t, w, h):
        color, label = _training_status(training_rate)
        pct = min(training_rate / 100.0, 1.0)
        card_h = max(2.0, h - _CARD_HEIGHT_REDUCTION_IN)
        cb.add_infima_metric_card(
            s, "Training on-track rate", f"{training_rate:g}%", label,
            pct=pct, min_label="0%", max_label="100%",
            icon_type="target", color_hex=color,
            left_in=l, top_in=t, w_in=w, h_in=card_h
        )

    sb.build_dynamic_slide(prs, SECTION, "Security Awareness Overview", [
        (lambda: bool(rates), _phishing_fn, "Phishing Click Rate"),
        (lambda: bool(rates), _training_fn, "Training On-Track Rate"),
    ])

    # ── Table: Dark Web Exposures ───────────────────────────────────────────
    darkweb = tables.get('darkweb_exposures') or {}
    records = darkweb.get('records', [])
    is_enabled = darkweb.get('enabled', True)

    if not is_enabled and not records:
        # Only when disabled AND there's genuinely no data to show — the
        # "Disabled" card, matching the dashboard's disabled view exactly:
        # left-aligned title + inline "Disabled" pill + the API's own
        # message text, centered.
        slide = sb.new_content_slide(prs, SECTION, "Dark Web Exposures")
        cb.add_disabled_info_card(
            slide,
            "Dark Web Exposures",
            darkweb.get('message') or "Dark web exposure monitoring is not enabled for this account.",
            left_in=lm.CONTENT_LEFT_IN, top_in=0.55,
            w_in=lm.CONTENT_W_IN, h_in=lm.CONTENT_H_IN - 0.1
        )
    else:
        # records has real data — always show the actual table, even if
        # the enabled flag happens to say False; never hide real data
        # behind the disabled-state placeholder.
        tb.build_table_slides(prs, SECTION, "Dark Web Exposures",
                              rows=records, columns=lm.DARKWEB_EXPOSURE_COLUMNS,
                              live_badge=True)