"""Alert Rules and Webhooks API endpoints."""
import json
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AlertRule, Webhook

router = APIRouter()


# === Alert Rule Schemas ===
class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rule_type: str  # oui_filter, switch_filter, vlan_filter, vendor_filter
    conditions: dict  # JSON conditions
    alert_severity: str = "warning"
    is_enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rule_type: Optional[str] = None
    conditions: Optional[dict] = None
    alert_severity: Optional[str] = None
    is_enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    rule_type: str
    conditions: dict
    alert_severity: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Webhook Schemas ===
class WebhookCreate(BaseModel):
    name: str
    url: str
    webhook_type: str = "generic"  # generic, slack, teams, discord, siem
    secret_token: Optional[str] = None
    alert_types: List[str] = ["all"]  # or specific types
    is_enabled: bool = True


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    webhook_type: Optional[str] = None
    secret_token: Optional[str] = None
    alert_types: Optional[List[str]] = None
    is_enabled: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    webhook_type: str
    alert_types: List[str]
    is_enabled: bool
    last_triggered: Optional[datetime]
    last_status: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# === Alert Rules Endpoints ===
@router.get("/rules", response_model=List[AlertRuleResponse])
def list_alert_rules(db: Session = Depends(get_db)):
    """List all custom alert rules."""
    rules = db.query(AlertRule).order_by(AlertRule.created_at.desc()).all()
    result = []
    for rule in rules:
        try:
            conditions = json.loads(rule.conditions)
        except:
            conditions = {}
        result.append(AlertRuleResponse(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            rule_type=rule.rule_type,
            conditions=conditions,
            alert_severity=rule.alert_severity,
            is_enabled=rule.is_enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        ))
    return result


@router.post("/rules", response_model=AlertRuleResponse)
def create_alert_rule(rule: AlertRuleCreate, db: Session = Depends(get_db)):
    """Create a new custom alert rule."""
    new_rule = AlertRule(
        name=rule.name,
        description=rule.description,
        rule_type=rule.rule_type,
        conditions=json.dumps(rule.conditions),
        alert_severity=rule.alert_severity,
        is_enabled=rule.is_enabled
    )
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    return AlertRuleResponse(
        id=new_rule.id,
        name=new_rule.name,
        description=new_rule.description,
        rule_type=new_rule.rule_type,
        conditions=rule.conditions,
        alert_severity=new_rule.alert_severity,
        is_enabled=new_rule.is_enabled,
        created_at=new_rule.created_at,
        updated_at=new_rule.updated_at
    )


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(rule_id: int, rule: AlertRuleUpdate, db: Session = Depends(get_db)):
    """Update a custom alert rule."""
    existing = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    if rule.name is not None:
        existing.name = rule.name
    if rule.description is not None:
        existing.description = rule.description
    if rule.rule_type is not None:
        existing.rule_type = rule.rule_type
    if rule.conditions is not None:
        existing.conditions = json.dumps(rule.conditions)
    if rule.alert_severity is not None:
        existing.alert_severity = rule.alert_severity
    if rule.is_enabled is not None:
        existing.is_enabled = rule.is_enabled

    db.commit()
    db.refresh(existing)

    try:
        conditions = json.loads(existing.conditions)
    except:
        conditions = {}

    return AlertRuleResponse(
        id=existing.id,
        name=existing.name,
        description=existing.description,
        rule_type=existing.rule_type,
        conditions=conditions,
        alert_severity=existing.alert_severity,
        is_enabled=existing.is_enabled,
        created_at=existing.created_at,
        updated_at=existing.updated_at
    )


@router.delete("/rules/{rule_id}")
def delete_alert_rule(rule_id: int, db: Session = Depends(get_db)):
    """Delete a custom alert rule."""
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted", "id": rule_id}


