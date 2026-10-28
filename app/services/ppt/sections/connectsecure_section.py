"""ConnectSecure section — Vulnerability & Asset Management slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.layout_manager as lm

SECTION = "ConnectSecure"

# Fixed vulnerability-severity taxonomy — used as a fallback so the
# "Vulnerability Severity" chart always has real category labels to show,
# even when live_count is empty. Severity levels are a known, fixed set
# independent of the data (same reasoning as ticket priority in Autotask).
DEFAULT_SEVERITY_LABELS = ["Critical", "High", "Medium", "Low"]

# Severity colours: medium → bright → deep → dark (Low → Critical)
_SEV_COLORS = ['#8DC63F', '#74C045', '#00A550', '#007030']

# OS Distribution colours: approved PMS greens cycling
_OS_COLORS = ['#00A550', '#74C045', '#3CB043', '#008C40', '#72C030']

# Asset Type Distribution: light-green → deep forest (light → dark)
_ASSET_GREEN_ANCHORS = ['#ADDA5E', '#74C045', '#3CB043', '#00A550', '#007030']

def _green_shades(n: int) -> list:
    """Return n hex colors: light-green (#ADDA5E) → dark green (#007030)."""
    if n <= 0:
        return []
    anchors = _ASSET_GREEN_ANCHORS
    if n <= len(anchors):
        return anchors[:n]
    r1, g1, b1 = 0xAD, 0xDA, 0x5E   # #ADDA5E — PMS 367
    r2, g2, b2 = 0x00, 0x70, 0x30   # #007030 — PMS 356
    result = []
    for i in range(n):
        t = i / (n - 1)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        result.append(f'#{r:02X}{g:02X}{b:02X}')
    return result


def _risk_label(score: float) -> str:
    """Compute risk level + message from score (0–100 scale)."""
    if score >= 80:
        return 'High Risk\nImmediate attention required'
    if score >= 50:
        return 'Medium Risk\nNeeds improvement'
    return 'Low Risk\nGood security posture'


def build_slides(prs, data: dict):
    """
    Builds ConnectSecure slides:
      Slide 1: Security Risk Score | Asset Type Distribution | Agent Type Distribution
      Slide 2: Vulnerability Severity (column) | OS Distribution (donut)

    Data source:
      All three dynamic charts (Security Risk Score, Asset Type Distribution,
      Operating System Distribution) always read live_count, regardless of
      reporting_period — monthly_count/quarterly_count are not used to pick
      the displayed data (quarterly_count is still passed to the risk-score
      card as a secondary reference value, not as the primary score source).
    """
    sb.add_section_slide(prs, SECTION, "Vulnerability & Asset Management")

    charts = data.get('charts', {})

    # ── Slide 1: Security Risk Score + Asset Type Distribution + Agent Type Distribution ──
    srs       = charts.get('security_risk_score') or {}
    atd       = charts.get('asset_type_distribution') or {}
    atd_data  = atd.get('live_count') or {}
    agent     = charts.get('agent_type_distribution') or {}
    breakdown = agent.get('breakdown', [])

    has_srs   = bool(srs)
    has_atd   = bool(atd_data)
    has_agent = bool(breakdown)

    chart_specs = []
    if has_srs:
        def _render_srs(slide, left, top, width, height):
            score_raw = srs.get('live_count')
            score_val = float(score_raw or 0)
            cb.add_security_risk_score(
                slide, "Security Risk Score",
                score=score_val,
                impact_label=_risk_label(score_val),
                monthly=srs.get('monthly_count'),
                quarterly=srs.get('quarterly_count'),
                left_in=left, top_in=top, w_in=width, h_in=height
            )
        chart_specs.append((lambda: True, _render_srs, "Security Risk Score"))

    if has_atd:
        def _render_atd(slide, left, top, width, height):
            _atd_colors = _green_shades(len(atd_data))
            _atd_total  = sum(atd_data.values())
            cb.add_donut_chart(
                slide, "Asset Type Distribution",
                labels=[k.replace('_', ' ').title() for k in atd_data.keys()],
                values=list(atd_data.values()),
                colors=_atd_colors,
                center_label=f"{_atd_total}\nTotal Assets Type",
                left_in=left, top_in=top, w_in=width, h_in=height
            )
            cb.add_live_badge(slide, left + width - 0.65, top + 0.05)
        chart_specs.append((lambda: True, _render_atd, "Asset Type Distribution"))

    if has_agent:
        def _render_agent(slide, left, top, width, height):
            a_labels = [b.get('agent_type', '') for b in breakdown]
            a_values = [b.get('count', 0) for b in breakdown]
            _total_agents = agent.get('total_agents', '')
            cb.add_donut_chart(
                slide, "Agent Type Distribution",
                labels=a_labels, values=a_values,
                center_label=f"{_total_agents}\nTotal Agents Type",
                left_in=left, top_in=top, w_in=width, h_in=height
            )
            cb.add_live_badge(slide, left + width - 0.65, top + 0.05)
        chart_specs.append((lambda: True, _render_agent, "Agent Type Distribution"))

    # ── Slide 2: Vulnerability Severity + OS Distribution ────────────────────
    vs      = charts.get('vulnerability_severity') or {}
    vs_live = vs.get('live_count') or {}
    has_vs  = bool(vs_live)

    osd     = charts.get('operating_system_distribution') or {}
    os_data = osd.get('live_count') or {}
    has_os  = bool(os_data)

    if has_vs:
        def _render_vs(slide, left, top, width, height):
            sev_keys = list(vs_live.keys())
            sev_labels = [k.replace('_', ' ').title() for k in sev_keys]
            sev_values = [vs_live.get(k, 0) for k in sev_keys]
            _sev_total = sum(sev_values)
            cb.add_grouped_bar_chart(
                slide, "Vulnerability Severity",
                categories=sev_labels,
                series_data={'Live': sev_values},
                per_category_colors=_SEV_COLORS,
                horizontal=False,
                corner_label=f"Total Severity - {_sev_total}",
                left_in=left, top_in=top, w_in=width, h_in=height
            )
            cb.add_live_badge(slide, left + width - 0.65, top + 0.06)
        chart_specs.append((lambda: True, _render_vs, "Vulnerability Severity"))

    if has_os:
        def _render_os(slide, left, top, width, height):
            _os_colors = (_OS_COLORS * ((len(os_data) // len(_OS_COLORS)) + 1))[:len(os_data)]
            cb.add_column_chart(
                slide, "OS Distribution",
                labels=list(os_data.keys()),
                values=list(os_data.values()),
                colors=_os_colors,
                y_axis_title="Number of Assets",
                left_in=left, top_in=top, w_in=width, h_in=height
            )
            cb.add_live_badge(slide, left + width - 0.65, top + 0.05)
        chart_specs.append((lambda: True, _render_os, "OS Distribution"))

    # Fill the first slide before starting the second one, so hidden charts do
    # not leave an unused slot between the remaining charts.
    sb.build_dynamic_slide(
        prs, SECTION, "Risk Score & Asset & Agent Distribution", chart_specs[:3]
    )
    sb.build_dynamic_slide(
        prs, SECTION, "Vulnerabilities & OS Distribution", chart_specs[3:]
    )