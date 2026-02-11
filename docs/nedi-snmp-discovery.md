# NeDi SNMP Discovery per Huawei - Documentazione Tecnica

## Overview

NeDi (Network Discovery) usa un approccio modulare per il discovery SNMP dei dispositivi di rete.
Per Huawei utilizza OID proprietari per ottenere la MAC table con supporto VLAN nativo.

---

## Architettura NeDi

### File Principali

| File | Funzione |
|------|----------|
| `/var/nedi/nedi.pl` | Script principale discovery |
| `/var/nedi/inc/libsnmp.pm` | Libreria SNMP con funzioni MAC table |
| `/var/nedi/inc/libdb.pm` | Interazione database |
| `/var/nedi/sysobj/*.def` | Definizioni dispositivi per OID |
| `/var/nedi/nedi.conf` | Configurazione SNMP/credenziali |

### Device Definitions (.def)

I file `.def` mappano il sysObjectID del dispositivo alle sue caratteristiche:

**Pattern nome:** `1.3.6.1.4.1.<enterprise>.<product>.def`

**Huawei Enterprise OID:** `1.3.6.1.4.1.2011`

---

## Configurazione SNMP (nedi.conf)

```perl
# SNMPv3 con auth+priv
comm    <snmpv3_user>    sha    <auth_password>    aes    <priv_password>
# SNMPv2c fallback
comm    <your_community_string>
comm    public

# Timeout e retry
timeout    10    5
```

---

## Discovery Flow

### 1. Identificazione Dispositivo

```
Identify($ip) →
  1. Prova SNMP communities in ordine
  2. Query sysObjectID (1.3.6.1.2.1.1.2.0)
  3. Carica .def file corrispondente
  4. Estrae: sysName, sysLocation, sysContact
```

### 2. MAC Table Collection

NeDi supporta diversi metodi (campo `Bridge` nel .def):

| Metodo | Descrizione |
|--------|-------------|
| `normal` | Standard Bridge-MIB |
| `normalX` | Bridge-MIB con index translation |
| `qbri` | Q-Bridge MIB (802.1Q) |
| `VLX` | VLAN-indexed communities |
| **`huaweiV`** | **Huawei proprietary con VLAN** |

---

## Huawei SNMP Discovery - Dettaglio

### OID Proprietario Huawei FDB

```
hwDynFdbPort = 1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4
```

### Struttura OID Response

```
hwDynFdbPort.<MAC_6_bytes>.<VLAN>.<type>.<flags> = ifIndex
```

**Esempio:**
```
1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4.0.28.115.195.11.65.100.1.0 = 10
                                    └─────MAC─────┘ └VL┘└─┘└─┘
```

Dove:
- Bytes 15-20: MAC address (6 ottetti decimali)
- Byte 21: VLAN ID
- Bytes 22-23: type e flags
- Value: ifIndex della porta

### Codice NeDi (libsnmp.pm)

```perl
sub FwdBridge {
    my ($na) = @_;

    # OID Huawei FDB
    my $hwfdbO = "1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4";

    # Se device ha Bridge=huaweiV nel .def
    if( $misc::sysobj{$main::dev{$na}{so}}{bf} eq "huaweiV" ){

        # Walk della tabella Huawei
        my $r = $session->get_table(-baseoid => $hwfdbO);

        while( my($key, $val) = each(%{$r}) ) {
            my @parts = split(/\./, $key);

            # Estrazione MAC (bytes 15-20)
            $mc = sprintf "%02x%02x%02x%02x%02x%02x",
                  $parts[15], $parts[16], $parts[17],
                  $parts[18], $parts[19], $parts[20];

            # VLAN ID (byte 21)
            my $vlid = $parts[21];

            # ifIndex dalla response
            $ifx = $val;

            # Salva nel database
            $nod{$na}{$mcvl}{if} = $po;      # porta
            $nod{$na}{$mcvl}{vl} = $vlid;    # vlan
        }

        db::WriteNod(\%nod);
    }
}
```

---

## Altri OID Huawei Importanti

### VLAN Names
```
hwVlanMIBTable = 1.3.6.1.4.1.2011.5.25.42.3.1.1.1.1.2
```

### Port VLAN Assignment (PVID)
```
hwL2IfPVID = 1.3.6.1.4.1.2011.5.25.42.1.1.1.3.1.4
```

### Interfaces
```
ifName = 1.3.6.1.2.1.31.1.1.1.1         # Nome interfaccia
ifAlias = 1.3.6.1.2.1.31.1.1.1.18       # Descrizione
ifDuplex = 1.3.6.1.2.1.10.7.2.1.19      # Duplex status
```

