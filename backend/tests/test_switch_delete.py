"""
Test suite per l'eliminazione degli switch.
Verifica che DELETE /api/switches/{id} funzioni correttamente
e che tutti i dati correlati vengano gestiti (cascade delete).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.db.models import (
    Switch,
    SwitchGroup,
    Port,
    MacAddress,
    MacLocation,
    MacHistory,
    TopologyLink,
    Alert,
    DiscoveryLog
)


# Setup test database in memory
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Database session fixture."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_switch(db_session):
    """Create a sample switch for testing."""
    switch = Switch(
        hostname="test-switch-01",
        ip_address="192.168.1.1",
        device_type="huawei",
        snmp_community="public",
        location="Test Location",
        is_active=True
    )
    db_session.add(switch)
    db_session.commit()
    db_session.refresh(switch)
    return switch


@pytest.fixture
def switch_with_ports(db_session):
    """Create a switch with associated ports."""
    switch = Switch(
        hostname="test-switch-ports",
        ip_address="192.168.1.2",
        device_type="huawei",
        is_active=True
    )
    db_session.add(switch)
    db_session.commit()
    db_session.refresh(switch)

    # Add 3 ports
    for i in range(3):
        port = Port(
            switch_id=switch.id,
            port_name=f"GE1/0/{i}",
            port_index=i,
            port_type="access"
        )
        db_session.add(port)

    db_session.commit()
    return switch


@pytest.fixture
def switch_with_mac_locations(db_session):
    """Create a switch with ports and MAC locations."""
    switch = Switch(
        hostname="test-switch-macs",
        ip_address="192.168.1.3",
        device_type="huawei",
        is_active=True
    )
    db_session.add(switch)
    db_session.commit()
    db_session.refresh(switch)

    # Add a port
    port = Port(
        switch_id=switch.id,
        port_name="GE1/0/1",
        port_index=1,
        port_type="access"
    )
    db_session.add(port)
    db_session.commit()
    db_session.refresh(port)

    # Add a MAC address
    mac = MacAddress(
        mac_address="AA:BB:CC:DD:EE:FF",
        vendor_name="Test Vendor"
    )
    db_session.add(mac)
    db_session.commit()
    db_session.refresh(mac)

    # Add MAC location
    location = MacLocation(
        mac_id=mac.id,
        switch_id=switch.id,
        port_id=port.id,
        vlan_id=100,
        is_current=True
    )
    db_session.add(location)

    # Add MAC history
    history = MacHistory(
        mac_id=mac.id,
        switch_id=switch.id,
        port_id=port.id,
        vlan_id=100,
        event_type="new"
    )
    db_session.add(history)

    db_session.commit()
    return {"switch": switch, "port": port, "mac": mac}


@pytest.fixture
def two_switches_with_topology(db_session):
    """Create two switches linked by topology."""
    switch1 = Switch(
        hostname="test-switch-topo-1",
        ip_address="192.168.1.10",
        device_type="huawei",
        is_active=True
    )
    switch2 = Switch(
        hostname="test-switch-topo-2",
        ip_address="192.168.1.11",
        device_type="huawei",
        is_active=True
    )
    db_session.add_all([switch1, switch2])
    db_session.commit()
    db_session.refresh(switch1)
    db_session.refresh(switch2)

    # Add ports
    port1 = Port(switch_id=switch1.id, port_name="GE1/0/24", port_index=24, is_uplink=True)
    port2 = Port(switch_id=switch2.id, port_name="GE1/0/24", port_index=24, is_uplink=True)
    db_session.add_all([port1, port2])
    db_session.commit()
    db_session.refresh(port1)
    db_session.refresh(port2)

    # Add topology link
    link = TopologyLink(
        local_switch_id=switch1.id,
        local_port_id=port1.id,
        remote_switch_id=switch2.id,
        remote_port_id=port2.id,
        protocol="lldp"
    )
    db_session.add(link)
    db_session.commit()

    return {"switch1": switch1, "switch2": switch2, "port1": port1, "port2": port2}


@pytest.fixture
def switch_with_alerts(db_session):
    """Create a switch with associated alerts."""
    switch = Switch(
        hostname="test-switch-alerts",
        ip_address="192.168.1.20",
        device_type="huawei",
        is_active=True
    )
    db_session.add(switch)
    db_session.commit()
    db_session.refresh(switch)

    # Add alerts
    for i, alert_type in enumerate(["new_mac", "mac_move", "port_threshold"]):
        alert = Alert(
            alert_type=alert_type,
            switch_id=switch.id,
            message=f"Test alert {i}",
            severity="info"
        )
        db_session.add(alert)

    db_session.commit()
    return switch


# ============================================================================
# TEST: Eliminazione switch esistente con successo
# ============================================================================

class TestDeleteSwitchSuccess:
    """Test eliminazione switch esistente."""

    def test_delete_existing_switch_returns_204(self, client, sample_switch):
        """Verifica che DELETE restituisca 204 No Content."""
        response = client.delete(f"/api/switches/{sample_switch.id}")
        assert response.status_code == 204

    def test_delete_existing_switch_removes_from_db(self, client, sample_switch, db_session):
        """Verifica che lo switch venga rimosso dal database."""
        switch_id = sample_switch.id

        # Verifica che esista prima
        switch_before = db_session.query(Switch).filter(Switch.id == switch_id).first()
        assert switch_before is not None

        # Elimina
        client.delete(f"/api/switches/{switch_id}")

        # Verifica che non esista piu
        db_session.expire_all()
        switch_after = db_session.query(Switch).filter(Switch.id == switch_id).first()
        assert switch_after is None

    def test_get_deleted_switch_returns_404(self, client, sample_switch):
        """Verifica che GET su switch eliminato restituisca 404."""
        switch_id = sample_switch.id

        # Elimina
        client.delete(f"/api/switches/{switch_id}")

        # Prova a recuperarlo
        response = client.get(f"/api/switches/{switch_id}")
        assert response.status_code == 404


# ============================================================================
# TEST: Errore 404 per switch inesistente
# ============================================================================

class TestDeleteSwitchNotFound:
    """Test errore 404 per switch inesistente."""

    def test_delete_nonexistent_switch_returns_404(self, client):
        """Verifica che DELETE su ID inesistente restituisca 404."""
        response = client.delete("/api/switches/99999")
        assert response.status_code == 404

    def test_delete_nonexistent_switch_error_message(self, client):
        """Verifica il messaggio di errore appropriato."""
        response = client.delete("/api/switches/99999")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "non trovato" in data["detail"].lower() or "not found" in data["detail"].lower()

    def test_delete_zero_id_returns_404(self, client):
        """Verifica che ID 0 restituisca 404."""
        response = client.delete("/api/switches/0")
        # Potrebbe essere 404 o 422 a seconda della validazione
        assert response.status_code in [404, 422]


# ============================================================================
# TEST: Cascade delete porte associate
# ============================================================================

class TestDeleteSwitchCascadePorts:
    """Test cascade delete delle porte."""

    def test_delete_switch_removes_associated_ports(self, client, switch_with_ports, db_session):
        """Verifica che le porte vengano eliminate con lo switch."""
        switch_id = switch_with_ports.id

        # Verifica che ci siano porte prima
        ports_before = db_session.query(Port).filter(Port.switch_id == switch_id).count()
        assert ports_before == 3

        # Elimina lo switch
        response = client.delete(f"/api/switches/{switch_id}")
        assert response.status_code == 204

        # Verifica che le porte siano state eliminate
        db_session.expire_all()
        ports_after = db_session.query(Port).filter(Port.switch_id == switch_id).count()
        assert ports_after == 0

    def test_no_orphan_ports_after_delete(self, client, switch_with_ports, db_session):
        """Verifica che non ci siano porte orfane."""
        switch_id = switch_with_ports.id

        # Conta porte totali prima
        total_ports_before = db_session.query(Port).count()
        assert total_ports_before == 3

        # Elimina lo switch
        client.delete(f"/api/switches/{switch_id}")

        # Verifica porte totali dopo
        db_session.expire_all()
        total_ports_after = db_session.query(Port).count()
        assert total_ports_after == 0


# ============================================================================
# TEST: Gestione MAC locations durante eliminazione
# ============================================================================

class TestDeleteSwitchMacLocations:
    """Test gestione MAC locations durante eliminazione."""

    def test_delete_switch_removes_mac_locations(self, client, switch_with_mac_locations, db_session):
        """Verifica che le mac_locations vengano eliminate."""
        switch = switch_with_mac_locations["switch"]

        # Verifica che ci siano locations prima
        locations_before = db_session.query(MacLocation).filter(
            MacLocation.switch_id == switch.id
        ).count()
        assert locations_before == 1

        # Elimina lo switch
        response = client.delete(f"/api/switches/{switch.id}")
        assert response.status_code == 204

        # Verifica che le locations siano state eliminate
        db_session.expire_all()
        locations_after = db_session.query(MacLocation).filter(
            MacLocation.switch_id == switch.id
        ).count()
        assert locations_after == 0

    def test_mac_address_preserved_after_switch_delete(self, client, switch_with_mac_locations, db_session):
        """Verifica che i record mac_addresses NON vengano eliminati."""
        mac = switch_with_mac_locations["mac"]
        switch = switch_with_mac_locations["switch"]
        mac_id = mac.id

        # Elimina lo switch
        client.delete(f"/api/switches/{switch.id}")

        # Verifica che il MAC address esista ancora
        db_session.expire_all()
        mac_after = db_session.query(MacAddress).filter(MacAddress.id == mac_id).first()
        assert mac_after is not None
        assert mac_after.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_mac_history_handling(self, client, switch_with_mac_locations, db_session):
        """Verifica la gestione di mac_history (i dati storici non hanno FK cascade)."""
        mac = switch_with_mac_locations["mac"]
        switch = switch_with_mac_locations["switch"]

        # Verifica che ci sia history prima
        history_before = db_session.query(MacHistory).filter(
            MacHistory.mac_id == mac.id
        ).count()
        assert history_before == 1

        # Elimina lo switch
        client.delete(f"/api/switches/{switch.id}")

        # mac_history ha switch_id come Integer semplice, non FK con CASCADE
        # quindi i record dovrebbero rimanere (dati storici)
        db_session.expire_all()
        history_after = db_session.query(MacHistory).filter(
            MacHistory.mac_id == mac.id
        ).count()
        # I dati storici rimangono (switch_id non ha ondelete=CASCADE)
        assert history_after == 1


# ============================================================================
# TEST: Cleanup topology_links
# ============================================================================

class TestDeleteSwitchTopologyLinks:
    """Test cleanup dei link topologici."""

    def test_delete_switch_removes_topology_links_as_local(self, client, two_switches_with_topology, db_session):
        """Verifica che i link con local_switch_id vengano eliminati."""
        switch1 = two_switches_with_topology["switch1"]

        # Verifica che ci sia un link prima
        links_before = db_session.query(TopologyLink).filter(
            TopologyLink.local_switch_id == switch1.id
        ).count()
        assert links_before == 1

        # Elimina switch1
        response = client.delete(f"/api/switches/{switch1.id}")
        assert response.status_code == 204

        # Verifica che il link sia stato eliminato
        db_session.expire_all()
        links_after = db_session.query(TopologyLink).filter(
            TopologyLink.local_switch_id == switch1.id
        ).count()
        assert links_after == 0

    def test_delete_switch_removes_topology_links_as_remote(self, client, two_switches_with_topology, db_session):
        """Verifica che i link con remote_switch_id vengano eliminati."""
        switch2 = two_switches_with_topology["switch2"]

        # Verifica che ci sia un link dove switch2 e' remote
        links_before = db_session.query(TopologyLink).filter(
            TopologyLink.remote_switch_id == switch2.id
        ).count()
        assert links_before == 1

        # Elimina switch2
        response = client.delete(f"/api/switches/{switch2.id}")
        assert response.status_code == 204

        # Verifica che il link sia stato eliminato
        db_session.expire_all()
        links_after = db_session.query(TopologyLink).filter(
            TopologyLink.remote_switch_id == switch2.id
        ).count()
        assert links_after == 0

    def test_other_switch_preserved_after_delete(self, client, two_switches_with_topology, db_session):
        """Verifica che l'altro switch rimanga intatto."""
        switch1 = two_switches_with_topology["switch1"]
        switch2 = two_switches_with_topology["switch2"]
        switch2_id = switch2.id

        # Elimina switch1
        client.delete(f"/api/switches/{switch1.id}")

        # Verifica che switch2 esista ancora
        db_session.expire_all()
        switch2_after = db_session.query(Switch).filter(Switch.id == switch2_id).first()
        assert switch2_after is not None
        assert switch2_after.hostname == "test-switch-topo-2"


