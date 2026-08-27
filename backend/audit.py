from __future__ import annotations
from typing import Dict, Any
from sqlalchemy.orm import Session
from .models import AuditLog

def write_audit(db: Session, actor: str, action: str, payload: Dict[str, Any]) -> int:
    record = AuditLog(actor=actor, action=action, payload=payload)
    db.add(record)
    # Let the caller commit the audit entry with the business operation.
    db.flush()
    return record.id
