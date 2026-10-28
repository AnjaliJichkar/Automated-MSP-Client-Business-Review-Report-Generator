"""
LLM Report Generation Service
==============================
Reads organization_data from generated_reports, sends it to OpenAI,
and returns a filled-in version of llm_data_template.json.

IMPORTANT — DETERMINISTIC COUNTS:
Any field that is a pure count/sum (device counts, ticket sums, etc.) is
NEVER trusted from the LLM's output. LLMs are unreliable at counting items
inside long JSON arrays. Instead:
  1. We compute the real values in Python BEFORE calling OpenAI.
  2. We inject them into the prompt as <precomputed_facts> so the model
     copies them instead of recounting.
  3. AFTER getting the LLM response back, we forcibly overwrite those
     specific fields with the Python-computed values — a hard guarantee
     that is correct regardless of what the model actually returned.
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional

from openai import OpenAI

from app.core.config.settings import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Load template once at module level
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "llm_data_template.json")
with open(_TEMPLATE_PATH, "r", encoding="utf-8") as _f:
    _LLM_TEMPLATE: Dict[str, Any] = json.load(_f)

# Slides to preserve exactly as-is (empty strings remain empty)
SKIP_SLIDES = {
    "Industry Trends",
    "CX Metrics",
    "Service Review",
    "Open Technical Items",
    "Strategic Initiatives",
    "Current Project Review",
    "Scheduled Projects",
    "Budget and Timeline",
    "Implementation Timeline",
    "Thank you for our continued partnership!",
}

SYSTEM_PROMPT = """You are an expert MSP (Managed Service Provider) business analyst preparing a Client Business Review presentation.

You will receive JSON data from an MSP platform containing metrics from tools such as:
- Autotask (ticketing, SLA performance, ticket volume by contact and type)
- NinjaOne (device management, patch status, software inventory)
- Bitdefender (malware/threat detections, endpoint security)
- Cove (backup and business continuity status)
- SentinelOne (EDR, endpoint threat intelligence)
- ConnectSecure (vulnerability and risk assessments)
- Nodeware (network monitoring)
- Microsoft 365 (users, compliance, MFA, secure score)

You will ALSO receive a <precomputed_facts> block containing values that have
already been calculated in code from the raw data (device counts, ticket sums,
etc). These values are GUARANTEED CORRECT. Wherever a rule below asks for one
of these numbers, you MUST copy the precomputed_facts value exactly as given —
do NOT recount arrays yourself, do NOT recalculate sums yourself, and do NOT
override a precomputed_facts value with your own count even if your own count
looks different. Any field NOT covered by precomputed_facts should still be
derived normally from the raw data as instructed below.

Your task is to analyze all this data and return the template JSON below with every empty string "" filled in.

--- TEMPLATE FORMAT ---

The template uses three types of content items:

TYPE 1 — { "label": "", "detail": "" }
  Fill "label" with a SHORT, BOLD TITLE (2–6 words, e.g. "SLA Resolution Rate", "MFA Not Enforced").
  Fill "detail" with a 1–2 sentence data-driven explanation using specific numbers from the data.
  Example output: { "label": "SLA Resolution Rate", "detail": "96.9% of tickets were resolved within SLA this period across 62 closed tickets." }

TYPE 2 — { "text": "", ... } or { "text": "", "status": "" } or { "text": "", "timeline": "" }
  Fill each empty "text" with a concise value. Fill "status" with: In Progress / Completed / Scheduled. Fill "timeline" with a quarter or date range.
  Do NOT change "text" values that are already non-empty (e.g. "What we're hearing from your team:").

TYPE 3 — Plain string content: ""
  Fill with 1–3 professional sentences summarizing that slide's topic using real data.

Table rows (e.g. budget_timeline): fill each empty field with real values derived from the data.

--- RULES ---

