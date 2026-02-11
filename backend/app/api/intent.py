"""Intent Verification API endpoints (IP Fabric-like compliance checks)."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.intent_verification import (
    IntentVerificationService,
    CheckSeverity,
    CheckCategory
)

router = APIRouter(tags=["intent-verification"])


class CheckResultResponse(BaseModel):
    check_id: str
    check_name: str
    category: str
    severity: str
    passed: bool
    message: str
    affected_count: int
    affected_items: List[dict]
    checked_at: datetime
    details: Optional[dict] = None
    remediation: Optional[str] = None  # Suggested fix/action


class IntentSummary(BaseModel):
    total_checks: int
    passed: int
    failed: int
    by_severity: dict
    by_category: dict
    checks: List[CheckResultResponse]
    run_at: datetime


class AvailableCheck(BaseModel):
    id: str
    name: str
    description: str


@router.get("/checks", response_model=List[AvailableCheck])
def list_available_checks(db: Session = Depends(get_db)):
    """List all available intent verification checks."""
    service = IntentVerificationService(db)
    return service.get_available_checks()


@router.post("/run", response_model=IntentSummary)
def run_all_checks(db: Session = Depends(get_db)):
    """Run all intent verification checks and return summary."""
    service = IntentVerificationService(db)
    results = service.run_all_checks()

    # Build summary
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    by_severity = {}
    by_category = {}

    for r in results:
        sev = r.severity.value
        cat = r.category.value
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1

    checks = [
        CheckResultResponse(
            check_id=r.check_id,
            check_name=r.check_name,
            category=r.category.value,
            severity=r.severity.value,
            passed=r.passed,
            message=r.message,
            affected_count=len(r.affected_items),
            affected_items=r.affected_items[:20],  # Limit items in response
            checked_at=r.checked_at,
            details=r.details,
            remediation=r.remediation
        )
        for r in results
    ]

    return IntentSummary(
        total_checks=len(results),
        passed=passed,
        failed=failed,
        by_severity=by_severity,
        by_category=by_category,
        checks=checks,
        run_at=datetime.utcnow()
    )


@router.post("/run/{check_id}", response_model=CheckResultResponse)
def run_single_check(check_id: str, db: Session = Depends(get_db)):
    """Run a specific intent verification check."""
    service = IntentVerificationService(db)
    result = service.run_check(check_id)

    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Check '{check_id}' not found")

    return CheckResultResponse(
        check_id=result.check_id,
        check_name=result.check_name,
        category=result.category.value,
        severity=result.severity.value,
        passed=result.passed,
        message=result.message,
        affected_count=len(result.affected_items),
        affected_items=result.affected_items,
        checked_at=result.checked_at,
        details=result.details,
        remediation=result.remediation
    )


@router.get("/summary", response_model=dict)
def get_quick_summary(db: Session = Depends(get_db)):
    """Get a quick summary of network health without running full checks.

    This is a lighter-weight endpoint for dashboard widgets.
    """
    service = IntentVerificationService(db)
    results = service.run_all_checks()

    critical = sum(1 for r in results if not r.passed and r.severity == CheckSeverity.CRITICAL)
    errors = sum(1 for r in results if not r.passed and r.severity == CheckSeverity.ERROR)
    warnings = sum(1 for r in results if not r.passed and r.severity == CheckSeverity.WARNING)

    # Calculate health score (0-100)
    total_weight = len(results) * 10
    deductions = critical * 30 + errors * 15 + warnings * 5
    health_score = max(0, 100 - (deductions * 100 / total_weight)) if total_weight > 0 else 100

    return {
        "health_score": round(health_score, 1),
        "total_checks": len(results),
        "passed": sum(1 for r in results if r.passed),
        "issues": {
            "critical": critical,
            "errors": errors,
            "warnings": warnings
        },
        "top_issues": [
            {
                "check": r.check_name,
                "severity": r.severity.value,
                "message": r.message
            }
            for r in sorted(results, key=lambda x: (
                0 if x.severity == CheckSeverity.CRITICAL else
                1 if x.severity == CheckSeverity.ERROR else
                2 if x.severity == CheckSeverity.WARNING else 3
            ))
            if not r.passed
        ][:5]
    }


# === Scheduler endpoints ===

class SchedulerConfig(BaseModel):
    enabled: bool
    interval_minutes: int = 60


@router.get("/scheduler/status")
def get_scheduler_status():
    """Get intent check scheduler status."""
    from app.services.intent.intent_scheduler import get_intent_scheduler
    scheduler = get_intent_scheduler()
    return scheduler.get_status()


@router.post("/scheduler/configure")
def configure_scheduler(config: SchedulerConfig):
    """Configure the intent check scheduler."""
    from app.services.intent.intent_scheduler import get_intent_scheduler
    scheduler = get_intent_scheduler()

    if config.enabled:
        scheduler.enable(config.interval_minutes)
    else:
        scheduler.disable()

    return scheduler.get_status()


@router.post("/scheduler/run-now")
def run_scheduler_now():
    """Trigger an immediate intent check run."""
    from app.services.intent.intent_scheduler import get_intent_scheduler
    scheduler = get_intent_scheduler()
    result = scheduler.run_now()
    return {
        "status": "completed",
        "passed": result.get("passed", 0) if result else 0,
        "failed": result.get("failed", 0) if result else 0,
    }
