"""
Layout Manager — Universal PPT Report
All visual constants: colors, fonts, dimensions, image paths.
Slide dimensions match the Client Business Review template (10" x 5.625").
"""
import os
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


def normalize(d):
    """
    Recursively lowercase all dict keys so that JSON from the API is
    always accessible via lowercase keys regardless of how the API
    capitalises them (e.g. 'Medium' vs 'medium', 'High' vs 'high').
    List items and scalar values are left untouched.
    """
    if isinstance(d, dict):
        return {k.lower(): normalize(v) for k, v in d.items()}
    if isinstance(d, list):
        return [normalize(i) for i in d]
    return d

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
IMG_FOOTER_BANNER  = os.path.join(_ASSETS_DIR, 'footer_banner.png')
IMG_MSP_AWARD2     = os.path.join(_ASSETS_DIR, 'msp_award2.png')
IMG_TEAMLOGIC_LOGO = os.path.join(_ASSETS_DIR, 'TLIT20.png')

SLIDE_W_IN   = 10.0
SLIDE_H_IN   = 5.625
SLIDE_WIDTH  = Inches(SLIDE_W_IN)
SLIDE_HEIGHT = Inches(SLIDE_H_IN)

HEADER_H_IN     = 0.45
HEADER_BG       = RGBColor(0x2E, 0x6B, 0x4F)   # Dark green
HEADER_TEXT_CLR = RGBColor(0xFF, 0xFF, 0xFF)    # White

FOOTER_TOP_IN    = 5.35
FOOTER_H_IN      = 0.228
FOOTER_LEFT      = Inches(0)
FOOTER_TOP       = Inches(FOOTER_TOP_IN)
FOOTER_WIDTH     = Inches(SLIDE_W_IN)
FOOTER_HEIGHT    = Inches(FOOTER_H_IN)

CONTENT_TOP_IN   = 0.44
CONTENT_LEFT_IN  = 0.2
CONTENT_BOT_IN   = FOOTER_TOP_IN
CONTENT_W_IN     = SLIDE_W_IN - CONTENT_LEFT_IN * 2   # 9.6
CONTENT_H_IN     = CONTENT_BOT_IN - CONTENT_TOP_IN    # 4.91

_GAP_IN         = 0.2
CHART2_W_IN     = (CONTENT_W_IN - _GAP_IN) / 2        # ~4.7
CHART2_H_IN     = 4.55
CHART2_L1_IN    = CONTENT_LEFT_IN
CHART2_L2_IN    = CONTENT_LEFT_IN + CHART2_W_IN + _GAP_IN
CHART2_TOP_IN   = 0.55

CHART1_W_IN     = CONTENT_W_IN
CHART1_H_IN     = 4.55
CHART1_LEFT_IN  = CONTENT_LEFT_IN
CHART1_TOP_IN   = 0.55

FIGSIZE_HALF = (4.7, 4.4)
FIGSIZE_FULL = (9.5, 4.4)


def calc_slots(n: int) -> list:
    """
    Return a list of n (left_in, top_in, w_in, h_in) tuples that evenly
    divide the content area of a slide.

      n=1 → one full-width slot
      n=2 → two equal halves (left / right)
      n=3 → three equal columns
      n=4+ → handled as pairs of rows (future-proof)
    """
    TOP = CHART2_TOP_IN
    H   = CHART2_H_IN
    GAP = 0.2
    L   = CONTENT_LEFT_IN
    TW  = CONTENT_W_IN

    if n <= 0:
        return []
    if n == 1:
        return [(L, TOP, TW, H)]

    w = (TW - GAP * (n - 1)) / n
    return [(L + i * (w + GAP), TOP, w, H) for i in range(n)]

CLR_DARK         = RGBColor(0x37, 0x40, 0x50)   # #374050  — primary dark
CLR_DARK2        = RGBColor(0x1F, 0x29, 0x37)   # #1F2937  — secondary dark
CLR_TEXT         = RGBColor(0x37, 0x3C, 0x3F)   # #373C3F  — body text
CLR_BLUE         = RGBColor(0x61, 0x93, 0xE3)   # #6193E3  — accent blue
CLR_GREEN        = RGBColor(0x69, 0xC7, 0x8C)   # #69C78C  — accent green
CLR_YELLOW       = RGBColor(0xEB, 0xB8, 0x65)   # #EBB865  — accent yellow
CLR_RED          = RGBColor(0xEC, 0x90, 0x90)   # #EC9090  — accent red
CLR_DARK_RED     = RGBColor(0xDB, 0x25, 0x25)   # #DB2525  — error red
CLR_WHITE        = RGBColor(0xFF, 0xFF, 0xFF)
CLR_SLIDE_BG     = RGBColor(0xFF, 0xFF, 0xFF)
CLR_SECTION_BG   = RGBColor(0x2E, 0x6B, 0x4F)   # dark green section divider

FONT_NAME       = "Times New Roman"
FONT_HEADER_PT  = Pt(11)
FONT_TITLE_PT   = Pt(10)
FONT_BODY_PT    = Pt(9)