# === Webhook Endpoints ===
@router.get("/webhooks", response_model=List[WebhookResponse])
def list_webhooks(db: Session = Depends(get_db)):
    """List all webhooks."""
    webhooks = db.query(Webhook).order_by(Webhook.created_at.desc()).all()
    result = []
    for wh in webhooks:
        try:
            alert_types = json.loads(wh.alert_types) if wh.alert_types != "all" else ["all"]
        except:
            alert_types = ["all"]
        result.append(WebhookResponse(
            id=wh.id,
            name=wh.name,
            url=wh.url,
            webhook_type=wh.webhook_type,
            alert_types=alert_types,
            is_enabled=wh.is_enabled,
            last_triggered=wh.last_triggered,
            last_status=wh.last_status,
            created_at=wh.created_at
        ))
    return result


@router.post("/webhooks", response_model=WebhookResponse)
def create_webhook(webhook: WebhookCreate, db: Session = Depends(get_db)):
    """Create a new webhook."""
    new_wh = Webhook(
        name=webhook.name,
        url=webhook.url,
        webhook_type=webhook.webhook_type,
        secret_token=webhook.secret_token,
        alert_types=json.dumps(webhook.alert_types) if webhook.alert_types != ["all"] else "all",
        is_enabled=webhook.is_enabled
    )
    db.add(new_wh)
    db.commit()
    db.refresh(new_wh)
    return WebhookResponse(
        id=new_wh.id,
        name=new_wh.name,
        url=new_wh.url,
        webhook_type=new_wh.webhook_type,
        alert_types=webhook.alert_types,
        is_enabled=new_wh.is_enabled,
        last_triggered=new_wh.last_triggered,
        last_status=new_wh.last_status,
        created_at=new_wh.created_at
    )


@router.put("/webhooks/{webhook_id}", response_model=WebhookResponse)
def update_webhook(webhook_id: int, webhook: WebhookUpdate, db: Session = Depends(get_db)):
    """Update a webhook."""
    existing = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if webhook.name is not None:
        existing.name = webhook.name
    if webhook.url is not None:
        existing.url = webhook.url
    if webhook.webhook_type is not None:
        existing.webhook_type = webhook.webhook_type
    if webhook.secret_token is not None:
        existing.secret_token = webhook.secret_token
    if webhook.alert_types is not None:
        existing.alert_types = json.dumps(webhook.alert_types) if webhook.alert_types != ["all"] else "all"
    if webhook.is_enabled is not None:
        existing.is_enabled = webhook.is_enabled

    db.commit()
    db.refresh(existing)

    try:
        alert_types = json.loads(existing.alert_types) if existing.alert_types != "all" else ["all"]
    except:
        alert_types = ["all"]

    return WebhookResponse(
        id=existing.id,
        name=existing.name,
        url=existing.url,
        webhook_type=existing.webhook_type,
        alert_types=alert_types,
        is_enabled=existing.is_enabled,
        last_triggered=existing.last_triggered,
        last_status=existing.last_status,
        created_at=existing.created_at
    )


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, db: Session = Depends(get_db)):
    """Delete a webhook."""
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(wh)
    db.commit()
    return {"message": "Webhook deleted", "id": webhook_id}


@router.post("/webhooks/{webhook_id}/test")
def test_webhook(webhook_id: int, db: Session = Depends(get_db)):
    """Test a webhook by sending a test payload."""
    import httpx

    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Build test payload based on type
    if wh.webhook_type == "slack":
        payload = {
            "text": "🔔 *Mac-Traker Test Alert*\nThis is a test notification from Mac-Traker.",
            "attachments": [{
                "color": "#36a64f",
                "fields": [{
                    "title": "Test",
                    "value": "Webhook configuration is working correctly",
                    "short": False
                }]
            }]
        }
    elif wh.webhook_type == "teams":
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": "Mac-Traker Test Alert",
            "sections": [{
                "activityTitle": "🔔 Mac-Traker Test Alert",
                "facts": [{
                    "name": "Status",
                    "value": "Test successful"
                }]
            }]
        }
    else:
        payload = {
            "event": "test",
            "source": "Mac-Traker",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "This is a test notification from Mac-Traker"
        }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(wh.url, json=payload)
            response.raise_for_status()

        wh.last_triggered = datetime.utcnow()
        wh.last_status = "success"
        db.commit()

        return {"status": "success", "message": "Test notification sent"}
    except Exception as e:
        wh.last_triggered = datetime.utcnow()
        wh.last_status = f"error: {str(e)[:100]}"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Webhook test failed: {str(e)}")
