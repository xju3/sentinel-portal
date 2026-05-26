"""
Authentication dependencies.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.customer import Account
from app.utils.jwt_token import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Account:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    try:
        payload = decode_access_token(credentials.credentials)
        account_id = UUID(str(payload.get("sub")))
        token_tenant_id = UUID(str(payload.get("tenant_id")))
        username = payload.get("username")
        admin = payload.get("admin", False)
        contact_id_str = payload.get("contact_id")
        contact_id = UUID(contact_id_str) if contact_id_str else None
        flag = payload.get("flag", 1)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authorization expired",
        ) from exc

    # Construct an in-memory Account object to avoid a DB hit on every request
    account = Account(
        id=account_id,
        tenant_id=token_tenant_id,
        username=username,
        admin=admin,
        contact_id=contact_id,
        flag=flag,
        active=True,  # Assume active since token is valid. Real state requires DB query.
    )

    return account
