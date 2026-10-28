"""Cove section — Backup & Cloud Storage slides."""
import app.services.ppt.chart_builder as cb
import app.services.ppt.slide_builder as sb
import app.services.ppt.layout_manager as lm
import app.services.ppt.table_builder as tb

SECTION = "Cove"


def build_slides(prs, data: dict):
    sb.add_section_slide(prs, SECTION, "Backup & Cloud Storage")

    data   = lm.normalize(data)
    charts = data.get('charts', {})

    # ── Slide 1: Devices & Storage Summary + Asset Type Distribution ─────────
    tds = charts.get('total_devices_storage_summary_cove') or {}
    atd = charts.get('asset_type_distribution_cove') or {}

    # Always define device_stats — previously this was only built inside
    # "if tds:", which caused a NameError once render_fn started being
    # called unconditionally (tds.get(...) already defaults to '—' safely,
    # so there's no need to gate this at all).
    used_storage_raw = tds.get('used_storage', '—')
    try:
        used_storage_val = f"{float(used_storage_raw):.2f}TB"
    except Exception:
        used_storage_val = str(used_storage_raw)

    device_stats = [
        ('Total Devices',              tds.get('totaldevices', '—'),
         'monitor',          '#00A550', '#E0F5EA'),
        ('Used Storage',               used_storage_val,
         'storage',          '#74C045', '#F0F8E6'),
        ('Protected User Mailboxes',   tds.get('user_mailboxes', '—'),
         'envelope',         '#3CB043', '#E8F5E8'),
        ('Protected Shared Mailboxes', tds.get('shared_mailboxes', '—'),
         'envelope_shared',  '#007030', '#E0EDE6'),
        ('OneDrive Protected Users',   tds.get('onedrive_user_accounts', '—'),
         'cloud',            '#8DC63F', '#F2F9E4'),
    ]

    def _storage_fn(s, l, t, w, h):
        cb.add_devices_storage_card(s, "Devices & Storage Summary",
                                    stats=device_stats,
                                    left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)


#Asset Type Distribution chart 
    # def _atd_fn(s, l, t, w, h):
    #     # asset_type_distribution_cove always has a fixed 3-key schema
    #     # (physical/virtual/others) — fall back to those names at zero if
    #     # the field is missing entirely, instead of a placeholder box.
    #     _labels = [k.title() for k in atd.keys()] or ['Physical', 'Virtual', 'Others']
    #     _values = list(atd.values()) or [0, 0, 0]
    #     cb.add_donut_chart(s, "Asset Type Distribution",
    #                        labels=_labels,
    #                        values=_values,
    #                        colors=[cb.CLR_BLUE, cb.CLR_GREEN, cb.CLR_YELLOW],
    #                        center_label=f"{sum(_values)}\nTotal Count",
    #                        left_in=l, top_in=t, w_in=w, h_in=h)
    #     cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Devices & Storage Summary", [
        (lambda: bool(tds),  _storage_fn, "Devices & Storage Summary"),
        #(lambda: bool(atd),  _atd_fn,     "Asset Type Distribution"),
    ])

    # ── Slide 2: Devices Distribution + Retention Policy ─────────────────────
    dd  = charts.get('devices_distribution_cove') or {}
    rpd = charts.get('retention_policy_distribution_cove') or {}



#devices_distribution_cove CHART 

    # def _dd_fn(s, l, t, w, h):
    #     # devices_distribution_cove always has a fixed 3-key schema
    #     # (workstations/servers/others) — fall back to those names at zero
    #     # if the field is missing entirely, instead of a placeholder box.
    #     _labels = [k.title() for k in dd.keys()] or ['Workstations', 'Servers', 'Others']
    #     _values = list(dd.values()) or [0, 0, 0]
    #     cb.add_donut_chart(s, "Devices Type Distribution",
    #                        labels=_labels,
    #                        values=_values,
    #                        colors=[cb.CLR_BLUE, cb.CLR_GREEN, cb.CLR_YELLOW],
    #                        center_label=f"{sum(_values)}\nTotal Devices",
    #                        left_in=l, top_in=t, w_in=w, h_in=h)
    #     cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    def _rpd_fn(s, l, t, w, h):
        cb.add_bar_chart(s, "Retention Policy Distribution",
                         labels=list(rpd.keys()), values=list(rpd.values()),
                         single_color=cb.CLR_BLUE,
                         x_axis_title="Number of Policies",
                         left_in=l, top_in=t, w_in=w, h_in=h)
        cb.add_live_badge(s, l + w - 0.65, t + 0.05)

    sb.build_dynamic_slide(prs, SECTION, "Device Distribution & Retention Policy", [
        # (lambda: bool(dd),  _dd_fn,  "Devices Type Distribution"),
        (lambda: bool(rpd), _rpd_fn, "Retention Policy Distribution"),
    ])



# ── Slide(s): Inventory (paginated table) ─────────────────────────────
    inventory_rows = data.get('tables', {}).get('inventory_cove', [])
    tb.build_table_slides(
        prs, SECTION, "Device Inventory Coverage",
        rows=inventory_rows,
        columns=[
            ('device_name',        'Device Name',        0.30),
            ('used_storage',       'Used Storage',        0.16),
            ('os_type',            'OS Type',             0.18),
            ('device_physicality', 'Device Physicality',  0.20),
            ('os_version',         'OS Version',          0.16),
        ],
        live_badge=True,
        empty_message="Data Not Available",
        empty_submessage="No inventory data was returned for this integration."
    )