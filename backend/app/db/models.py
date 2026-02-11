"""Database models for Mac-Traker."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SwitchGroup(Base):
    """Group of switches sharing SSH credentials."""

    __tablename__ = "switch_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    ssh_username: Mapped[Optional[str]] = mapped_column(String(100))
    ssh_password_encrypted: Mapped[Optional[str]] = mapped_column(String(500))
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    switches: Mapped[list["Switch"]] = relationship("Switch", back_populates="group")


class Switch(Base):
    """Network switch device."""

    __tablename__ = "switches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(50), default="huawei"
    )  # huawei, cisco, extreme
    snmp_community: Mapped[Optional[str]] = mapped_column(String(100))
    group_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("switch_groups.id", ondelete="SET NULL")
    )
    location: Mapped[Optional[str]] = mapped_column(String(255))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    serial_number: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    use_ssh_fallback: Mapped[bool] = mapped_column(Boolean, default=False)  # Use SSH/CLI when SNMP fails
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_discovery: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # SNMP-discovered system information
    sys_name: Mapped[Optional[str]] = mapped_column(String(255))  # sysName.0 via SNMP
    ports_up_count: Mapped[int] = mapped_column(Integer, default=0)  # Count of ports with ifOperStatus=up
    ports_down_count: Mapped[int] = mapped_column(Integer, default=0)  # Count of ports with ifOperStatus=down
    vlan_count: Mapped[int] = mapped_column(Integer, default=0)  # Number of active VLANs
    # Site code extracted from hostname prefix (e.g., "01" from "01_L2_switch")
    site_code: Mapped[Optional[str]] = mapped_column(String(10), index=True)

    # Relationships
    group: Mapped[Optional["SwitchGroup"]] = relationship(
        "SwitchGroup", back_populates="switches"
    )
    ports: Mapped[list["Port"]] = relationship(
        "Port", back_populates="switch", cascade="all, delete-orphan"
    )
    mac_locations: Mapped[list["MacLocation"]] = relationship(
        "MacLocation", back_populates="switch"
    )
    discovery_logs: Mapped[list["DiscoveryLog"]] = relationship(
        "DiscoveryLog", back_populates="switch"
    )

    __table_args__ = (Index("ix_switches_ip", "ip_address"),)


class Port(Base):
    """Switch port."""

    __tablename__ = "ports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    switch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False
    )
    port_name: Mapped[str] = mapped_column(String(100), nullable=False)
    port_index: Mapped[Optional[int]] = mapped_column(Integer)
    port_description: Mapped[Optional[str]] = mapped_column(String(255))
    port_type: Mapped[str] = mapped_column(
        String(50), default="access"
    )  # access, trunk, uplink
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer)
    admin_status: Mapped[str] = mapped_column(String(20), default="up")
    oper_status: Mapped[str] = mapped_column(String(20), default="up")
    speed: Mapped[Optional[str]] = mapped_column(String(50))
    is_uplink: Mapped[bool] = mapped_column(Boolean, default=False)
    last_mac_count: Mapped[int] = mapped_column(Integer, default=0)
    # LLDP neighbor information (for determining if port is true uplink or AP port)
    lldp_neighbor_name: Mapped[Optional[str]] = mapped_column(String(255))  # Remote system name from LLDP
    lldp_neighbor_type: Mapped[Optional[str]] = mapped_column(String(50))   # switch, router, ap, phone, unknown
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    switch: Mapped["Switch"] = relationship("Switch", back_populates="ports")
    mac_locations: Mapped[list["MacLocation"]] = relationship(
        "MacLocation", back_populates="port"
    )

    __table_args__ = (
        Index("ix_ports_switch_port", "switch_id", "port_name"),
    )


class MacAddress(Base):
    """MAC address entity."""

    __tablename__ = "mac_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mac_address: Mapped[str] = mapped_column(
        String(17), unique=True, nullable=False, index=True
    )
    vendor_oui: Mapped[Optional[str]] = mapped_column(String(8))
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    device_type: Mapped[Optional[str]] = mapped_column(String(100))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    locations: Mapped[list["MacLocation"]] = relationship(
        "MacLocation", back_populates="mac"
    )
    history: Mapped[list["MacHistory"]] = relationship(
        "MacHistory", back_populates="mac"
    )
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="mac")

    __table_args__ = (Index("ix_mac_addresses_mac", "mac_address"),)


class MacLocation(Base):
    """Current location of a MAC address."""

    __tablename__ = "mac_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mac_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mac_addresses.id", ondelete="CASCADE"), nullable=False
    )
    switch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False
    )
    port_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ports.id", ondelete="CASCADE"), nullable=False
    )
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    hostname: Mapped[Optional[str]] = mapped_column(String(255))
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    mac: Mapped["MacAddress"] = relationship("MacAddress", back_populates="locations")
    switch: Mapped["Switch"] = relationship("Switch", back_populates="mac_locations")
    port: Mapped["Port"] = relationship("Port", back_populates="mac_locations")

    __table_args__ = (
        Index("ix_mac_locations_mac_current", "mac_id", "is_current"),
        Index("ix_mac_locations_switch_port", "switch_id", "port_id"),
    )


class MacHistory(Base):
    """Historical movement of MAC addresses."""

    __tablename__ = "mac_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mac_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mac_addresses.id", ondelete="CASCADE"), nullable=False
    )
    switch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    port_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    event_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # new, move, disappear
    event_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    previous_switch_id: Mapped[Optional[int]] = mapped_column(Integer)
    previous_port_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    mac: Mapped["MacAddress"] = relationship("MacAddress", back_populates="history")

    __table_args__ = (
        Index("ix_mac_history_mac_date", "mac_id", "event_at"),
        Index("ix_mac_history_event_at", "event_at"),
    )


class TopologyLink(Base):
    """Network topology link between switches."""

    __tablename__ = "topology_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    local_switch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False
    )
    local_port_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ports.id", ondelete="CASCADE"), nullable=False
    )
    remote_switch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False
    )
    remote_port_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ports.id", ondelete="SET NULL")
    )
    protocol: Mapped[str] = mapped_column(String(20), default="lldp")  # lldp, cdp
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_topology_links_local", "local_switch_id", "local_port_id"),
    )


class Alert(Base):
    """System alert."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # new_mac, mac_move, mac_disappear, port_threshold
    mac_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("mac_addresses.id", ondelete="SET NULL")
    )
    switch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="SET NULL")
    )
    port_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ports.id", ondelete="SET NULL")
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info, warning, critical
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    mac: Mapped[Optional["MacAddress"]] = relationship(
        "MacAddress", back_populates="alerts"
    )

    __table_args__ = (
        Index("ix_alerts_unread", "is_read", "created_at"),
        Index("ix_alerts_type", "alert_type"),
    )