### Discovery Protocol (LLDP)
```
Dispro = LLDPXN  # LLDP standard + estensioni
```

### Serial Number
```
entPhysicalSerialNum = 1.3.6.1.2.1.47.1.1.1.1.11.<entity_index>
# Per S6720: entity_index = 67108867
# Per altri: entity_index = 16777216
```

---

## Esempio Device Definition Huawei

**File:** `1.3.6.1.4.1.2011.2.23.545.def` (S6720-32X-LI)

```ini
# Main
SNMPv   2HC                              # SNMP v2c con High Counters
Type    S6720-32X-LI-32S-AC
OS      HuaweiVRP
Icon    s3m
Size    1
Uptime  U
Bridge  huaweiV                          # ← USA hwDynFdbPort!
ArpND   oldphy
Dispro  LLDPXN

# Serial
Serial  1.3.6.1.2.1.47.1.1.1.1.11.67108867

# Interfaces
IFname  1.3.6.1.2.1.31.1.1.1.1
IFalia  1.3.6.1.2.1.31.1.1.1.18
IFvlan  1.3.6.1.4.1.2011.5.25.42.1.1.1.3.1.4
IFdupl  1.3.6.1.2.1.10.7.2.1.19
Halfdp  2
Fulldp  3

# Modules (Entity-MIB)
Moslot  1.3.6.1.2.1.47.1.1.1.1.7
Moclas  1.3.6.1.2.1.47.1.1.1.1.5
Movalu  3|6|10
Modesc  1.3.6.1.2.1.47.1.1.1.1.2
Modhw   1.3.6.1.2.1.47.1.1.1.1.8
Modfw   1.3.6.1.2.1.47.1.1.1.1.9
Modsw   1.3.6.1.2.1.47.1.1.1.1.10
Modser  1.3.6.1.2.1.47.1.1.1.1.11
Momodl  1.3.6.1.2.1.47.1.1.1.1.13

# RRD Graphing
CPUutl  1.3.6.1.4.1.2011.6.3.4.1.2.0.0.0
MemCPU  1.3.6.1.4.1.2011.6.3.5.1.1.2.0.0.0
```

---

## Database NeDi - Schema Rilevante

### Tabella `nodes` (MAC addresses)

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| mac | varchar(16) | MAC address (hex) |
| oui | varchar(32) | Vendor (IEEE lookup) |
| firstseen | int | Timestamp primo avvistamento |
| lastseen | int | Timestamp ultimo avvistamento |
| device | varchar(64) | Nome switch |
| ifname | varchar(32) | Nome porta |
| vlanid | smallint | VLAN ID |
| metric | varchar(10) | Speed/duplex codificato |
| ifupdate | int | Ultimo aggiornamento porta |
| ifchanges | int | Contatore cambi porta |

### Tabella `devices` (Switches)

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| device | varchar(64) | Nome dispositivo |
| devip | int | IP (decimal) |
| serial | varchar(32) | Serial number |
| type | varchar(64) | Modello |
| sysobjid | varchar(255) | sysObjectID |
| devos | varchar(16) | OS (HuaweiVRP, IOS, etc) |
| readcomm | varchar(32) | SNMP community |
| snmpversion | tinyint | Versione SNMP |
| totmac | int | Totale MAC visti |

---

## Implementazione per Mac-Tracker

### Strategia Consigliata

1. **Usare stesso OID Huawei di NeDi:**
   ```python
   HUAWEI_FDB_OID = "1.3.6.1.4.1.2011.5.25.42.2.1.3.1.4"
   ```

2. **Parsing identico:**
   ```python
   def parse_huawei_fdb(oid, value):
       parts = oid.split('.')
       mac = ':'.join(f'{int(parts[i]):02x}' for i in range(15, 21))
       vlan = int(parts[21])
       ifindex = int(value)
       return mac, vlan, ifindex
   ```

3. **Fallback Bridge-MIB standard per altri vendor**

### OID Standard (Cisco, Extreme, etc)

```python
# Bridge-MIB (RFC 1493)
FWD_MAC = "1.3.6.1.2.1.17.4.3.1.1"     # MAC entries
FWD_PORT = "1.3.6.1.2.1.17.4.3.1.2"    # Port mappings
FWD_IDX = "1.3.6.1.2.1.17.1.4.1.2"     # Port-to-ifIndex

# Q-Bridge MIB (802.1Q)
QBRIDGE_FDB = "1.3.6.1.2.1.17.7.1.2.2.1.2"
```

---

## Riferimenti

- NeDi Documentation: https://www.nedi.ch
- Huawei MIB Browser: Device Manager / MIB Browser
- IEEE OUI Database: https://standards-oui.ieee.org/
