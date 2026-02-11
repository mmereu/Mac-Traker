"""Alert generation and management service."""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Alert, MacAddress, Switch, Port

logger = logging.getLogger(__name__)


class AlertService:
    """Service for generating and managing alerts."""

    def __init__(self, db: Session):
        self.db = db

    def create_new_mac_alert(
        self,
        mac: MacAddress,
        switch: Switch,
        port: Port,
        vlan_id: Optional[int] = None
    ) -> Alert:
        """
        Create an alert for a newly discovered MAC address.

        Args:
            mac: The new MAC address
            switch: The switch where the MAC was discovered
            port: The port where the MAC was discovered
            vlan_id: Optional VLAN ID

        Returns:
            The created Alert object
        """
        vendor_info = ""
        if mac.vendor_name:
            vendor_info = f" ({mac.vendor_name})"
        elif mac.vendor_oui:
            vendor_info = f" (OUI: {mac.vendor_oui})"

        vlan_info = f" VLAN {vlan_id}" if vlan_id else ""

        message = (
            f"Nuovo MAC {mac.mac_address}{vendor_info} rilevato su "
            f"{switch.hostname} porta {port.port_name}{vlan_info}"
        )

        alert = Alert(
            alert_type="new_mac",
            mac_id=mac.id,
            switch_id=switch.id,
            port_id=port.id,
            message=message,
            severity="info",
            is_read=False,
            is_notified=False,
            created_at=datetime.utcnow(),
        )

        self.db.add(alert)
        self.db.flush()  # Get the alert ID without committing

        logger.info(f"Created new_mac alert for {mac.mac_address} on {switch.hostname}:{port.port_name}")

        return alert

    def create_mac_move_alert(
        self,
        mac: MacAddress,
        new_switch: Switch,
        new_port: Port,
        old_switch: Switch,
        old_port: Port,
        vlan_id: Optional[int] = None
    ) -> Alert:
        """
        Create an alert for a MAC address movement.

        Args:
            mac: The MAC address that moved
            new_switch: The new switch
            new_port: The new port
            old_switch: The previous switch
            old_port: The previous port
            vlan_id: Optional VLAN ID

        Returns:
            The created Alert object
        """
        message = (
            f"MAC {mac.mac_address} spostato da "
            f"{old_switch.hostname}:{old_port.port_name} a "
            f"{new_switch.hostname}:{new_port.port_name}"
        )

        alert = Alert(
            alert_type="mac_move",
            mac_id=mac.id,
            switch_id=new_switch.id,
            port_id=new_port.id,
            message=message,
            severity="warning",
            is_read=False,
            is_notified=False,
            created_at=datetime.utcnow(),
        )

        self.db.add(alert)
        self.db.flush()

        logger.info(f"Created mac_move alert for {mac.mac_address}")

        return alert

    def create_mac_disappear_alert(
        self,
        mac: MacAddress,
        last_switch: Switch,
        last_port: Port,
        hours_missing: int = 24
    ) -> Alert:
        """
        Create an alert for a disappeared MAC address.

        Args:
            mac: The MAC address that disappeared
            last_switch: The last known switch
            last_port: The last known port
            hours_missing: How many hours the MAC has been missing

        Returns:
            The created Alert object
        """
        message = (
            f"MAC {mac.mac_address} non visibile da {hours_missing}h "
            f"(ultima posizione: {last_switch.hostname}:{last_port.port_name})"
        )

        alert = Alert(
            alert_type="mac_disappear",
            mac_id=mac.id,
            switch_id=last_switch.id,
            port_id=last_port.id,
            message=message,
            severity="info",
            is_read=False,
            is_notified=False,
            created_at=datetime.utcnow(),
        )

        self.db.add(alert)
        self.db.flush()

        logger.info(f"Created mac_disappear alert for {mac.mac_address}")

        return alert

    def create_multiple_mac_alert(
        self,
        switch: Switch,
        port: Port,
        mac_count: int
    ) -> Alert:
        """
        Create an alert when a port has multiple MACs (>1).

        Args:
            switch: The switch with the port
            port: The port with multiple MACs
            mac_count: Current number of MACs on the port

        Returns:
            The created Alert object
        """
        message = (
            f"Porta {port.port_name} su {switch.hostname} ha {mac_count} MAC collegati. "
            f"Possibile uplink non mappato o hub/switch non gestito."
        )

        alert = Alert(
            alert_type="multiple_mac",
            switch_id=switch.id,
            port_id=port.id,
            message=message,
            severity="info",
            is_read=False,
            is_notified=False,
            created_at=datetime.utcnow(),
        )

        self.db.add(alert)
        self.db.flush()

        logger.info(f"Created multiple_mac alert for {switch.hostname}:{port.port_name} ({mac_count} MACs)")

        return alert

    def create_port_threshold_alert(
        self,
        switch: Switch,
        port: Port,
        mac_count: int,
        threshold: int = 10
    ) -> Alert:
        """
        Create an alert when a port has too many MACs (possible unmapped uplink).

        Args:
            switch: The switch with the problematic port
            port: The port with many MACs
            mac_count: Current number of MACs on the port
            threshold: The threshold that was exceeded

        Returns:
            The created Alert object
        """
        message = (
            f"Porta {port.port_name} su {switch.hostname} ha {mac_count} MAC collegati "
            f"(soglia: {threshold}). Possibile uplink non mappato."
        )

        alert = Alert(
            alert_type="port_threshold",
            switch_id=switch.id,
            port_id=port.id,
            message=message,
            severity="warning",
            is_read=False,
            is_notified=False,
            created_at=datetime.utcnow(),
        )

        self.db.add(alert)
        self.db.flush()

        logger.info(f"Created port_threshold alert for {switch.hostname}:{port.port_name}")

        return alert

    def get_unread_count(self) -> int:
        """Get the count of unread alerts."""
        return self.db.query(Alert).filter(Alert.is_read == False).count()
