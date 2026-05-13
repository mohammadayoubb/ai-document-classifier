"""Audit log API routes.

Audit routes expose read-only audit information to allowed users.
The route calls the service layer and never queries the database directly.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_audit_service, require_admin_or_auditor
from app.domain.audit import AuditLogDomain
from app.domain.user import UserDomain
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogDomain])
async def list_audit_log(
    current_user: Annotated[UserDomain, Depends(require_admin_or_auditor)],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
) -> list[AuditLogDomain]:
    """Return audit log entries.

    Admins and auditors can read the audit log. Reviewers cannot.
    """
    # Permission is enforced by the dependency above.
    # The variable is intentionally kept to make the authorization dependency explicit.
    _ = current_user

    return await audit_service.list_audit_log()