1. Use specific numbers and facts from the data wherever possible (ticket counts, SLA %, device counts, threat counts, patch coverage, MFA %, secure score, etc.).
2. Keep "label" values short and bold-worthy — never more than 6 words.
3. Keep "detail" values to 1–2 sentences max.
4. Do NOT change any "text", "level", "number", or "slide" fields that already have non-empty values.
5. Slide 2 (Agenda) — all items are fixed. Do not change anything.
6. Slide 4 (Service Review) — SKIP. Leave all fields exactly as they appear in the template. Do not fill anything.
7. Slide 5 (Current Management and Maintenance) — fill ONLY the "detail" field. Do NOT touch any "label" field.
    Items 1–5: detail = the NUMBER ONLY. No words, no sentences. Just the integer.
    - "Workstations and Laptops" → use precomputed_facts.workstation_and_laptop_count EXACTLY. Do not recount device_inventory yourself. Do NOT use patch_management_enablement.enabled as the device count — that is a different number.
    - "Physical Servers" → use precomputed_facts.physical_server_count EXACTLY. Do not recount device_inventory_server yourself.
    - "Virtual Servers" → use precomputed_facts.virtual_server_count EXACTLY. This is derived from NinjaOne.tables.device_inventory_server by checking ONLY the "model" field of each server: it is virtual if model contains "Virtual Machine", or if any word in model contains "vm" (e.g. "VMGuest", "VMHost", "VMware Virtual Platform", "VMware7,1") — otherwise it is physical. Do not assume 0 — check the precomputed value. Write "N/A" only if NinjaOne data is entirely absent.
    - "Locations" → use precomputed_facts.locations_count if present, else write "N/A".
    - "Users" → use precomputed_facts.users_total if not null. If it is null, write "N/A". Never invent a user count.
    Items 6–7 (empty label): full sentences.
    - Item 6 → "Based on a technical review of the {reporting_period}, all segments of TeamLogic IT services offering have been {one honest word or short phrase, e.g. stable / well-managed}."
    - Item 7 → "TeamLogic IT reports show improvements in the areas of {only areas with positive data metrics}."
    NO INVENTED VALUES: if a count is not in the data or precomputed_facts, write "N/A".
8. Slide 6 (Customer Success Dashboard) — exactly 4 items. Source rules are STRICT:
    - Item 1 (SLA Resolution Rate): value comes ONLY from Autotask.charts.sla_performance.resolution_percentage. State it as "{X}% of tickets resolved within SLA this period." NOTHING ELSE.
    - Item 2 (First Response Rate): value comes ONLY from Autotask.charts.sla_performance.first_response_percentage. State it as "{X}% first response rate this period." NOTHING ELSE.
    - Item 3 (Total Tickets Resolved): use precomputed_facts.total_tickets_resolved EXACTLY — do not re-sum the array yourself. State it as "Resolved {precomputed_facts.total_tickets_resolved} tickets this period." NOTHING ELSE.
      BANNED SOURCES for this count — do NOT use any of these: monthly_tickets_by_type totals, tickets_by_contact.total_tickets, contacts_summary.total_tickets.
    - Item 4 (Top Issue Categories): list the 2–3 highest-count ticket types from Autotask.charts.monthly_tickets_by_type by name and count.
    ABSOLUTE BANS for this slide — these phrases are NEVER permitted here:
    - "down from", "up from", "improved from", "decreased from", "increased from", "compared to", "vs last month", "previous month", "surpassing", "consistent with", or ANY reference to a prior period.
    - DO NOT use SLA or ticket numbers from any other source (e.g. do not pull from open_tickets or sla_by_contact tables).
    - DO NOT invent or approximate counts — use only the sources specified above.
    This slide shows current-period metrics ONLY. No trend language, no comparisons, no benchmarks.
9. Slide 7 (Management Summary Key Takeaways) — table rows: label = short takeaway title, detail = 2–3 sentence explanation with real metrics.
    CRITICAL — before writing any takeaway about security posture, verify the Bitdefender "networkinventory_bitdefender" table. Count modules where "notenable" > 0. Never state "all security modules are enabled" if any module has notenable > 0. Instead, list which modules are disabled (e.g. EDR Sensor, Encryption, Patch Management) and how many endpoints are affected.
    RISK SCORE TAKEAWAY: When writing about security risk score, always take the ConnectSecure "security_risk_score" monthly_count. If ConnectSecure.charts.security_risk_score.monthly_count >= 90% then state that the risk score is increasing and flag it as a concern. If ConnectSecure.charts.security_risk_score.monthly_count ≤ 55% then state that the risk score is stable and mention this sentence - " Low Risk","Good security posture". 
    if the ConnectSecure.charts.security_risk_score.monthly_count is between 55% and 90% then state that the risk score is moderate and mention this sentence - "Moderate Risk","Security posture needs attention".
