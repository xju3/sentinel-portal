"""
Authentication dependencies.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_manager
from app.models.customer import Account
from app.utils.jwt_token import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(db_manager.get_session),
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
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authorization expired",
        ) from exc

    result = await session.execute(
        select(Account).where(Account.id == account_id, Account.active == True)  # noqa: E712
    )
    account = result.scalar_one_or_none()
    if account is None or account.tenant_id != token_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authorization expired",
        )

    return account