class OuiVendor(Base):
    """OUI vendor database."""

    __tablename__ = "oui_vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    oui_prefix: Mapped[str] = mapped_column(
        String(8), unique=True, nullable=False, index=True
    )
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type_hint: Mapped[Optional[str]] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DiscoveryLog(Base):
    """Discovery operation log."""

    __tablename__ = "discovery_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    switch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="SET NULL")
    )
    discovery_type: Mapped[str] = mapped_column(String(20), nullable=False)  # snmp, cli
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, error
    mac_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    switch: Mapped[Optional["Switch"]] = relationship(
        "Switch", back_populates="discovery_logs"
    )

    __table_args__ = (Index("ix_discovery_logs_started", "started_at"),)


class Setting(Base):
    """Application settings."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AlertRule(Base):
    """Custom alert rule definition."""

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Rule types: oui_filter, switch_filter, port_filter, vlan_filter, vendor_filter
    conditions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON conditions
    alert_severity: Mapped[str] = mapped_column(String(20), default="warning")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_alert_rules_enabled", "is_enabled"),)


class Webhook(Base):
    """Webhook endpoint for external notifications."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    webhook_type: Mapped[str] = mapped_column(String(50), default="generic")
    # Types: generic, slack, teams, discord, siem
    secret_token: Mapped[Optional[str]] = mapped_column(String(500))  # For signature verification
    alert_types: Mapped[str] = mapped_column(Text, default="all")  # JSON array or "all"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_status: Mapped[Optional[str]] = mapped_column(String(50))  # success, error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_webhooks_enabled", "is_enabled"),)


