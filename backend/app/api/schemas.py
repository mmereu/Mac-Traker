"""Pydantic schemas for API request/response."""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator


def empty_to_none(v: Any) -> Any:
    """Convert empty strings to None."""
    if v == "" or v == "undefined":
        return None
    return v


# Switch Schemas
class SwitchBase(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    ip_address: str = Field(..., min_length=7, max_length=45)
    device_type: str = Field(default="huawei")
    snmp_community: Optional[str] = None
    group_id: Optional[int] = None
    location: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    use_ssh_fallback: bool = Field(default=False)

    @field_validator('snmp_community', 'location', 'model', 'serial_number', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return empty_to_none(v)


class SwitchCreate(SwitchBase):
    pass


class SwitchUpdate(BaseModel):
    hostname: Optional[str] = Field(None, min_length=1, max_length=255)
    ip_address: Optional[str] = Field(None, min_length=7, max_length=45)
    device_type: Optional[str] = None
    snmp_community: Optional[str] = None
    group_id: Optional[int] = None
    location: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    is_active: Optional[bool] = None
    use_ssh_fallback: Optional[bool] = None


class SwitchGroupBasic(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class SwitchResponse(SwitchBase):
    id: int
    is_active: bool
    use_ssh_fallback: bool = False
    last_seen: Optional[datetime] = None
    last_discovery: Optional[datetime] = None
    created_at: datetime
    group: Optional[SwitchGroupBasic] = None
    mac_count: int = 0
    # SNMP-discovered system information
    sys_name: Optional[str] = None
    ports_up_count: int = 0
    ports_down_count: int = 0
    vlan_count: int = 0
    # Site code extracted from hostname prefix (e.g., "01", "02")
    site_code: Optional[str] = None

    class Config:
        from_attributes = True


class SwitchListResponse(BaseModel):
    items: List[SwitchResponse]
    total: int


# Switch Group Schemas
class SwitchGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_port: int = Field(default=22)


class SwitchGroupCreate(SwitchGroupBase):
    pass


class SwitchGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_port: Optional[int] = None


class SwitchGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_port: int
    created_at: datetime
    updated_at: datetime
    switch_count: int = 0

    class Config:
        from_attributes = True


class SwitchGroupListResponse(BaseModel):
    items: List[SwitchGroupResponse]
    total: int


# Dashboard Schemas
class DashboardStats(BaseModel):
    mac_count: int
    switch_count: int
    alert_count: int
    last_discovery: Optional[datetime] = None


# Alert Schemas
class AlertResponse(BaseModel):
    id: int
    alert_type: str
    message: str
    severity: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    items: List[AlertResponse]
    total: int
    unread_count: int


# Port Schemas
class PortResponse(BaseModel):
    id: int
    switch_id: int
    port_name: str
    port_index: Optional[int] = None
    port_description: Optional[str] = None
    port_type: str = "access"  # access, trunk, uplink
    vlan_id: Optional[int] = None
    admin_status: str = "up"
    oper_status: str = "up"
    speed: Optional[str] = None
    is_uplink: bool = False
    last_mac_count: int = 0
    updated_at: datetime

    class Config:
        from_attributes = True


class PortListResponse(BaseModel):
    items: List[PortResponse]
    total: int


# Delete Request Schema
class BulkDeleteRequest(BaseModel):
    switch_ids: List[int]


# Delete Response Schema
class DeleteResult(BaseModel):
    deleted_count: int
    success: bool

    class Config:
        from_attributes = True