# ============================================================================
# TEST: Cleanup alert associati
# ============================================================================

class TestDeleteSwitchAlerts:
    """Test cleanup degli alert associati."""

    def test_delete_switch_handles_alerts(self, client, switch_with_alerts, db_session):
        """Verifica che gli alert vengano gestiti (SET NULL su switch_id)."""
        switch = switch_with_alerts
        switch_id = switch.id

        # Verifica che ci siano alert prima
        alerts_before = db_session.query(Alert).filter(Alert.switch_id == switch_id).count()
        assert alerts_before == 3

        # Elimina lo switch
        response = client.delete(f"/api/switches/{switch_id}")
        assert response.status_code == 204

        # Gli alert hanno ondelete="SET NULL", quindi dovrebbero rimanere con switch_id = NULL
        db_session.expire_all()

        # Verifica che non ci siano piu alert con questo switch_id
        alerts_with_switch = db_session.query(Alert).filter(Alert.switch_id == switch_id).count()
        assert alerts_with_switch == 0

        # Gli alert dovrebbero esistere ancora ma con switch_id = NULL
        all_alerts = db_session.query(Alert).filter(Alert.switch_id.is_(None)).count()
        assert all_alerts >= 3  # Potrebbero essercene altri da test precedenti

    def test_no_orphan_alerts_referencing_deleted_switch(self, client, switch_with_alerts, db_session):
        """Verifica integrita referenziale - nessun alert con switch_id invalido."""
        switch = switch_with_alerts
        switch_id = switch.id

        # Elimina lo switch
        client.delete(f"/api/switches/{switch_id}")

        db_session.expire_all()

        # Verifica che tutti gli alert abbiano switch_id NULL o valido
        all_alerts = db_session.query(Alert).all()
        for alert in all_alerts:
            if alert.switch_id is not None:
                # Se c'e' uno switch_id, deve esistere
                switch_exists = db_session.query(Switch).filter(
                    Switch.id == alert.switch_id
                ).first()
                assert switch_exists is not None, f"Alert {alert.id} ha switch_id orfano {alert.switch_id}"


# ============================================================================
# TEST: Discovery logs handling
# ============================================================================

class TestDeleteSwitchDiscoveryLogs:
    """Test gestione discovery logs durante eliminazione."""

    def test_delete_switch_handles_discovery_logs(self, client, sample_switch, db_session):
        """Verifica che i discovery_logs vengano gestiti."""
        switch = sample_switch

        # Aggiungi un discovery log
        log = DiscoveryLog(
            switch_id=switch.id,
            discovery_type="snmp",
            status="success",
            mac_count=10
        )
        db_session.add(log)
        db_session.commit()

        # Elimina lo switch
        response = client.delete(f"/api/switches/{switch.id}")
        assert response.status_code == 204

        # discovery_logs ha ondelete="SET NULL", verifica
        db_session.expire_all()
        logs = db_session.query(DiscoveryLog).filter(
            DiscoveryLog.switch_id == switch.id
        ).count()
        assert logs == 0  # Nessun log dovrebbe avere questo switch_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
