"""
Slide Registry — maps JSON integration keys to their section builder functions.
Adding a new integration = add one entry here + create a section file.
The report generator iterates this registry and calls only sections present in the JSON.
"""
from app.services.ppt.sections import (
    ninjaone_section,
    autotask_section,
    connectsecure_section,
    bitdefender_section,
    sentinelone_section,
    nodeware_section,
    cove_section,
    DNS_section,
    dropsuite_section,
    blackpoint_section,
    infima_section,
    axcient_section
)

REGISTRY = [
    ("NinjaOne",       ninjaone_section.build_slides),
    ("Autotask",       autotask_section.build_slides),
    ("ConnectSecure",  connectsecure_section.build_slides),
    ("Cove",           cove_section.build_slides),
    ("Bitdefender",    bitdefender_section.build_slides),
    ("SentinelOne",    sentinelone_section.build_slides),
    ("NodeWare",       nodeware_section.build_slides),
    ("DNSFilter",      DNS_section.build_slides),
    ("Dropsuite",      dropsuite_section.build_slides),
    ("Blackpoint",     blackpoint_section.build_slides),
    ("Infima",         infima_section.build_slides),
    ("Axcient",        axcient_section.build_slides)
]