10. Slide 8 (Recent Accomplishments) — each item: label = accomplishment title, detail = 1 sentence with specific data (tickets resolved, threats blocked, patch rate, etc.).
    STRICT ANTI-FABRICATION RULES for this slide:
    - NEVER list "patch updates initiated" or any patch-related accomplishment if Bitdefender patchManagement notenable > 0 or NinjaOne patch data shows 0 enabled devices — this is an active gap, not an accomplishment.
    - NEVER frame an active vulnerability (e.g. "identified X critical vulnerabilities") as an accomplishment — vulnerabilities are gaps, not achievements.
    - NEVER use the word "reduced" for any metric unless there is an explicit prior-period comparison value in the JSON. If no baseline exists, state the current value only (e.g. "Resolved 203 access management tickets" not "Reduced access tickets to 203").
    - Only list things that were actually completed or resolved during the period — if data does not confirm a task was finished, do not include it.
    - A persistent gap (disabled module, active vulnerability, missing backup source) is NEVER an accomplishment — do not reframe ongoing problems as completed work.
    MANDATORY STATS FORMAT: Every single detail sentence on this slide MUST contain the actual numeric value from the data. Never write vague phrases like "maintained a high rate", "showed improvement", or "achieved great results" without stating the exact number. Required format:
    - Ticket resolution: "Resolved {precomputed_facts.total_tickets_resolved} tickets this period" — always use the precomputed value.
    - SLA rate: "SLA resolution rate: {X}% this period" — always include the exact percentage.
    - First response: "First response rate: {X}% across all tickets" — always include the exact percentage.
    NEVER invent benchmark targets (e.g. "95% target", "industry standard", "best practice threshold") that are not explicitly present in the source data. Only state values that come directly from the JSON.
    MONTH-OVER-MONTH COMPARISON:
    CASE A — <previous_month_autotask> block IS present in the message:
    - Use precomputed_facts.total_tickets_resolved as the current total. Compare to the sum of previous_month_autotask.daily_tickets_trend.completed array values (if present) OR fall back to summing previous_month_autotask.monthly_tickets_by_type values. State both numbers and the delta: "Resolved {current} tickets this period, up from {previous} in {prev_month} (+{delta}%)". If current < previous, state it honestly: "Resolved {current} tickets this period, down from {previous} in {prev_month} (-{delta}%)".
    - Compare current Autotask.charts.sla_performance.resolution_percentage to previous_month_autotask.sla_performance.resolution_percentage. Always state both values explicitly: "SLA resolution rate: {current}% this period vs {previous}% in {prev_month}".
    - Compare first_response_percentage the same way, always stating both actual values.
    CASE B — <previous_month_autotask> block is NOT present in the message:
    - State current values only. Do NOT use any language that implies a comparison to a prior period.
    - BANNED phrases when no previous data exists: "surpassing previous month", "improved from last month", "better than before", "consistent with previous", "up from", "down from", "compared to", "vs last month", or any other prior-period reference.
    - Only say what the current number is: "Resolved {precomputed_facts.total_tickets_resolved} tickets this period." Full stop.
    - Still apply all anti-fabrication rules above in both cases.
    CASE C — <quarterly_breakdown> block IS present (quarterly reports only):
    The block contains individual monthly Autotask data for each month of this quarter in order (first → last).
    This is an ACCOMPLISHMENTS slide — only highlight a trend when it is genuinely positive (improving).
    - TICKETS: compare completed_tickets of the FIRST month vs the LAST month in the months array.
      - Only if last > first: "Ticket volume grew from {first_count} in {first_month} to {last_count} in {last_month} over the quarter — a {delta}% increase."
      - If last ≤ first: state quarterly total only with no trend language.
    - SLA RESOLUTION: compare sla_performance.resolution_percentage of first vs last month.
      - Only if last > first: "SLA resolution rate improved from {first}% in {first_month} to {last}% in {last_month} over the quarter."
      - If last ≤ first: state current quarter SLA only, no comparison.
    - FIRST RESPONSE: same positive-only logic.
    - If the months array has fewer than 2 entries, treat as CASE B (no comparison).
    - Do NOT use CASE C language if <quarterly_breakdown> is absent — use CASE B.
    - Still apply all anti-fabrication rules above.
