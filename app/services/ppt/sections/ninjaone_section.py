"""NinjaOne section — Patch Management + Device Inventory slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.table_builder as tb
import app.services.ppt.layout_manager as lm

SECTION = "NinjaOne"


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "Patch Management & Device Inventory")

    data   = lm.normalize(data)
    charts = data.get('charts', {})
    tables = data.get('tables', {})

    # ── Slide 1: Patch Management Enablement + Patch Status Distribution ──────
    pme = charts.get('patch_management_enablement') or {}
    psd = charts.get('patch_status_distribution') or {}

    # These two fields have a fixed, known schema (enabled/disabled and
    # installed/approved/failed/pending) - fall back to those names at
    # zero if the fields are missing entirely, instead of a placeholder box.
    if pme:
        _pme_labels = [k.replace('_', ' ').title() for k in pme.keys()]
        _pme_values = list(pme.values())
    else:
        _pme_labels = ['Enabled', 'Disabled']
        _pme_values = [0, 0]
    _pme_total   = sum(_pme_values)
    _pme_colors  = cb.brand_palette(len(_pme_labels))

    if psd:
        _psd_keys    = list(psd.keys())
        _psd_labels  = [k.replace('_', ' ').title() for k in _psd_keys]
        _psd_values  = [psd.get(k, 0) for k in _psd_keys]
    else:
        _psd_labels = ['Installed', 'Approved', 'Failed', 'Pending']
        _psd_values = [0, 0, 0, 0]
    _psd_colors  = cb.brand_palette(len(_psd_labels))

    def _pme_fn(s, l, t, w, h):
        cb.add_donut_chart(s, "Patch Management Enablement",
                           labels=_pme_labels, values=_pme_values, colors=_pme_colors,
                           center_label=f"{_pme_total}\nTotal Devices",
                           left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _psd_fn(s, l, t, w, h):
        cb.add_column_chart(s, "Patch Status & Compliance",
                            labels=_psd_labels, values=_psd_values, colors=_psd_colors,
                            y_axis_title="Counts",
                            left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Patch Management Overview", [
        (lambda: bool(pme),                       _pme_fn, "Patch Management Enablement"),
        (lambda: bool(psd) and any(_psd_values),  _psd_fn, "Patch Status & Compliance"),
    ])

    # ── Slide 2: All Devices With Failed Patches ──────────────────────────────
    pm      = charts.get('patch_management') or {}
    os_raw  = pm.get('os_patches') or {}
    tp_raw  = pm.get('third_party_patches') or {}

    dwfp    = charts.get('devices_with_failed_patches') or {}
    devices = dwfp.get('devices', [])
    top_dev = devices[0].get('device', 'No failed devices') if devices else 'No failed devices'

    sb.build_dynamic_slide(prs, SECTION, "Status Of Patches Deployed", [
        (lambda: bool(os_raw) or bool(tp_raw),
         lambda s, l, t, w, h: cb.add_patch_summary(
             s, "Status of patches deployed", os_raw, tp_raw,
             left_in=l, top_in=t, w_in=w, h_in=h),
         "Status of patches deployed"),
    ])

    # ── Tables ────────────────────────────────────────────────────────────────
    def _compute_storage(row):
        total = row.get('total_storage', '') or ''
        free  = row.get('free_storage',  '') or ''
        if not total and not free:
            return ''
        try:
            total_gb = float(str(total).replace('GB', '').strip())
            free_gb  = float(str(free).replace('GB', '').strip())
            pct = (free_gb / total_gb * 100) if total_gb else 0
            return f"{free_gb:.1f}GB / {total_gb:.1f}GB\n{pct:.1f}% free"
        except Exception:
            return f"{free} / {total}"

    ws_rows = tables.get('device_inventory', [])
    for row in ws_rows:
        row['storage'] = _compute_storage(row)
    tb.build_table_slides(prs, SECTION, "Asset Lifecycle Details",
                          ws_rows, lm.WORKSTATION_COLUMNS, live_badge=True)

    srv_rows = tables.get('device_inventory_server', [])
    if srv_rows:
        for row in srv_rows:
            row['storage'] = _compute_storage(row)
        tb.build_table_slides(prs, SECTION, "Server Lifecycle Details",
                              srv_rows, lm.SERVER_COLUMNS, live_badge=True)