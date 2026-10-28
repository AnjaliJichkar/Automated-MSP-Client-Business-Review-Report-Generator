"""NodeWare section — CVE Vulnerability Management slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.table_builder as tb
import app.services.ppt.layout_manager as lm

SECTION = "NodeWare"

# CVSS severity levels are a fixed, known taxonomy — used as a fallback so
# the "CVSS Severity Breakdown" donut always has real category labels to
# show, even when cvss_breakdown is empty.
DEFAULT_SEVERITY_LABELS = ["Critical", "High", "Medium", "Low"]


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "CVE Vulnerability Management")

    data   = lm.normalize(data)
    charts = data.get('charts', {})
    tables = data.get('tables', {})

    # ── Slide 1: Vulnerability Summary + CVSS Severity Breakdown (merged) ───
    sm          = charts.get('summary_metrics') or {}
    cvss        = charts.get('cvss_breakdown') or {}
    has_sm      = bool(sm)
    has_cvss    = bool(cvss)

    if cvss:
        cvss_keys   = list(cvss.keys())
        cvss_labels = [k.replace('_', ' ').title() for k in cvss_keys]
        cvss_values = [cvss.get(k, 0) for k in cvss_keys]
    else:
        cvss_labels = list(DEFAULT_SEVERITY_LABELS)
        cvss_values = [0] * len(cvss_labels)
    unique_cves = sum(cvss_values)

    def _merged_fn(s, l, t, w, h):
        if has_sm and has_cvss:
            # Both present — original 58%/42% split, unchanged.
            orig_gauge_w = w * 0.404          # keep gauge at original full-width size
            summary_w    = w * 0.58           # left zone: gauge + compact stat cards
            donut_l      = l + summary_w + 0.15
            donut_w      = w - summary_w - 0.15

            cb.add_nodeware_summary_card(s, sm, left_in=l, top_in=t,
                                         w_in=summary_w, h_in=h,
                                         compact_cards=True,
                                         gauge_w_override=orig_gauge_w)
            cb.add_live_badge(s, l + orig_gauge_w - 0.65, t + 0.05)
            cb.add_donut_chart(s, "CVSS Severity Breakdown",
                               labels=cvss_labels, values=cvss_values,
                               center_label=f"Unique CVEs\n{unique_cves}",
                               center_value_size=20, center_value_bold=True,
                               center_value_color='#000000',
                               left_in=donut_l, top_in=t, w_in=donut_w, h_in=h)
            cb.add_live_badge(s, l + w - 0.65, t + 0.05)
        elif has_sm:
            # Only the summary gauge is active — full width, no donut.
            orig_gauge_w = w * 0.404
            cb.add_nodeware_summary_card(s, sm, left_in=l, top_in=t,
                                         w_in=w, h_in=h,
                                         compact_cards=True,
                                         gauge_w_override=orig_gauge_w)
            cb.add_live_badge(s, l + orig_gauge_w - 0.65, t + 0.05)
        else:
            # Only the CVSS donut is active — full width, no gauge.
            cb.add_donut_chart(s, "CVSS Severity Breakdown",
                               labels=cvss_labels, values=cvss_values,
                               center_label=f"Unique CVEs\n{unique_cves}",
                               center_value_size=20, center_value_bold=True,
                               center_value_color='#000000',
                               left_in=l, top_in=t, w_in=w, h_in=h)
            cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Vulnerability Summary &  CVSS Severity Breakdown", [
        (lambda: has_sm or has_cvss, _merged_fn, "Vulnerability Summary"),
    ])

    # ── Tables ────────────────────────────────────────────────────────────────
    kev_rows = tables.get('known_exploited_cves', [])
    tb.build_table_slides(prs, SECTION, "Known Exploited Vulnerabilities",
                          rows=kev_rows, columns=lm.CVE_EXPLOITED_COLUMNS,
                          empty_message="No Exploited Vulnerabilities Found",
                          empty_submessage="")

    pri_rows = tables.get('cvss_prioritized', [])
    tb.build_table_slides(prs, SECTION, "CVSS Prioritized CVEs",
                          rows=pri_rows, columns=lm.CVE_PRIORITIZED_COLUMNS,
                          live_badge=True)

    ars_rows = tables.get('asset_risk_score', [])
    tb.build_table_slides(prs, SECTION, "Assets Score Distribution",
                          rows=ars_rows, columns=lm.ASSET_SCORE_COLUMNS,
                          live_badge=True)

    epss_rows = tables.get('epss_prioritized', [])
    tb.build_table_slides(prs, SECTION, "EPSS Prioritized",
                          rows=epss_rows, columns=lm.EPSS_PRIORITIZED_COLUMNS,
                          live_badge=True)