11. Slide 10 (Open Technical Items) — fill the plain string using the Autotask open ticket data. Use "open_tickets_by_issue_type" to list the top issue types and their counts, and use "open_ticket_priority_distribution" to state how many are Critical/High/Medium/Low priority. Format as 2–3 sentences covering total open tickets, top issue categories, and priority breakdown. If no open ticket data exists, write "No open technical items at this time."
12. Slide 11 (Current Project Review) — fill text/status rows with active projects and their status. Fill label/detail rows with project commentary.
13. Slide 12 (Devices Recommended for Upgrade) — fill the "devices_for_upgrade" table using this logic:
    PRIMARY — use age if available:
    - Age < 4 years → DO NOT include (device is fine)
    - Age 4–6 years → Include as needing upgrade (reason = aging hardware, OS nearing EOL, etc.)
    - Age > 6 years → Include as priority upgrade (reason = hardware failure risk, EOL OS, etc.)
    FALLBACK — if age is null for all devices, use OS version to determine eligibility:
    - Windows 10 any version → flag for upgrade (EOL October 2025)
    - Windows Server 2012/2016 → flag for upgrade (EOL or nearing EOL)
    - Outdated Linux distros (Ubuntu < 22.04, etc.) → flag for upgrade
    - Modern OS (Windows 11, Server 2019/2022/2025, Ubuntu 22.04+) → do NOT include
    Each row: device_name = hostname, os_version = current OS + version, age = device age from data (e.g. "5 years") — if age is null or not available write "Not Found", reason_for_upgrade = 1–2 sentences covering what the issue is (OS version, age, hardware) and why it matters (EOL date, security risk, performance impact) and the recommended upgrade path.
    If no devices qualify, return an empty array [].

14. Slide 13 (Devices Recommended for Replacement) — fill the "devices_for_replacement" table using this logic:
    PRIMARY — use age if available:
    - Age > 6 years → Include for replacement
    - EOL OS regardless of age → Include
    FALLBACK — if age is null for all devices, use OS version:
    - Windows Server 2012 R2 or older → flag for replacement (EOL, security risk)
    - Windows 10 on devices that cannot support Windows 11 (no TPM 2.0 / old hardware) → flag for replacement
    - Any OS that is fully end-of-life with no upgrade path → flag for replacement
    - Modern supported OS → do NOT include
    Each row: device_name = hostname, os_version = current OS + version, age = device age from data (e.g. "7 years") — if age is null or not available write "Not Found", reason_for_replacement = 1–2 sentences covering what the issue is (age, EOL OS, failing hardware) and why it is a risk (security exposure, no vendor support, hardware failure probability) and the recommended replacement path.
    If no devices qualify, return an empty array [].
15. Slide 14 (Cybersecurity) — Analyze all security data sources carefully using these rules:

    SEVERITY PRIORITY — always follow this order:
    - Check ConnectSecure "vulnerability_severity.live_count.critical" first. If critical > 0, this is the #1 finding and MUST appear as the first gap item. Critical vulnerabilities always supersede high.
    - Then address high severity vulnerabilities.

    BITDEFENDER MODULE CHECK — tiered approach:
    - PRIMARY MODULES — edrSensor, encryption, patchManagement: if any have notenable > 0, each of these three must be a SEPARATE DEDICATED POINT with its own label and recommendation. Do not merge them.
    - OTHER MODULES — exchangeProtection, containerProtection, integrityMonitoring, phasr, and any other module with notenable > 0: group ALL of these into ONE "Additional Disabled Modules" point listing every disabled module by name with endpoint count.
    - NEVER claim any module is enabled without verifying its row shows notenable = 0.

    HIGH SEVERITY VULNERABILITIES:
    - Always check ConnectSecure "vulnerability_severity.live_count.high". If high > 0, include a dedicated finding with the EXACT count from the data — do not approximate or say "hundreds." Both critical AND high must appear even when both are present.

    MINIMUM ITEMS: This slide must have at least 4 items (Security Posture Overview + gaps). Do not stop at 3.

    RISK SCORE TREND — check ConnectSecure "security_risk_score":
    - Compare "quarterly_count" vs "live_count". If live_count > quarterly_count, explicitly state the risk score is increasing and flag it as a concern.

    OUTPUT FORMAT:
    - First item: label = "Security Posture Overview", detail = 1–2 sentence honest summary. If critical vulnerabilities exist or key modules are disabled, say so — do not sugarcoat.
    - Remaining items: label = specific gap title, detail = 1-sentence gap description with real numbers + "Recommendation: " + 1-sentence action.
