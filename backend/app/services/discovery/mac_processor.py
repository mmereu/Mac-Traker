"""MAC Address Processor for vendor lookup and classification."""
import logging
import httpx
from typing import Optional, Dict, Tuple

from sqlalchemy.orm import Session

from app.db.models import MacAddress, OuiVendor
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Cache for API lookups to reduce external calls
_vendor_api_cache: Dict[str, Optional[str]] = {}

# Built-in OUI database for common vendors
COMMON_OUI = {
    # === VIRTUAL MACHINES ===
    "000C29": ("VMware, Inc.", "virtual_machine"),
    "005056": ("VMware, Inc.", "virtual_machine"),
    "000569": ("VMware, Inc.", "virtual_machine"),
    "001C42": ("Parallels, Inc.", "virtual_machine"),
    "080027": ("PCS Systemtechnik GmbH", "virtual_machine"),  # VirtualBox

    # === NETWORK EQUIPMENT ===
    # Huawei
    "482C6A": ("Huawei Technologies Co.,Ltd", "network"),
    "ACE2D3": ("Huawei Technologies Co.,Ltd", "network"),
    "A4BA76": ("HUAWEI TECHNOLOGIES CO.,LTD", "network"),
    "00E00E": ("HUAWEI TECHNOLOGIES CO.,LTD", "network"),
    "00E60E": ("Extreme Networks Headquarters", "access_point"),
    # Extreme Networks (Access Points)
    "00186E": ("Extreme Networks", "access_point"),
    "00012E": ("Extreme Networks", "access_point"),
    "5C0E8B": ("Extreme Networks", "access_point"),
    "B4C799": ("Extreme Networks", "access_point"),
    # Aruba (Access Points)
    "000B86": ("Aruba Networks", "access_point"),
    "24DE9A": ("Aruba Networks", "access_point"),
    "6CFDB9": ("Aruba Networks", "access_point"),
    "9C1C12": ("Aruba Networks", "access_point"),
    "ACA31E": ("Aruba, HPE", "access_point"),
    "D8C7C8": ("Aruba Networks", "access_point"),
    "20A6CD": ("Aruba Networks", "access_point"),
    "94B40F": ("Aruba Networks", "access_point"),
    # Cisco (Meraki, APs)
    "0018BA": ("Cisco-Linksys/Meraki", "access_point"),
    "0024A5": ("Cisco Meraki", "access_point"),
    "88155F": ("Cisco Meraki", "access_point"),
    # Ubiquiti
    "00275D": ("Ubiquiti Networks", "access_point"),
    "0418D6": ("Ubiquiti Inc", "access_point"),
    "24A43C": ("Ubiquiti Inc", "access_point"),
    "44D9E7": ("Ubiquiti Inc", "access_point"),
    "68D79A": ("Ubiquiti Inc", "access_point"),
    "788A20": ("Ubiquiti Inc", "access_point"),
    "802AA8": ("Ubiquiti Inc", "access_point"),
    "B4FBE4": ("Ubiquiti Inc", "access_point"),
    "DC9FDB": ("Ubiquiti Inc", "access_point"),
    "E063DA": ("Ubiquiti Inc", "access_point"),
    "F09FC2": ("Ubiquiti Inc", "access_point"),
    "FCECDA": ("Ubiquiti Inc", "access_point"),
    # Ruckus
    "C4108A": ("Ruckus Wireless", "access_point"),
    "58B633": ("Ruckus Wireless", "access_point"),
    "4C1D96": ("Ruckus Wireless", "access_point"),
    "842B2B": ("Ruckus Wireless", "access_point"),
    # Other network
    "001E58": ("D-Link Corporation", "network"),
    "00179A": ("D-Link Corporation", "network"),
    "C83A35": ("Shenzhen Tenda Technology", "network"),
    "001018": ("Broadcom", "network"),

    # === IP PHONES ===
    # Cisco
    "00070E": ("Cisco IP Phone", "ip_phone"),
    "000FEE": ("Cisco IP Phone", "ip_phone"),
    "001121": ("Cisco IP Phone", "ip_phone"),
    "001A2F": ("Cisco IP Phone", "ip_phone"),
    "001BD4": ("Cisco IP Phone", "ip_phone"),
    "00226B": ("Cisco IP Phone", "ip_phone"),
    "002490": ("Cisco IP Phone", "ip_phone"),
    "002566": ("Cisco IP Phone", "ip_phone"),
    "0026CB": ("Cisco IP Phone", "ip_phone"),
    "10BDEC": ("Cisco IP Phone", "ip_phone"),
    "1CE6C7": ("Cisco IP Phone", "ip_phone"),
    "442B03": ("Cisco IP Phone", "ip_phone"),
    "503DE5": ("Cisco IP Phone", "ip_phone"),
    "5CF9DD": ("Cisco IP Phone", "ip_phone"),
    "6400F1": ("Cisco IP Phone", "ip_phone"),
    "6C416A": ("Cisco IP Phone", "ip_phone"),
    "7C1E52": ("Cisco IP Phone", "ip_phone"),
    "A8A666": ("Cisco IP Phone", "ip_phone"),
    "C4649B": ("Cisco IP Phone", "ip_phone"),
    "DCF898": ("Cisco IP Phone", "ip_phone"),
    "F8B7E2": ("Cisco IP Phone", "ip_phone"),
    # Polycom
    "0004F2": ("Polycom IP Phone", "ip_phone"),
    "64167F": ("Polycom IP Phone", "ip_phone"),
    # Yealink
    "001565": ("Yealink IP Phone", "ip_phone"),
    "24CF11": ("Yealink IP Phone", "ip_phone"),
    "309E65": ("Yealink IP Phone", "ip_phone"),
    "805E0C": ("Yealink IP Phone", "ip_phone"),
    "805EC0": ("Yealink IP Phone", "ip_phone"),
    # Grandstream
    "000B82": ("Grandstream IP Phone", "ip_phone"),
    # Avaya
    "00040D": ("Avaya IP Phone", "ip_phone"),
    "001B4F": ("Avaya IP Phone", "ip_phone"),
    "3CE5A6": ("Avaya IP Phone", "ip_phone"),
    "70521C": ("Avaya IP Phone", "ip_phone"),
    "7C57BC": ("Avaya IP Phone", "ip_phone"),
    # Snom
    "000413": ("Snom IP Phone", "ip_phone"),
    # Mitel
    "08000F": ("Mitel IP Phone", "ip_phone"),

    # === HANDHELD / MOBILE DEVICES ===
    # Zebra (palmari industriali)
    "0023A7": ("Zebra Technologies", "handheld"),
    "00A0F8": ("Zebra Technologies", "handheld"),
    "F8DC7A": ("Zebra Technologies", "handheld"),
    "8CBEBE": ("Zebra Technologies", "handheld"),
    "00176B": ("Zebra Technologies", "handheld"),
    "001FBA": ("Zebra Technologies", "handheld"),
    "14A7D0": ("Zebra Technologies", "handheld"),
    "AC3FA4": ("Zebra Technologies", "handheld"),
    "BCC1D2": ("Zebra Technologies", "handheld"),
    "C4F57C": ("Zebra Technologies", "handheld"),
    # Honeywell (palmari industriali)
    "00176D": ("Honeywell", "handheld"),
    "002686": ("Honeywell", "handheld"),
    "008098": ("Honeywell", "handheld"),
    "00A0D1": ("Honeywell", "handheld"),
    "0CB5DE": ("Honeywell", "handheld"),
    "2C5A8D": ("Honeywell", "handheld"),
    "5CFCFC": ("Honeywell", "handheld"),
    "94E6F7": ("Honeywell", "handheld"),
    # Datalogic (palmari industriali)
    "002104": ("Datalogic", "handheld"),
    "001E7D": ("Datalogic", "handheld"),
    "0002A5": ("Datalogic", "handheld"),
    "000F1F": ("Datalogic", "handheld"),
    # Symbol/Motorola (palmari)
    "00A0F8": ("Symbol Technologies", "handheld"),
    "001373": ("Symbol Technologies", "handheld"),
    "0015B9": ("Symbol Technologies", "handheld"),
    "002275": ("Symbol Technologies", "handheld"),
    "0026AB": ("Symbol Technologies", "handheld"),
    "00A027": ("Symbol Technologies", "handheld"),
    # Intermec
    "000B91": ("Intermec Technologies", "handheld"),
    "00309B": ("Intermec Technologies", "handheld"),
    "001F6B": ("Intermec Technologies", "handheld"),
    # CipherLab
    "00D01E": ("CipherLab Co., Ltd.", "handheld"),
    "9027E4": ("CipherLab Co., Ltd.", "handheld"),
    # Unitech
    "000F06": ("Unitech Electronics", "handheld"),
    # SIMCOM (moduli 4G/LTE nei palmari Datalogic/altri)
    "3095E3": ("SIMCOM (4G Module in Handheld)", "handheld"),
    "861286": ("SIMCOM LIMITED", "handheld"),
    "FCDB96": ("SIMCOM LIMITED", "handheld"),
    # Urovo (palmari industriali)
    "B4293D": ("Urovo Technology", "handheld"),

    # === MOBILE DEVICES (smartphone/tablet) ===
    # Apple
    "7C5CF8": ("Apple, Inc.", "mobile"),
    "A4D1D2": ("Apple, Inc.", "mobile"),
    "DC2B2A": ("Apple, Inc.", "mobile"),
    "ACBC32": ("Apple, Inc.", "mobile"),
    "5855CA": ("Apple, Inc.", "mobile"),
    "38C986": ("Apple, Inc.", "mobile"),
    "847BEB": ("Apple, Inc.", "mobile"),
    "64A5C3": ("Apple, Inc.", "mobile"),
    "3C15C2": ("Apple, Inc.", "mobile"),
    "E0B9BA": ("Apple, Inc.", "mobile"),
    # Samsung
    "00166C": ("Samsung Electronics Co.,Ltd", "mobile"),
    "5C0A5B": ("Samsung Electronics", "mobile"),
    "0026E8": ("Samsung Electronics", "mobile"),
    "D0667B": ("Samsung Electronics", "mobile"),
    "E4E0C5": ("Samsung Electronics", "mobile"),
    "BC8CCD": ("Samsung Electronics", "mobile"),
    "F0EE10": ("Samsung Electronics", "mobile"),
    # Xiaomi
    "7CE2CA": ("Xiaomi Communications", "mobile"),
    "D4970B": ("Xiaomi Communications", "mobile"),
    "28E31F": ("Xiaomi Communications", "mobile"),
    "2C3311": ("Xiaomi Communications", "mobile"),
    "F8A45F": ("Xiaomi Communications", "mobile"),
    # Huawei Mobile
    "A8CE90": ("HUAWEI TECHNOLOGIES CO.,LTD", "mobile"),
    "688F84": ("HUAWEI TECHNOLOGIES CO.,LTD", "mobile"),
    "88CF98": ("HUAWEI TECHNOLOGIES CO.,LTD", "mobile"),
    "C4B8B4": ("HUAWEI TECHNOLOGIES CO.,LTD", "mobile"),
    # Others
    "E00ED7": ("Hon Hai Precision Ind. Co.,Ltd.", "mobile"),  # Foxconn

    # === WORKSTATIONS ===
    "001517": ("INTEL CORPORATE", "workstation"),
    "3C5731": ("ASUSTek COMPUTER INC.", "workstation"),
    "001CC0": ("Intel Corporate", "workstation"),
    "089E01": ("Quanta Computer Inc.", "workstation"),
    "0003FF": ("Microsoft Corporation", "workstation"),
    "001DD8": ("Microsoft Corporation", "workstation"),
    "78AC44": ("Hewlett Packard", "workstation"),
    "001E4F": ("Dell Inc.", "workstation"),
    "001422": ("Dell Inc.", "workstation"),
    "001C23": ("Dell Inc.", "workstation"),
    "001AA0": ("Dell Inc.", "workstation"),
    "F0921C": ("Dell Inc.", "workstation"),
    "001E0B": ("Hewlett Packard", "workstation"),
    "B42965": ("Lenovo", "workstation"),
    "B4293D": ("Lenovo", "workstation"),

    # === PRINTERS ===
    "9C8E99": ("Hewlett Packard", "printer"),
    "00237D": ("Hewlett Packard", "printer"),
    "002505": ("Hewlett Packard", "printer"),
    "001F29": ("Hewlett Packard", "printer"),

    # === IoT ===
    "DCA632": ("Raspberry Pi Foundation", "iot"),
    "B827EB": ("Raspberry Pi Foundation", "iot"),
    "DC2632": ("Raspberry Pi Trading Ltd", "iot"),
    "E45F01": ("Raspberry Pi Trading Ltd", "iot"),
    "2CCF67": ("Espressif Inc.", "iot"),
    "30AEA4": ("Espressif Inc.", "iot"),
    "A4CF12": ("Espressif Inc.", "iot"),
    "5C1BF4": ("Espressif Inc.", "iot"),

    # === BILANCE / POS / RETAIL ===
    "0040C1": ("Bizerba", "scale"),  # Bilance Bizerba
    "0010F3": ("Nexcom International", "pos"),
    "001040": ("Sharp Corporation", "pos"),
    "001020": ("Sharp Corporation", "pos"),
}


