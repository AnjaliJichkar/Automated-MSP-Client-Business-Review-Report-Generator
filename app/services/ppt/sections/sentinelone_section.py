"""SentinelOne section — EDR / Endpoint Detection & Response slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.layout_manager as lm

SECTION = "SentinelOne"

COLORS_DOMAIN = ['#00A550', '#74C045', '#3CB043', '#72C030', '#8DC63F', '#008C40', '#5CA028']

# Approved PMS green colors
_BLUE   = '#00A550'   # PMS 354  — deep vivid green
_GREEN  = '#74C045'   # PMS 360  — fresh bright green
_YELLOW = '#CCE000'   # PMS 381  — vivid lime
_RED    = '#8DC63F'   # PMS 375  — yellow-green accent
_GRAY   = '#007030'   # PMS 356  — dark green


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "Endpoint Detection & Response")

    data   = lm.normalize(data)
    charts = data.get('charts', {})

    # ── Slide 1: Secured by Domain + Secured by Role ─────────────────────────
    sbd = charts.get('secured_devices_by_domain') or {}
    sbr = charts.get('secured_devices_by_role') or {}

    def _sbd_fn(s, l, t, w, h):
        cb.add_bar_chart(s, "Secured Devices by Domain",
                         labels=list(sbd.keys()), values=list(sbd.values()),
                         colors=COLORS_DOMAIN, x_axis_title="Counts",
                         left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _sbr_fn(s, l, t, w, h):
        cb.add_donut_chart(s, "Secured Devices by Role",
                           labels=[k.title() for k in sbr.keys()],
                           values=list(sbr.values()),
                           colors=[_BLUE, _GREEN, _YELLOW],
                           left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Device Coverage by Domain & Role", [
        (lambda: bool(sbd), _sbd_fn, "Secured Devices by Domain"),
        (lambda: bool(sbr), _sbr_fn, "Secured Devices by Role"),
    ])

    # ── Slide 2: OS Coverage + Endpoint Health + Incident Status (up to 3) ───
    sbo = charts.get('secured_devices_by_os') or {}
    ie  = charts.get('infected_endpoints') or {}
    ins = charts.get('incident_status') or {}

    def _sbo_fn(s, l, t, w, h):
        cb.add_donut_chart(s, "Secured Devices by OS",
                           labels=[k.title() for k in sbo.keys()],
                           values=list(sbo.values()),
                           colors=[_BLUE, _YELLOW, _GREEN],
                           left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _ie_fn(s, l, t, w, h):
        cb.add_donut_chart(s, "Infected Endpoint",
                           labels=[k.replace('_', ' ').title() for k in ie.keys()],
                           values=list(ie.values()),
                           colors=[_GREEN, _RED],
                           left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "OS Coverage, Endpoint Health & Incident Status", [
        (lambda: bool(sbo), _sbo_fn, "Secured Devices by OS"),
        (lambda: bool(ie),  _ie_fn,  "Infected Endpoint"),
        (lambda: bool(ins),
         lambda s, l, t, w, h: cb.add_donut_chart(
             s, "Incident Status",
             labels=[k.replace('_', ' ').title() for k in ins.keys()],
             values=list(ins.values()),
             colors=[_GREEN, _RED, _YELLOW],
             left_in=l, top_in=t, w_in=w, h_in=h),
         "Incident Status"),
    ])

    # ── Slide 3: Severity Levels + Threats by Type ────────────────────────────
    slt = charts.get('severity_levels_threats') or {}
    tbt = charts.get('threats_by_type') or {}

    sb.build_dynamic_slide(prs, SECTION, "Threat Severity & Threats by Type", [
        (lambda: bool(slt),
         lambda s, l, t, w, h: cb.add_column_chart(
             s, "Severity Levels of Threats",
             labels=[k.replace('/', ' / ').title() for k in slt.keys()],
             values=list(slt.values()),
             colors=cb.brand_palette(len(slt)),
             y_axis_title="Counts",
             left_in=l, top_in=t, w_in=w, h_in=h),
         "Severity Levels of Threats"),

        (lambda: bool(tbt),
         lambda s, l, t, w, h: cb.add_column_chart(
             s, "Threats by Type",
             labels=[k.title() for k in tbt.keys()],
             values=list(tbt.values()),
             colors=[_RED, _YELLOW, _BLUE, '#3CB043', _GREEN],
             y_axis_title="Counts",
             left_in=l, top_in=t, w_in=w, h_in=h),
         "Threats by Type"),
    ])
    

    # ── Slide 4: Agent Version + Connection Status ────────────────────────────
    avc = charts.get('agent_version_coverage') or {}
    ecs = charts.get('endpoint_connection_status') or {}
    _ecs_clrs  = [_GREEN, _RED, _YELLOW, _GRAY, '#3CB043', '#5CA028']
    ecs_labels = [k.replace('_', ' ').title() for k in ecs.keys()]
    ecs_values = list(ecs.values())
    ecs_colors = [_ecs_clrs[i % len(_ecs_clrs)] for i in range(len(ecs_labels))]

    def _avc_fn(s, l, t, w, h):
        cb.add_bar_chart(s, "Agent Version Coverage",
                         labels=list(avc.keys()), values=list(avc.values()),
                         single_color=_BLUE,
                         left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _ecs_fn(s, l, t, w, h):
        cb.add_donut_chart(s, "Endpoint Connection Status",
                           labels=ecs_labels, values=ecs_values, colors=ecs_colors,
                           left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Agent Version & Connection Status", [
        (lambda: bool(avc), _avc_fn, "Agent Version Coverage"),
        (lambda: bool(ecs), _ecs_fn, "Endpoint Connection Status"),
    ])

    # ── Slide 5: Analyst Verdicts + Detection Engines ─────────────────────────
    av  = charts.get('analyst_verdicts_threats') or {}
    tde = charts.get('threats_by_detection_engine') or {}

    _av_clrs   = [_GREEN, _RED, _YELLOW, _GRAY]
    av_labels  = [k.replace('_', ' ').title() for k in av.keys()]
    av_values  = list(av.values())
    av_colors  = (_av_clrs * ((len(av_labels) // len(_av_clrs)) + 1))[:len(av_labels)]

    _tde_clrs  = [_BLUE, _GREEN, _YELLOW, '#3CB043', _RED, _GRAY]
    tde_labels = [k.replace('_', ' ').title() for k in tde.keys()]
    tde_values = list(tde.values())
    tde_colors = (_tde_clrs * ((len(tde_labels) // len(_tde_clrs)) + 1))[:len(tde_labels)]

    sb.build_dynamic_slide(prs, SECTION, "Analyst Verdicts & Detection Engines", [
        (lambda: bool(av),
         lambda s, l, t, w, h: cb.add_column_chart(
             s, "Analyst Verdict Threats",
             labels=av_labels, values=av_values, colors=av_colors,
             y_axis_title="Counts",
             left_in=l, top_in=t, w_in=w, h_in=h),
         "Analyst Verdict Threats"),

        (lambda: bool(tde),
         lambda s, l, t, w, h: cb.add_bar_chart(
             s, "Threats by Detection Engine",
             labels=tde_labels, values=tde_values, colors=tde_colors,
             left_in=l, top_in=t, w_in=w, h_in=h),
         "Threats by Detection Engine"),
    ])