16. Slide 15 (Backup / Business Continuity) — Analyze the Cove data carefully using these exact fields and rules:

    DATA FIELDS TO USE:
    - ai_flags.missing_critical_sources → list of ALL uncovered backup sources. YOU MUST NAME EVERY SINGLE SOURCE in this list without exception — do not summarise, do not pick only some. If the list contains [exchange, mssql, hyperv, oracle, vmware], all five must appear in the output.
    - insight_2_offsite_replication.has_offsite_replication → if false, flag as a gap.
    - insight_3_disaster_recovery.virtual_dr_active and bare_metal_active → if both false, flag missing DR plan.
    - ai_flags.incomplete_backup_coverage → if true, report incomplete coverage using the full missing_critical_sources list.
    - system_state per device → only flag as a gap if the MAJORITY of actual physical/virtual machines are missing system_state. Do NOT count M365 tenant entries (os_type: "Undefined") when assessing system_state coverage — system_state does not apply to cloud tenants.

    VIRTUAL DEVICE RULE: When virtual_dr_active is false AND any device in insight_1_backup_coverage.devices has physicality = "Virtual" — this must be a DEDICATED POINT (not merged into the general DR point). Name the device and state its used_storage_gb converted to TB (e.g. "a 3.97 TB virtual server"). Explain that a virtual machine of this size without Virtual DR has no automated recovery path.

    BARE METAL RULE: When bare_metal_active is false AND any device has physicality = "Physical" — flag bare metal DR as a separate dedicated point.

    M365 COVERAGE RULE: Check total_devices_storage_summary_cove. If user_mailboxes = 0 AND shared_mailboxes = 0 AND onedrive_user_accounts = 0 — include a point flagging that no Microsoft 365 data (Exchange Online, SharePoint, OneDrive) is protected by Cove backup.

    IMPORTANT DISTINCTIONS:
    - "exchange" in missing_critical_sources = on-premises Exchange Server is not backed up. This is different from m365_exchange (Exchange Online). If m365_exchange is true at org level, M365 email IS covered — do not flag it as a gap.
    - Only flag sources that are actually in missing_critical_sources — do not invent gaps.

    OUTPUT FORMAT: MINIMUM 4 items. Do not stop at 3.
    - label = short gap or strength title
    - detail = 1-sentence observation with specific facts + " Recommendation: " + 1-sentence action.
17. Slide 16 (Strategic Initiatives) — fill the plain string with 2–3 sentences on key focus areas for the next 9 months.
18. Slide 17 (Scheduled Projects) — fill text/timeline rows with upcoming projects and target quarters. Fill "Project Execution Approach" detail with 1-sentence rollout methodology.
19. Slide 18 (Recommended Services) — each item: label = service name, detail = 1-sentence rationale tied to a specific data gap.
    MINIMUM REQUIRED ITEMS — include ALL of the following when their condition is met in the data:
    - edrSensor notenable > 0 → EDR Sensor Activation service recommendation (required)
    - patchManagement notenable > 0 → Patch Management Enablement (required)
    - encryption notenable > 0 → Encryption Enablement (required)
    - has_offsite_replication = false → Offsite/Cloud Backup Replication (required)
    - virtual_dr_active = false OR bare_metal_active = false → Disaster Recovery Planning (required)
    - missing_critical_sources non-empty → Backup Coverage Expansion, naming ALL sources from the list (required)
    Do not drop any of these if their condition is met.
20. Slide 19 (Near-Term Priorities) — each item: label = action-oriented priority title, detail = 1-sentence justification using real data.
    RANKING RULES — slide 19 must be a RANKED SUBSET (top 3–5 items) of slide 18 priorities, ordered by urgency:
    - Rank #1: critical vulnerabilities — if live_count.critical > 0, this is always #1.
    - Rank #2: EDR Sensor activation — if edrSensor enable:0, always #2.
    - Rank #3 onward: remaining items from slide 18 in order of client risk impact.
    Do NOT simply copy slide 18. Prioritize and rank. If offsite replication appeared on slide 18, it must appear here. If encryption appeared on slide 18, it must appear here.
21. Slide 20 (AI Essentials) — 8 items covering AI risks and readiness. label = topic name (e.g. "Shadow AI Risk", "Data Governance").
    DATA REFERENCE RULE: Every single detail value MUST reference a specific data field and metric from this client's JSON — format: "[AI capability or risk] — [specific client finding + metric from data]." Example: "Shadow AI Risk — EDR Sensor is disabled across 95 endpoints, leaving AI-driven threats undetected."
    Generic boilerplate that could apply to any company is NOT permitted. If a point cannot be tied to real client data, replace it with one that can.
    STRICT LIMIT: the combined total of all 8 detail values must not exceed 125 words.
22. Slide 21 (Implementation Timeline) — 3 items for Q2/Q3/Q4. label = quarter label (e.g. "Q2 2026: April–June"), detail = 2–3 specific initiatives for that quarter.
23. Slide 22 (Budget and Timeline) — fill each table row: recommendation = service name, budget = estimated monthly cost, timeline = target quarter.
24. Slide 23 (Thank You) — content is a plain empty string, leave it as "".