class MacProcessor:
    """Service for processing and enriching MAC address data."""

    def __init__(self, db: Session):
        self.db = db

    def get_vendor_info(self, mac_address: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get vendor information for a MAC address.

        Args:
            mac_address: MAC address in format AA:BB:CC:DD:EE:FF

        Returns:
            Tuple of (vendor_name, device_type) or (None, None) if not found
        """
        # Extract OUI (first 6 hex chars without separators)
        oui = mac_address.replace(":", "").replace("-", "").upper()[:6]

        # First try database
        oui_entry = self.db.query(OuiVendor).filter(
            OuiVendor.oui_prefix == oui
        ).first()

        if oui_entry:
            return oui_entry.vendor_name, oui_entry.device_type_hint

        # Fall back to built-in database
        if oui in COMMON_OUI:
            return COMMON_OUI[oui]

        # Finally, try external API
        api_vendor = self._lookup_vendor_api(mac_address)
        if api_vendor:
            # Save to database for future lookups
            self._save_oui_to_db(oui, api_vendor)
            device_type = self.classify_device(api_vendor)
            return api_vendor, device_type

        return None, None

    def _lookup_vendor_api(self, mac_address: str) -> Optional[str]:
        """
        Look up vendor via external API (macvendors.com).

        Args:
            mac_address: MAC address in format AA:BB:CC:DD:EE:FF

        Returns:
            Vendor name or None if not found
        """
        settings = get_settings()
        oui = mac_address.replace(":", "").replace("-", "").upper()[:6]

        # Check cache first
        if oui in _vendor_api_cache:
            logger.debug(f"Vendor API cache hit for OUI {oui}")
            return _vendor_api_cache[oui]

        api_url = settings.oui_fallback_api_url
        if not api_url:
            return None

        try:
            # Format MAC for API (AA:BB:CC format)
            mac_formatted = f"{oui[:2]}:{oui[2:4]}:{oui[4:6]}"
            url = f"{api_url}/{mac_formatted}"

            logger.info(f"Looking up vendor via API for OUI {oui}")

            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)

                if response.status_code == 200:
                    vendor = response.text.strip()
                    _vendor_api_cache[oui] = vendor
                    logger.info(f"API lookup success for OUI {oui}: {vendor}")
                    return vendor
                elif response.status_code == 404:
                    # Not found in API, cache negative result
                    _vendor_api_cache[oui] = None
                    logger.debug(f"OUI {oui} not found in vendor API")
                    return None
                else:
                    logger.warning(f"Vendor API returned status {response.status_code} for OUI {oui}")
                    return None

        except httpx.TimeoutException:
            logger.warning(f"Vendor API timeout for OUI {oui}")
            return None
        except Exception as e:
            logger.error(f"Vendor API error for OUI {oui}: {e}")
            return None

    def _save_oui_to_db(self, oui: str, vendor_name: str) -> None:
        """
        Save a discovered OUI to the database for future lookups.

        Args:
            oui: The 6-character OUI prefix (uppercase, no separators)
            vendor_name: The vendor name from API
        """
        try:
            existing = self.db.query(OuiVendor).filter(
                OuiVendor.oui_prefix == oui
            ).first()

            if not existing:
                new_oui = OuiVendor(
                    oui_prefix=oui,
                    vendor_name=vendor_name,
                    device_type_hint=self.classify_device(vendor_name)
                )
                self.db.add(new_oui)
                self.db.commit()
                logger.info(f"Saved OUI {oui} ({vendor_name}) to database")
        except Exception as e:
            logger.error(f"Failed to save OUI {oui} to database: {e}")
            self.db.rollback()

    def enrich_mac(self, mac: MacAddress) -> MacAddress:
        """
        Enrich a MAC address with vendor information.

        Args:
            mac: MacAddress model instance

        Returns:
            Updated MacAddress instance
        """
        if not mac.vendor_name:
            vendor_name, device_type = self.get_vendor_info(mac.mac_address)
            if vendor_name:
                mac.vendor_name = vendor_name
            if device_type:
                mac.device_type = device_type
            self.db.commit()

        return mac

    def classify_device(self, vendor_name: Optional[str]) -> str:
        """
        Classify device type based on vendor name.

        Args:
            vendor_name: The vendor name

        Returns:
            Device classification string
        """
        if not vendor_name:
            return "unknown"

        vendor_lower = vendor_name.lower()

        # Virtual Machines
        if any(x in vendor_lower for x in ["vmware", "virtualbox", "parallels", "hyper-v"]):
            return "virtual_machine"
        # Access Points
        elif any(x in vendor_lower for x in ["aruba", "ubiquiti", "ruckus", "meraki", "extreme networks"]):
            if any(x in vendor_lower for x in ["ap", "access point", "wireless"]):
                return "access_point"
            return "access_point"  # Most are APs
        # IP Phones
        elif any(x in vendor_lower for x in ["yealink", "polycom", "grandstream", "snom", "mitel", "avaya"]):
            return "ip_phone"
        elif "ip phone" in vendor_lower or "voip" in vendor_lower:
            return "ip_phone"
        # Handheld / Palmari industriali
        elif any(x in vendor_lower for x in ["zebra", "honeywell", "datalogic", "symbol", "intermec", "cipherlab", "unitech", "simcom", "urovo", "shanghai simcom"]):
            return "handheld"
        # Network equipment
        elif any(x in vendor_lower for x in ["cisco", "huawei", "juniper", "netgear", "d-link", "tenda"]):
            return "network"
        # Mobile devices
        elif any(x in vendor_lower for x in ["apple", "samsung", "xiaomi", "oppo", "oneplus", "motorola"]):
            return "mobile"
        # Printers
        elif any(x in vendor_lower for x in ["printer", "jet", "lexmark", "epson", "canon", "brother"]):
            return "printer"
        elif any(x in vendor_lower for x in ["hp", "hewlett"]):
            if "printer" in vendor_lower or "jet" in vendor_lower:
                return "printer"
            return "workstation"
        # Workstations
        elif any(x in vendor_lower for x in ["dell", "lenovo", "asus", "acer", "intel"]):
            return "workstation"
        # IoT
        elif any(x in vendor_lower for x in ["raspberry", "arduino", "espressif"]):
            return "iot"
        # Retail / POS / Scale
        elif any(x in vendor_lower for x in ["bizerba", "mettler", "pos", "ncr"]):
            return "scale"

        return "unknown"

    def update_all_vendor_info(self) -> Dict[str, int]:
        """
        Update vendor information for all MAC addresses without vendor data.

        Returns:
            Statistics about the update
        """
        macs_without_vendor = self.db.query(MacAddress).filter(
            MacAddress.vendor_name == None
        ).all()

        stats = {
            "total": len(macs_without_vendor),
            "updated": 0,
            "not_found": 0,
        }

        for mac in macs_without_vendor:
            vendor_name, device_type = self.get_vendor_info(mac.mac_address)
            if vendor_name:
                mac.vendor_name = vendor_name
                mac.device_type = device_type
                stats["updated"] += 1
            else:
                stats["not_found"] += 1

        self.db.commit()
        return stats