TBL_HDR_BG      = RGBColor(0xC6, 0xDF, 0xCE)
TBL_HDR_TEXT    = RGBColor(0x1E, 0x3D, 0x2F)
TBL_ROW_ODD     = RGBColor(0xFF, 0xFF, 0xFF)
TBL_ROW_EVEN    = RGBColor(0xE8, 0xF4, 0xEC)
TBL_BODY_TEXT   = RGBColor(0x26, 0x26, 0x26)
TBL_BORDER      = RGBColor(0xA8, 0xCD, 0xB8)
TBL_BAR_BG      = RGBColor(0x2E, 0x6B, 0x4F)

TABLE_LEFT      = Inches(CONTENT_LEFT_IN)
TABLE_TOP       = Inches(0.75)
TABLE_WIDTH     = Inches(CONTENT_W_IN)
ROW_HEIGHT      = Inches(0.44)   # tall enough for 2 wrapped lines at 8pt
HDR_ROW_H       = Inches(0.32)
ROWS_PER_SLIDE  = 10             # updated via dynamic calc in table_builder

COVER_LOGO_LEFT     = Inches(3.25)
COVER_LOGO_TOP      = Inches(0.25)
COVER_LOGO_W        = Inches(3.5)
COVER_LOGO_H        = Inches(0.75)
COVER_FOOTER_LEFT   = Inches(0)
COVER_FOOTER_TOP    = Inches(FOOTER_TOP_IN)
COVER_FOOTER_W      = Inches(SLIDE_W_IN)
COVER_FOOTER_H      = Inches(FOOTER_H_IN)
CLR_COVER_TITLE     = RGBColor(0x1E, 0x3D, 0x2F)
CLR_COVER_SUBTITLE  = RGBColor(0x40, 0x40, 0x40)

WORKSTATION_COLUMNS = [
    ("device",           "Device",               0.09),
    ("lastloggedinuser", "Last Logged In User",   0.11),
    ("manufacturer",     "Manufacturer",          0.09),
    ("model",            "Model",                 0.12),
    ("os",               "OS",                    0.14),
    ("ram",              "RAM",                   0.05),
    ("cpu",              "CPU",                   0.16),
    ("storage",          "Storage",               0.14),
    ("age",              "Age (Yrs)",              0.05),
    ("location",         "Location",              0.05),
]

SERVER_COLUMNS = WORKSTATION_COLUMNS

CVE_EXPLOITED_COLUMNS = [
    ("cve_id",     "CVE ID",       0.15),
    ("title",      "Title",        0.62),
    ("date_added", "Date Added",   0.13),
    ("assets",     "Assets",       0.10),
]

CVE_PRIORITIZED_COLUMNS = [
    ("cve",        "CVE ID",       0.13),
    ("title",      "Title",        0.50),
    ("severity",   "Severity",     0.12),
    ("cvss_score", "CVSS Score",   0.12),
    ("assets",     "Assets",       0.13),
]

BITDEFENDER_MODULE_COLUMNS = [
    ("displayName", "Module",        0.35),
    ("enable",      "Enabled",       0.20),
    ("notenable",   "Not Enabled",   0.20),
]

ASSET_SCORE_COLUMNS = [
    ("asset_name", "Asset Name",  0.28),
    ("total",      "Total",       0.10),
    ("critical",   "Critical",    0.12),
    ("high",       "High",        0.10),
    ("medium",     "Medium",      0.12),
    ("low",        "Low",         0.10),
    ("score",      "Score",       0.10),
]

EPSS_PRIORITIZED_COLUMNS = [
    ("cve",             "CVE ID",          0.40),
    ("assets",          "Assets",          0.25),
    ("epss_percentage", "EPSS %",          0.35),
]

# ──────────────────────────────────────────────────────────────────────────────
# Blackpoint
# ──────────────────────────────────────────────────────────────────────────────

BLACKPOINT_SOC_COLUMNS = [
    ("date",            "Date",             0.09),
    ("ticketId",        "Ticket ID",        0.18),
    ("action",          "Action",           0.24),
    ("riskScore",       "Risk Score",       0.07),
    ("target",          "Target",           0.14),
    ("status",          "Status",           0.08),
    ("sourceLocation",  "Source Location",  0.20),
]
# ──────────────────────────────────────────────────────────────────────────────
# Axcient
# ──────────────────────────────────────────────────────────────────────────────

BACKUP_ALERTS_COLUMNS = [
    ("resource",         "Resource",         0.12),
    ("type",             "Alert Type",       0.22),
    ("count",            "Count",            0.10),
    ("severity",         "Severity",         0.14),
    ("action_required",  "Action Required",  0.42),
]

# ──────────────────────────────────────────────────────────────────────────────
# Infima
# ──────────────────────────────────────────────────────────────────────────────

DARKWEB_EXPOSURE_COLUMNS = [
    ("name",                 "Name",                 0.24),
    ("email",                "Email",                0.38),
    ("resolved_exposures",   "Resolved Exposures",   0.19),
    ("unresolved_exposures", "Unresolved Exposures",  0.19),
]

BACKUP_ALERTS_COLUMNS = [
    ("resource",         "Resource",         0.12),
    ("type",             "Alert Type",       0.22),
    ("count",            "Count",            0.10),
    ("severity",         "Severity",         0.14),
    ("action_required",  "Action Required",  0.42),
]