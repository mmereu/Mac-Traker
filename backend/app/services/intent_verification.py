"""Intent Verification Service - IP Fabric-like network compliance checks.

This module provides automated checks to verify network intent and detect
configuration issues, anomalies, and compliance violations.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any, Optional
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.db.models import (
    Switch, Port, MacAddress, MacLocation, TopologyLink, Host
)


class CheckSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CheckCategory(str, Enum):
    TOPOLOGY = "topology"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"
    AVAILABILITY = "availability"


@dataclass
class IntentCheckResult:
    """Result of a single intent verification check."""
    check_id: str
    check_name: str
    category: CheckCategory
    severity: CheckSeverity
    passed: bool
    message: str
    affected_items: List[Dict[str, Any]]
    checked_at: datetime
    details: Optional[Dict[str, Any]] = None
    remediation: Optional[str] = None  # Suggested fix/action


class IntentVerificationService:
    """Service for running network intent verification checks."""

    def __init__(self, db: Session):
        self.db = db
        self._checks = [
            self._check_duplicate_mac,
            self._check_duplicate_ip,
            self._check_orphan_ports,
            self._check_uplink_consistency,
            self._check_mac_on_multiple_switches,
            self._check_switch_connectivity,
            self._check_high_mac_count_ports,
            self._check_inactive_switches,
            self._check_vlan_spread,
            self._check_stale_macs,
            self._check_vlan_consistency,
            self._check_vlan_mismatch_on_trunk,
        ]

    def run_all_checks(self) -> List[IntentCheckResult]:
        """Run all intent verification checks."""
        results = []
        for check_func in self._checks:
            try:
                result = check_func()
                results.append(result)
            except Exception as e:
                # Create error result for failed check
                results.append(IntentCheckResult(
                    check_id=check_func.__name__,
                    check_name=check_func.__name__.replace('_check_', '').replace('_', ' ').title(),
                    category=CheckCategory.COMPLIANCE,
                    severity=CheckSeverity.ERROR,
                    passed=False,
                    message=f"Check failed with error: {str(e)}",
                    affected_items=[],
                    checked_at=datetime.utcnow()
                ))
        return results

    def run_check(self, check_id: str) -> Optional[IntentCheckResult]:
        """Run a specific check by ID."""
        for check_func in self._checks:
            if check_func.__name__ == f"_check_{check_id}":
                return check_func()
        return None

    def get_available_checks(self) -> List[Dict[str, str]]:
        """Get list of available checks."""
        return [
            {
                "id": func.__name__.replace('_check_', ''),
                "name": func.__name__.replace('_check_', '').replace('_', ' ').title(),
                "description": func.__doc__ or ""
            }
            for func in self._checks
        ]

    # ==========================================
    # INTENT CHECKS
    # ==========================================

    def _check_duplicate_mac(self) -> IntentCheckResult:
        """Check for duplicate MAC addresses across the network."""
        # Find MACs appearing on multiple ports as endpoint (not uplink)
        duplicates = []

        # Get all current MAC locations on non-uplink ports
        locations = self.db.query(
            MacLocation.mac_id,
            func.count(MacLocation.id).label('location_count')
        ).join(
            Port, MacLocation.port_id == Port.id
        ).filter(
            MacLocation.is_current == True,
            Port.is_uplink == False
        ).group_by(
            MacLocation.mac_id
        ).having(
            func.count(MacLocation.id) > 1
        ).all()

        for loc in locations:
            mac = self.db.query(MacAddress).filter(MacAddress.id == loc.mac_id).first()
            if mac:
                # Get all locations for this MAC
                mac_locs = self.db.query(MacLocation).join(Port).filter(
                    MacLocation.mac_id == loc.mac_id,
                    MacLocation.is_current == True,
                    Port.is_uplink == False
                ).all()

                switches = []
                for ml in mac_locs:
                    sw = self.db.query(Switch).filter(Switch.id == ml.switch_id).first()
                    pt = self.db.query(Port).filter(Port.id == ml.port_id).first()
                    if sw and pt:
                        switches.append({
                            "switch": sw.hostname,
                            "port": pt.port_name
                        })

                duplicates.append({
                    "mac_address": mac.mac_address,
                    "vendor": mac.vendor_name,
                    "locations": switches
                })

        return IntentCheckResult(
            check_id="duplicate_mac",
            check_name="Duplicate MAC Address",
            category=CheckCategory.SECURITY,
            severity=CheckSeverity.WARNING if duplicates else CheckSeverity.INFO,
            passed=len(duplicates) == 0,
            message=f"Found {len(duplicates)} MAC addresses on multiple endpoint ports" if duplicates else "No duplicate MACs found",
            affected_items=duplicates,
            checked_at=datetime.utcnow(),
            remediation="1. Run Discovery per aggiornare le MAC table\n2. Verificare se i MAC duplicati sono VM migrate o dispositivi mobili\n3. Controllare la retention policy per eliminare dati stale\n4. Se persistente, verificare loop di rete o configurazioni errate" if duplicates else None
        )

    def _check_duplicate_ip(self) -> IntentCheckResult:
        """Check for duplicate IP addresses in the network."""
        # Find IPs assigned to multiple MACs
        duplicates = []

        ip_counts = self.db.query(
            MacLocation.ip_address,
            func.count(func.distinct(MacLocation.mac_id)).label('mac_count')
        ).filter(
            MacLocation.is_current == True,
            MacLocation.ip_address.isnot(None),
            MacLocation.ip_address != ''
        ).group_by(
            MacLocation.ip_address
        ).having(
            func.count(func.distinct(MacLocation.mac_id)) > 1
        ).all()

        for ip_row in ip_counts:
            # Get all MACs with this IP
            macs_with_ip = self.db.query(MacLocation).join(MacAddress).filter(
                MacLocation.is_current == True,
                MacLocation.ip_address == ip_row.ip_address
            ).all()

            mac_list = []
            for loc in macs_with_ip:
                mac = self.db.query(MacAddress).filter(MacAddress.id == loc.mac_id).first()
                sw = self.db.query(Switch).filter(Switch.id == loc.switch_id).first()
                if mac and sw:
                    mac_list.append({
                        "mac_address": mac.mac_address,
                        "vendor": mac.vendor_name,
                        "switch": sw.hostname
                    })

            duplicates.append({
                "ip_address": ip_row.ip_address,
                "mac_count": ip_row.mac_count,
                "macs": mac_list
            })

        return IntentCheckResult(
            check_id="duplicate_ip",
            check_name="Duplicate IP Address",
            category=CheckCategory.SECURITY,
            severity=CheckSeverity.ERROR if duplicates else CheckSeverity.INFO,
            passed=len(duplicates) == 0,
            message=f"Found {len(duplicates)} IP addresses assigned to multiple MACs" if duplicates else "No duplicate IPs found",
            affected_items=duplicates,
            checked_at=datetime.utcnow(),
            remediation="1. CRITICO: Conflitto IP può causare problemi di rete\n2. Verificare configurazione DHCP per IP duplicati\n3. Controllare se ci sono IP statici configurati erroneamente\n4. Eseguire arp scan per confermare il conflitto attuale" if duplicates else None
        )

    def _check_orphan_ports(self) -> IntentCheckResult:
        """Check for ports with MACs but not marked as uplink or having topology links."""
        orphans = []

        # Find ports with many MACs that are not uplinks
        high_mac_ports = self.db.query(Port).filter(
            Port.is_uplink == False,
            Port.last_mac_count > 10  # Threshold for suspicious
        ).all()

        for port in high_mac_ports:
            # Check if port has topology link
            has_link = self.db.query(TopologyLink).filter(
                (TopologyLink.local_port_id == port.id) |
                (TopologyLink.remote_port_id == port.id)
            ).first()

            if not has_link:
                sw = self.db.query(Switch).filter(Switch.id == port.switch_id).first()
                if sw:
                    orphans.append({
                        "switch": sw.hostname,
                        "port": port.port_name,
                        "mac_count": port.last_mac_count,
                        "suggestion": "Port may be an undetected uplink"
                    })

        return IntentCheckResult(
            check_id="orphan_ports",
            check_name="Potential Undetected Uplinks",
            category=CheckCategory.TOPOLOGY,
            severity=CheckSeverity.WARNING if orphans else CheckSeverity.INFO,
            passed=len(orphans) == 0,
            message=f"Found {len(orphans)} ports with high MAC count not marked as uplink" if orphans else "All high-MAC ports are correctly classified",
            affected_items=orphans,
            checked_at=datetime.utcnow(),
            remediation="1. Verificare manualmente se le porte elencate sono uplink verso altri switch\n2. Eseguire 'display lldp neighbor' sullo switch per confermare connessioni\n3. Se è uplink, marcare la porta come uplink nel database\n4. Se è un hub/switch non gestito, documentare come eccezione" if orphans else None
        )

    def _check_uplink_consistency(self) -> IntentCheckResult:
        """Check that uplink ports have corresponding topology links."""
        inconsistent = []

        uplink_ports = self.db.query(Port).filter(Port.is_uplink == True).all()

        for port in uplink_ports:
            has_link = self.db.query(TopologyLink).filter(
                (TopologyLink.local_port_id == port.id) |
                (TopologyLink.remote_port_id == port.id)
            ).first()

            if not has_link:
                sw = self.db.query(Switch).filter(Switch.id == port.switch_id).first()
                if sw:
                    inconsistent.append({
                        "switch": sw.hostname,
                        "port": port.port_name,
                        "issue": "Marked as uplink but no topology link found"
                    })

        return IntentCheckResult(
            check_id="uplink_consistency",
            check_name="Uplink Topology Consistency",
            category=CheckCategory.TOPOLOGY,
            severity=CheckSeverity.WARNING if inconsistent else CheckSeverity.INFO,
            passed=len(inconsistent) == 0,
            message=f"Found {len(inconsistent)} uplink ports without topology links" if inconsistent else "All uplink ports have valid topology links",
            affected_items=inconsistent,
            checked_at=datetime.utcnow(),
            remediation="1. Eseguire NeDi Sync per importare i dati LLDP aggiornati\n2. Verificare che LLDP sia abilitato sugli switch interessati\n3. Se la porta non è più un uplink, rimuovere il flag is_uplink\n4. Controllare se lo switch remoto è presente nel database" if inconsistent else None
        )

    def _check_mac_on_multiple_switches(self) -> IntentCheckResult:
        """Check for MACs appearing on multiple switches simultaneously on ENDPOINT ports only.

        MACs on uplink/trunk ports are expected to appear on multiple switches - that's normal.
        This check only flags MACs appearing on multiple ENDPOINT (non-uplink) ports.
        Excludes ports with uplink-like names: Eth-Trunk, XGigabitEthernet, etc.
        """
        issues = []

        # Uplink port name patterns to exclude
        uplink_patterns = ['Eth-Trunk', 'XGigabitEthernet', 'XGE', '10GE', '40GE', '100GE', 'Po', 'Port-channel']

        def is_likely_uplink_port(port_name: str) -> bool:
            """Check if port name suggests it's an uplink."""
            if not port_name:
                return False
            for pattern in uplink_patterns:
                if pattern.lower() in port_name.lower():
                    return True
            return False

        # Get MACs with current location on multiple switches - ONLY on non-uplink ports
        multi_switch_macs = self.db.query(
            MacLocation.mac_id,
            func.count(func.distinct(MacLocation.switch_id)).label('switch_count')
        ).join(
            Port, MacLocation.port_id == Port.id
        ).filter(
            MacLocation.is_current == True,
            Port.is_uplink == False  # Only endpoint ports
        ).group_by(
            MacLocation.mac_id
        ).having(
            func.count(func.distinct(MacLocation.switch_id)) > 2
        ).all()

        for row in multi_switch_macs:
            mac = self.db.query(MacAddress).filter(MacAddress.id == row.mac_id).first()
            if mac:
                # Get only endpoint port locations
                locations = self.db.query(MacLocation).join(Port).filter(
                    MacLocation.mac_id == row.mac_id,
                    MacLocation.is_current == True,
                    Port.is_uplink == False
                ).all()

                # Filter out locations on likely-uplink ports by name
                filtered_locations = []
                for loc in locations:
                    pt = self.db.query(Port).filter(Port.id == loc.port_id).first()
                    if pt and not is_likely_uplink_port(pt.port_name):
                        sw = self.db.query(Switch).filter(Switch.id == loc.switch_id).first()
                        if sw:
                            filtered_locations.append(f"{sw.hostname}:{pt.port_name}")

                # Only report if still on multiple switches after filtering
                unique_switches = set(loc.split(':')[0] for loc in filtered_locations)
                if len(unique_switches) > 2:
                    issues.append({
                        "mac_address": mac.mac_address,
                        "vendor": mac.vendor_name,
                        "switch_count": len(unique_switches),
                        "locations": filtered_locations[:20]  # Limit output
                    })

        return IntentCheckResult(
            check_id="mac_on_multiple_switches",
            check_name="MAC on Multiple Switches",
            category=CheckCategory.TOPOLOGY,
            severity=CheckSeverity.WARNING if issues else CheckSeverity.INFO,  # Reduced from ERROR
            passed=len(issues) == 0,
            message=f"Found {len(issues)} MACs appearing on more than 2 switches (endpoint ports only)" if issues else "No MAC address spread issues detected",
            affected_items=issues[:50],  # Limit output
            checked_at=datetime.utcnow(),
            remediation="1. Probabilmente dati storici non puliti - eseguire Cleanup\n2. Verificare la retention policy (consigliato 7-14 giorni)\n3. Alcuni MAC mobili (laptop, telefoni) sono normali\n4. Controllare se ci sono uplink non riconosciuti che causano duplicazioni" if issues else None
        )

    def _check_switch_connectivity(self) -> IntentCheckResult:
        """Check for switches without any topology links (isolated)."""
        isolated = []

        switches = self.db.query(Switch).filter(Switch.is_active == True).all()

        for switch in switches:
            link_count = self.db.query(TopologyLink).filter(
                (TopologyLink.local_switch_id == switch.id) |
                (TopologyLink.remote_switch_id == switch.id)
            ).count()

            if link_count == 0:
                isolated.append({
                    "switch": switch.hostname,
                    "ip_address": switch.ip_address,
                    "site_code": switch.site_code,
                    "issue": "No topology links detected"
                })

        return IntentCheckResult(
            check_id="switch_connectivity",
            check_name="Switch Topology Connectivity",
            category=CheckCategory.AVAILABILITY,
            severity=CheckSeverity.WARNING if isolated else CheckSeverity.INFO,
            passed=len(isolated) == 0,
            message=f"Found {len(isolated)} isolated switches without topology links" if isolated else "All active switches have topology connectivity",
            affected_items=isolated,
            checked_at=datetime.utcnow(),
            remediation="1. Eseguire NeDi Sync per importare i link LLDP\n2. Verificare che LLDP sia abilitato sugli switch\n3. Alcuni switch potrebbero essere standalone (AP, access point)\n4. Verificare connettività fisica e cablaggio" if isolated else None
        )

    def _check_high_mac_count_ports(self) -> IntentCheckResult:
        """Check for access ports with unusually high MAC counts (>50)."""
        suspicious = []

        high_mac_ports = self.db.query(Port).filter(
            Port.is_uplink == False,
            Port.last_mac_count > 50
        ).all()

        for port in high_mac_ports:
            sw = self.db.query(Switch).filter(Switch.id == port.switch_id).first()
            if sw:
                suspicious.append({
                    "switch": sw.hostname,
                    "port": port.port_name,
                    "mac_count": port.last_mac_count,
                    "suggestion": "May be hub, unmanaged switch, or misconfigured uplink"
                })

        return IntentCheckResult(
            check_id="high_mac_count_ports",
            check_name="High MAC Count Access Ports",
            category=CheckCategory.SECURITY,
            severity=CheckSeverity.WARNING if suspicious else CheckSeverity.INFO,
            passed=len(suspicious) == 0,
            message=f"Found {len(suspicious)} access ports with >50 MACs" if suspicious else "No access ports with abnormally high MAC counts",
            affected_items=suspicious,
            checked_at=datetime.utcnow(),
            remediation="1. Verificare se c'è un hub o switch non gestito collegato\n2. Controllare se la porta è un uplink non marcato correttamente\n3. Può essere normale per porte con VM host o access point\n4. Considerare port-security se è un problema di sicurezza" if suspicious else None
        )

    def _check_inactive_switches(self) -> IntentCheckResult:
        """Check for switches marked inactive that still have active MAC locations."""
        issues = []

        inactive_switches = self.db.query(Switch).filter(Switch.is_active == False).all()

        for switch in inactive_switches:
            active_macs = self.db.query(MacLocation).filter(
                MacLocation.switch_id == switch.id,
                MacLocation.is_current == True
            ).count()

            if active_macs > 0:
                issues.append({
                    "switch": switch.hostname,
                    "ip_address": switch.ip_address,
                    "active_macs": active_macs,
                    "issue": "Inactive switch still has current MAC locations"
                })

        return IntentCheckResult(
            check_id="inactive_switches",
            check_name="Inactive Switch Data Consistency",
            category=CheckCategory.COMPLIANCE,
            severity=CheckSeverity.WARNING if issues else CheckSeverity.INFO,
            passed=len(issues) == 0,
            message=f"Found {len(issues)} inactive switches with active MAC data" if issues else "No data inconsistencies on inactive switches",
            affected_items=issues,
            checked_at=datetime.utcnow(),
            remediation="1. Se lo switch è stato dismesso, eseguire Cleanup per rimuovere i dati\n2. Se lo switch è ancora attivo, riattivarlo nel database\n3. Verificare lo stato di connettività dello switch\n4. Rimuovere completamente lo switch se non più in uso" if issues else None
        )

    def _check_vlan_spread(self) -> IntentCheckResult:
        """Check for VLANs that are spread across many sites (potential misconfiguration)."""
        issues = []

        # Get VLANs by site
        vlan_sites = self.db.query(
            MacLocation.vlan_id,
            Switch.site_code
        ).join(
            Switch, MacLocation.switch_id == Switch.id
        ).filter(
            MacLocation.is_current == True,
            MacLocation.vlan_id.isnot(None),
            Switch.site_code.isnot(None)
        ).distinct().all()

        # Group by VLAN
        vlan_to_sites: Dict[int, set] = {}
        for vlan_id, site_code in vlan_sites:
            if vlan_id not in vlan_to_sites:
                vlan_to_sites[vlan_id] = set()
            vlan_to_sites[vlan_id].add(site_code)

        # Flag VLANs on more than 10 sites
        for vlan_id, sites in vlan_to_sites.items():
            if len(sites) > 10:
                issues.append({
                    "vlan_id": vlan_id,
                    "site_count": len(sites),
                    "sites": list(sites)[:10],  # Limit output
                    "note": "VLAN spans many sites, verify if intentional"
                })

        return IntentCheckResult(
            check_id="vlan_spread",
            check_name="VLAN Site Distribution",
            category=CheckCategory.COMPLIANCE,
            severity=CheckSeverity.INFO,
            passed=len(issues) == 0,
            message=f"Found {len(issues)} VLANs spanning more than 10 sites" if issues else "VLAN distribution within normal parameters",
            affected_items=issues,
            checked_at=datetime.utcnow(),
            remediation="1. Verificare se è intenzionale (es. VLAN management globale)\n2. VLAN come 1 (default) o management sono normalmente globali\n3. Considerare segmentazione per motivi di sicurezza\n4. Documentare le VLAN globali come eccezioni note" if issues else None
        )

    def _check_stale_macs(self) -> IntentCheckResult:
        """Check for MACs not seen in the last 7 days but still marked current."""
        issues = []
        threshold = datetime.utcnow() - timedelta(days=7)

        stale_locations = self.db.query(MacLocation).filter(
            MacLocation.is_current == True,
            MacLocation.seen_at < threshold
        ).limit(100).all()  # Limit to avoid huge results

        for loc in stale_locations:
            mac = self.db.query(MacAddress).filter(MacAddress.id == loc.mac_id).first()
            sw = self.db.query(Switch).filter(Switch.id == loc.switch_id).first()
            if mac and sw:
                issues.append({
                    "mac_address": mac.mac_address,
                    "switch": sw.hostname,
                    "last_seen": loc.seen_at.isoformat() if loc.seen_at else None,
                    "days_ago": (datetime.utcnow() - loc.seen_at).days if loc.seen_at else None
                })

        total_stale = self.db.query(MacLocation).filter(
            MacLocation.is_current == True,
            MacLocation.seen_at < threshold
        ).count()

        return IntentCheckResult(
            check_id="stale_macs",
            check_name="Stale MAC Addresses",
            category=CheckCategory.COMPLIANCE,
            severity=CheckSeverity.WARNING if total_stale > 100 else CheckSeverity.INFO,
            passed=total_stale == 0,
            message=f"Found {total_stale} MAC addresses not seen in 7+ days" if total_stale > 0 else "All current MACs have been seen recently",
            affected_items=issues[:50],  # Limit output
            checked_at=datetime.utcnow(),
            details={"total_stale": total_stale, "sample_size": len(issues)},
            remediation="1. Eseguire Cleanup manuale da Impostazioni\n2. Configurare retention automatica (consigliato 7-14 giorni)\n3. Verificare che il Discovery sia in esecuzione regolarmente\n4. I MAC stale potrebbero essere dispositivi spenti o rimossi" if total_stale > 0 else None
        )


    def _check_vlan_consistency(self) -> IntentCheckResult:
        """Check for same MAC appearing on different VLANs across switches (VLAN mismatch)."""
        issues = []

        # Get MACs with current locations on multiple VLANs
        mac_vlans = self.db.query(
            MacLocation.mac_id,
            func.count(func.distinct(MacLocation.vlan_id)).label('vlan_count')
        ).filter(
            MacLocation.is_current == True,
            MacLocation.vlan_id.isnot(None)
        ).group_by(
            MacLocation.mac_id
        ).having(
            func.count(func.distinct(MacLocation.vlan_id)) > 1
        ).all()

        for row in mac_vlans:
            mac = self.db.query(MacAddress).filter(MacAddress.id == row.mac_id).first()
            if not mac:
                continue

            # Get all VLAN locations for this MAC
            locations = self.db.query(MacLocation).filter(
                MacLocation.mac_id == row.mac_id,
                MacLocation.is_current == True,
                MacLocation.vlan_id.isnot(None)
            ).all()

            vlan_details = []
            for loc in locations:
                sw = self.db.query(Switch).filter(Switch.id == loc.switch_id).first()
                pt = self.db.query(Port).filter(Port.id == loc.port_id).first()
                if sw and pt:
                    vlan_details.append({
                        "switch": sw.hostname,
                        "port": pt.port_name,
                        "vlan_id": loc.vlan_id
                    })

            # Check if this is a real mismatch (different VLANs on endpoint ports)
            vlans_seen = set(d["vlan_id"] for d in vlan_details)
            if len(vlans_seen) > 1:
                issues.append({
                    "mac_address": mac.mac_address,
                    "vendor": mac.vendor_name,
                    "vlan_count": len(vlans_seen),
                    "vlans": list(vlans_seen),
                    "locations": vlan_details[:5],  # Limit
                    "issue": "Same MAC on different VLANs"
                })

        return IntentCheckResult(
            check_id="vlan_consistency",
            check_name="VLAN Consistency",
            category=CheckCategory.COMPLIANCE,
            severity=CheckSeverity.WARNING if issues else CheckSeverity.INFO,
            passed=len(issues) == 0,
            message=f"Found {len(issues)} MACs appearing on multiple VLANs" if issues else "All MACs are consistent within their VLANs",
            affected_items=issues[:20],  # Limit output
            checked_at=datetime.utcnow(),
            details={"total_issues": len(issues)},
            remediation="1. Può essere normale per dispositivi con più interfacce (server, router)\n2. Verificare se il MAC è di un dispositivo legittimamente multi-VLAN\n3. Controllare eventuali errori di configurazione VLAN\n4. Eseguire Cleanup per rimuovere dati stale" if issues else None
        )

    def _check_vlan_mismatch_on_trunk(self) -> IntentCheckResult:
        """Check for VLAN mismatches between linked switches (trunk VLAN consistency)."""
        issues = []

        # Get all topology links
        links = self.db.query(TopologyLink).all()

        for link in links:
            local_sw = self.db.query(Switch).filter(Switch.id == link.local_switch_id).first()
            remote_sw = self.db.query(Switch).filter(Switch.id == link.remote_switch_id).first()

            if not local_sw or not remote_sw:
                continue

            # Get VLANs seen on local switch
            local_vlans = set()
            local_locs = self.db.query(MacLocation.vlan_id).filter(
                MacLocation.switch_id == link.local_switch_id,
                MacLocation.is_current == True,
                MacLocation.vlan_id.isnot(None)
            ).distinct().all()
            for v in local_locs:
                if v.vlan_id:
                    local_vlans.add(v.vlan_id)

            # Get VLANs seen on remote switch
            remote_vlans = set()
            remote_locs = self.db.query(MacLocation.vlan_id).filter(
                MacLocation.switch_id == link.remote_switch_id,
                MacLocation.is_current == True,
                MacLocation.vlan_id.isnot(None)
            ).distinct().all()
            for v in remote_locs:
                if v.vlan_id:
                    remote_vlans.add(v.vlan_id)

            # Find VLANs only on one side
            only_local = local_vlans - remote_vlans
            only_remote = remote_vlans - local_vlans

            # Flag if significant mismatch (>5 VLANs different)
            if len(only_local) > 5 or len(only_remote) > 5:
                issues.append({
                    "link": f"{local_sw.hostname} <-> {remote_sw.hostname}",
                    "local_switch": local_sw.hostname,
                    "remote_switch": remote_sw.hostname,
                    "only_on_local": list(only_local)[:10],
                    "only_on_remote": list(only_remote)[:10],
                    "common_vlans": len(local_vlans & remote_vlans),
                    "issue": "VLAN mismatch between linked switches"
                })

        return IntentCheckResult(
            check_id="vlan_mismatch_on_trunk",
            check_name="Trunk VLAN Mismatch",
            category=CheckCategory.COMPLIANCE,
            severity=CheckSeverity.WARNING if issues else CheckSeverity.INFO,
            passed=len(issues) == 0,
            message=f"Found {len(issues)} trunk links with VLAN mismatches" if issues else "All trunk links have consistent VLANs",
            affected_items=issues,
            checked_at=datetime.utcnow(),
            remediation="1. Verificare la configurazione trunk sugli switch interessati\n2. Controllare che le VLAN siano propagate correttamente\n3. Può essere normale se le VLAN sono filtrate intenzionalmente\n4. Usare 'display vlan' per confrontare le configurazioni" if issues else None
        )


def get_intent_verification_service(db: Session) -> IntentVerificationService:
    """Factory function to get IntentVerificationService instance."""
    return IntentVerificationService(db)