class Host(Base):
    """Network endpoint/host device (IP Fabric-like host table).

    This table tracks end devices (workstations, printers, phones, servers, etc.)
    discovered via MAC/ARP tables, separate from network infrastructure.
    """

    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mac_address: Mapped[str] = mapped_column(String(17), unique=True, nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), index=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    # Vendor information
    vendor_oui: Mapped[Optional[str]] = mapped_column(String(8))
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Device classification
    device_type: Mapped[Optional[str]] = mapped_column(String(50))  # workstation, printer, phone, server, iot, camera, unknown
    device_model: Mapped[Optional[str]] = mapped_column(String(255))  # If determinable
    os_type: Mapped[Optional[str]] = mapped_column(String(100))  # Windows, Linux, iOS, etc. (if determinable)

    # Current edge location (where the host connects to the network)
    edge_switch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("switches.id", ondelete="SET NULL")
    )
    edge_port_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ports.id", ondelete="SET NULL")
    )
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer)
    vrf: Mapped[Optional[str]] = mapped_column(String(50))  # VRF name if applicable
    site_code: Mapped[Optional[str]] = mapped_column(String(10), index=True)

    # Classification flags
    is_infrastructure: Mapped[bool] = mapped_column(Boolean, default=False)  # Is this a network device?
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False)  # VM detected via OUI
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)  # Marked as critical by user

    # Discovery status
    discovery_attempted: Mapped[bool] = mapped_column(Boolean, default=False)  # Did we try to discover it?
    discovery_result: Mapped[Optional[str]] = mapped_column(String(50))  # success, auth_failed, timeout, not_network_device

    # Timestamps
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # User-added notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_hosts_mac", "mac_address"),
        Index("ix_hosts_ip", "ip_address"),
        Index("ix_hosts_edge", "edge_switch_id", "edge_port_id"),
        Index("ix_hosts_site", "site_code"),
        Index("ix_hosts_active", "is_active", "last_seen"),
    )


class NetworkSnapshot(Base):
    """Immutable network state snapshot (IP Fabric-like snapshot system).

    Each discovery run creates a snapshot that captures the complete network state
    at that point in time. Snapshots are immutable once created.
    """

    __tablename__ = "network_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(100))  # Optional user-friendly name
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Snapshot status
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed

    # Statistics captured in this snapshot
    total_switches: Mapped[int] = mapped_column(Integer, default=0)
    total_ports: Mapped[int] = mapped_column(Integer, default=0)
    total_macs: Mapped[int] = mapped_column(Integer, default=0)
    total_hosts: Mapped[int] = mapped_column(Integer, default=0)
    total_links: Mapped[int] = mapped_column(Integer, default=0)

    # Discovery metrics
    switches_discovered: Mapped[int] = mapped_column(Integer, default=0)
    switches_failed: Mapped[int] = mapped_column(Integer, default=0)
    discovery_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Retention
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)  # Prevent auto-deletion
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)  # Mark as baseline for comparison

    __table_args__ = (
        Index("ix_snapshots_status", "status"),
        Index("ix_snapshots_completed", "completed_at"),
    )


class SnapshotMacLocation(Base):
    """MAC location data captured in a specific snapshot.

    This is the immutable record of where each MAC was located
    at the time of the snapshot.
    """

    __tablename__ = "snapshot_mac_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("network_snapshots.id", ondelete="CASCADE"), nullable=False
    )

    # MAC information (denormalized for snapshot immutability)
    mac_address: Mapped[str] = mapped_column(String(17), nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    hostname: Mapped[Optional[str]] = mapped_column(String(255))
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    device_type: Mapped[Optional[str]] = mapped_column(String(100))

    # Location (denormalized)
    switch_hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    switch_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    port_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer)
    site_code: Mapped[Optional[str]] = mapped_column(String(10))

    __table_args__ = (
        Index("ix_snapshot_macs_snapshot", "snapshot_id"),
        Index("ix_snapshot_macs_mac", "mac_address"),
        Index("ix_snapshot_macs_switch", "switch_hostname"),
    )