IMPORTANT — THE FOLLOWING SLIDES MUST BE LEFT COMPLETELY UNTOUCHED:
- Industry Trends
- CX Metrics
- Service Review
- Open Technical Items
- Strategic Initiatives
- Current Project Review
- Scheduled Projects
- Budget and Timeline
- Implementation Timeline
- Thank you for our continued partnership!

For these slides, do NOT fill in any empty strings. Return them exactly as they appear in the template, with all empty strings "" remaining as "".

Return ONLY the filled JSON object that exactly matches the structure of the template provided below. No markdown, no code fences, no explanation — just the raw JSON object."""


def _extract_json(text: str) -> Dict[str, Any]:
    """Strip markdown code fences if present and parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


_VIRTUAL_SERVER_PHRASE_MARKERS = ("virtual machine",)


def _is_virtual_server(device: Dict[str, Any]) -> bool:
    """
    Determine whether a device_inventory_server row is a virtual server.

    Rule (per spec): check ONLY the "model" field, two checks:
      1. Phrase check — model contains "virtual machine" → virtual.
         ("virtual" and "machine" are separate words, so this needs its
         own check — neither word alone contains "vm".)
      2. Word-level "vm" check — split model into words on whitespace /
         commas / slashes / hyphens, and if ANY word contains the
         substring "vm" (case-insensitive) → virtual.
         This catches vendor-specific virtualization naming that doesn't
         say "Virtual Machine" literally, e.g.:
           - "VMGuest"                 → word "vmguest" contains "vm"
           - "VMHost"                  → word "vmhost" contains "vm"
           - "VMware Virtual Platform" → word "vmware" contains "vm"
           - "VMware7,1"               → word "vmware7,1" contains "vm"
      Anything else → physical.

    manufacturer/cpu are intentionally NOT checked — model is the single
    source of truth for this classification.
    """
    model = (device.get("model") or "").strip().lower()

    if any(marker in model for marker in _VIRTUAL_SERVER_PHRASE_MARKERS):
        return True

    words = re.split(r"[\s,/\-]+", model)
    return any("vm" in word for word in words if word)


