"""Port name normalization utilities.

Huawei switches use multiple naming conventions for the same physical port:
- SNMP ifDescr: XGigabitEthernet1/0/44, GigabitEthernet0/0/28
- SSH CLI output: XGE1/0/44, GE0/0/28
- NeDi/LLDP: Gi0/0/28, XGi3/0/18, 10GE1/0/1

This module provides a single canonical normalization to prevent duplicate
port records in the database.
"""
import re


def normalize_port_name(port_name: str) -> str:
    """Normalize Huawei/Cisco port names to canonical short form.

    Canonical forms:
        GigabitEthernet0/0/X  -> GE0/0/X
        Gi0/0/X               -> GE0/0/X
        XGigabitEthernet1/0/X -> XGE1/0/X
        XGi3/0/18             -> XGE3/0/18
        10GE1/0/X             -> XGE1/0/X
        40GE1/0/X             -> 40GE1/0/X (kept as-is)
        100GE1/0/X            -> 100GE1/0/X (kept as-is)
        Eth-Trunk 1           -> Eth-Trunk1 (strip spaces)
    """
    if not port_name:
        return port_name

    name = port_name.strip()

    # XGigabitEthernet -> XGE
    name = re.sub(r'^XGigabitEthernet', 'XGE', name)
    # XGi (but not XGigabit already handled) -> XGE
    name = re.sub(r'^XGi(?=\d)', 'XGE', name)
    # 10GE -> XGE
    name = re.sub(r'^10GE', 'XGE', name)

    # GigabitEthernet -> GE
    name = re.sub(r'^GigabitEthernet', 'GE', name)
    # Gi (but not Gig already) -> GE
    name = re.sub(r'^Gi(?=\d)', 'GE', name)

    # Eth-Trunk with optional space
    name = re.sub(r'^Eth-Trunk\s*', 'Eth-Trunk', name)

    return name