def _compute_deterministic_facts(organization_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute every count/sum-based fact in code so the LLM never has to count
    long arrays or sum long arrays itself. These values are treated as ground
    truth and are:
      (a) injected into the prompt so the LLM copies them, and
      (b) force-applied onto the LLM's response afterward as a hard guarantee.

    Add new entries here any time a new "count X" / "sum Y" rule is added to
    the SYSTEM_PROMPT — never let the LLM do that arithmetic itself.
    """
    ninja = organization_data.get("NinjaOne") or {}
    ninja_tables = ninja.get("tables") or {}

    device_inventory = ninja_tables.get("device_inventory") or []
    device_inventory_server = ninja_tables.get("device_inventory_server") or []

    # ── Workstations and Laptops ──────────────────────────────────────────
    # Rule (per spec): count EVERY entry in device_inventory, no filtering.
    workstation_and_laptop_count = len(device_inventory)
    physical_server_count = 0
    virtual_server_count = 0
    for d in device_inventory_server:
        if _is_virtual_server(d):
            virtual_server_count += 1
        else:
            physical_server_count += 1

    # Distinct locations across workstations + servers (if location data exists)
    locations = set()
    for d in device_inventory + device_inventory_server:
        loc = d.get("location")
        if loc:
            locations.add(loc)
    locations_count = len(locations) if locations else None

    # Total tickets resolved = sum of Autotask.charts.daily_tickets_trend.completed
    autotask = organization_data.get("Autotask") or {}
    daily_trend = (
        (autotask.get("charts") or {}).get("daily_tickets_trend") or {}
    )
    completed_arr = daily_trend.get("completed") or []
    total_tickets_resolved = sum(completed_arr) if completed_arr else 0

    # Users total — only if Microsoft365 data is present
    m365 = organization_data.get("Microsoft365")
    users_total = None
    if m365:
        users_total = (m365.get("users") or {}).get("total")

    # Bitdefender disabled module counts (useful for slides 7, 14, 18, 19, 20)
    bitdefender = organization_data.get("Bitdefender") or {}
    bd_tables = bitdefender.get("tables") or {}
    module_rows = bd_tables.get("networkinventory_bitdefender") or []
    disabled_modules = {
        row.get("displayName") or row.get("Module"): row.get("notenable", 0)
        for row in module_rows
        if row.get("notenable", 0) and row.get("notenable", 0) > 0
    }

    # ConnectSecure vulnerability counts (avoid LLM misreading nested dict)
    connectsecure = organization_data.get("ConnectSecure") or {}
    vuln = (
        (connectsecure.get("charts") or {}).get("vulnerability_severity") or {}
    ).get("live_count") or {}
    critical_vuln_count = vuln.get("critical", 0)
    high_vuln_count = vuln.get("high", 0)

    # LoyaltyLoop NPS + Loyalty score -- sourced directly from code (the
    # LoyaltyLoop processor), never from the LLM. Shape:
    #   organization_data["LoyaltyLoop"]["charts"] = {"nps_score": ..., "loyalty_score": ...}
    loyaltyloop = organization_data.get("LoyaltyLoop") or {}
    ll_charts = loyaltyloop.get("charts") or {}
    nps_score = ll_charts.get("nps_score")
    loyalty_score = ll_charts.get("loyalty_score")

    return {
        "workstation_and_laptop_count": workstation_and_laptop_count,
        "physical_server_count": physical_server_count,
        "virtual_server_count": virtual_server_count,
        "locations_count": locations_count,  # None if no location data
        "total_tickets_resolved": total_tickets_resolved,
        "users_total": users_total,  # None if Microsoft365 data absent
        "disabled_bitdefender_modules": disabled_modules,  # {name: endpoint_count}
        "critical_vulnerability_count": critical_vuln_count,
        "high_vulnerability_count": high_vuln_count,
        "nps_score": nps_score,  # None if LoyaltyLoop data absent
        "loyalty_score": loyalty_score,  # None if LoyaltyLoop data absent
    }


def _apply_deterministic_overrides(
    result: Dict[str, Any],
    facts: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Hard guarantee: force known count/sum fields to their precomputed values,
    regardless of what the LLM actually returned. This makes correctness
    100% guaranteed rather than "probably correct if the model followed
    instructions."
    """
    for slide in result.get("slides", []):
        title = slide.get("title", "")

        if title == "Current Management and Maintenance":
            for item in slide.get("content", []):
                label = item.get("label", "")
                if label == "Workstations and Laptops":
                    item["detail"] = str(facts["workstation_and_laptop_count"])
                elif label == "Physical Servers":
                    item["detail"] = str(facts["physical_server_count"])
                elif label == "Virtual Servers":
                    item["detail"] = str(facts["virtual_server_count"])
                elif label == "Locations":
                    item["detail"] = (
                        str(facts["locations_count"])
                        if facts["locations_count"] is not None
                        else "N/A"
                    )
                elif label == "Users":
                    item["detail"] = (
                        str(facts["users_total"])
                        if facts["users_total"] is not None
                        else "N/A"
                    )

        elif title == "Customer Success Dashboard":
            for item in slide.get("content", []):
                if item.get("label") == "Total Tickets Resolved":
                    item["detail"] = (
                        f"Resolved {facts['total_tickets_resolved']} tickets this period."
                    )

        elif title == "CX Metrics":
            # NPS and Loyalty Score come from LoyaltyLoop data in code, never
            # from the LLM -- this slide is in SKIP_SLIDES, so
            # _preserve_skipped_slides() has already reset `content` back to
            # the clean 3-item template (header + NPS + Loyalty, no blanks,
            # no Score Summary) before this runs. We just fill in the two
            # real numbers by fixed index.
            content = slide.get("content", [])
            nps = facts.get("nps_score")
            loyalty = facts.get("loyalty_score")

            if len(content) > 1:
                content[1]["text"] = (
                    f"Net Promoter Score (NPS): {nps}" if nps is not None
                    else "Net Promoter Score (NPS): N/A"
                )
            if len(content) > 2:
                content[2]["text"] = (
                    f"Loyalty Score: {loyalty}" if loyalty is not None
                    else "Loyalty Score: N/A"
                )

    return result


def _preserve_skipped_slides(
    filled: Dict[str, Any],
    original: Dict[str, Any],
    extra_skips: set = None
) -> Dict[str, Any]:
    """
    Overwrite any slides in SKIP_SLIDES (plus any extra_skips) with their
    original template values, ensuring the LLM did not accidentally fill them.

    Works with the {"slides": [...]} list structure — matches by slide title.
    extra_skips: additional slide titles to skip beyond the global SKIP_SLIDES
                 (used when specific integration data is unavailable).
    """
    skip = SKIP_SLIDES | (extra_skips or set())

    # Build title → original slide lookup
    orig_by_title = {
        slide.get("title", ""): slide
        for slide in original.get("slides", [])
    }

    filled_slides = filled.get("slides", [])
    for i, slide in enumerate(filled_slides):
        title = slide.get("title", "")
        if title in skip and title in orig_by_title:
            filled_slides[i] = orig_by_title[title]

    filled["slides"] = filled_slides
    return filled


class LLMReportService:

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    async def generate_llm_data(self, organization_data: Dict[str, Any], previous_month_data: Optional[Dict[str, Any]] = None, quarterly_breakdown: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send organization_data to OpenAI and get back a filled-in llm_data_template.
        Slides listed in SKIP_SLIDES are preserved from the original template.
        Additional slides are skipped if their source integration data is missing:
          - Cove missing  → Backup / Business Continuity kept empty
          - NinjaOne missing → both Devices slides kept empty

        Count/sum fields (device counts, ticket totals, etc.) are computed in
        Python via _compute_deterministic_facts, injected into the prompt so
        the LLM copies them, and then force-applied onto the response via
        _apply_deterministic_overrides as a hard correctness guarantee.

        Args:
            organization_data: The JSONB data from generated_reports.organization_data

        Returns:
            Filled-in dict matching llm_data_template.json structure
        """
        # ── Detect missing integrations and build extra skips ────────────────
        extra_skips: set = set()

        if not organization_data.get("Cove"):
            extra_skips.add("Backup / Business Continuity")
            logger.info("Cove data not available — Backup / Business Continuity slide will be left empty.")

        if not organization_data.get("NinjaOne"):
            extra_skips.add("Devices Under Management Recommended for Upgrade")
            extra_skips.add("Devices Under Management Recommended for Replacement")
            logger.info("NinjaOne data not available — Devices slides will be left empty.")

        # ── Compute deterministic facts in Python (ground truth) ─────────────
        precomputed_facts = _compute_deterministic_facts(organization_data)
        logger.info(f"Precomputed deterministic facts: {precomputed_facts}")

        template_str = json.dumps(_LLM_TEMPLATE, indent=2)
        org_data_str = json.dumps(organization_data, indent=2)
        precomputed_str = json.dumps(precomputed_facts, indent=2)

        precomputed_block = f"""

<precomputed_facts>
The following values have ALREADY been calculated in code directly from the
raw data below and are GUARANTEED CORRECT. Wherever a rule in the system
prompt asks for one of these numbers, copy it EXACTLY as given here. Do NOT
recount any array yourself and do NOT recalculate any sum yourself — use
these values verbatim.

{precomputed_str}
</precomputed_facts>"""

        prev_block = ""
        if previous_month_data:
            prev_month_str = json.dumps(previous_month_data, indent=2)
            prev_block = f"\n\n<previous_month_autotask>\n{prev_month_str}\n</previous_month_autotask>"

        quarterly_block = ""
        if quarterly_breakdown:
            quarterly_str = json.dumps(quarterly_breakdown, indent=2)
            quarterly_block = f"\n\n<quarterly_breakdown>\n{quarterly_str}\n</quarterly_breakdown>"

        user_message = f"""Here is the MSP platform data for this client:

<organization_data>
{org_data_str}
</organization_data>{precomputed_block}{prev_block}{quarterly_block}

Now fill in the following slide template using this data. Return ONLY the completed JSON:

<template>
{template_str}
</template>"""

        logger.info("Sending organization_data to OpenAI for LLM report generation...")

        response = self.client.chat.completions.create(
            model= "gpt-4o",
            max_completion_tokens=16000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )

        raw_text = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        tokens_used = response.usage.completion_tokens

        logger.info(f"OpenAI responded — finish_reason: {finish_reason}, tokens used: {tokens_used}")

        try:
            result = _extract_json(raw_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            logger.error(f"Raw response (first 500 chars): {raw_text[:500]}")
            raise ValueError(f"OpenAI returned invalid JSON: {e}")

        # Hard guarantee #1: restore skipped slides from the original template
        result = _preserve_skipped_slides(result, _LLM_TEMPLATE, extra_skips)

        # Hard guarantee #2: force-correct count/sum fields regardless of
        # what the LLM returned — this is what fixes the 41-vs-46 bug.
        result = _apply_deterministic_overrides(result, precomputed_facts)

        return result


# Singleton — created lazily so missing API key only fails at call time
_service_instance: LLMReportService | None = None


def get_llm_service() -> LLMReportService:
    global _service_instance
    if _service_instance is None:
        _service_instance = LLMReportService()
    return _service_instance