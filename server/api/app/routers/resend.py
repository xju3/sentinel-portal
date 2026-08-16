import base64
import hashlib
import hmac
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from pub.services import get_session
from pub.models.customer import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resend", tags=["Resend"])

def verify_svix_signature(secret: str, msg_id: str, timestamp: str, body: bytes, signature_header: str) -> bool:
    """Verifies a standard Svix webhook signature."""
    try:
        if secret.startswith("whsec_"):
            secret = secret[6:]
        secret_bytes = base64.b64decode(secret)
        
        to_sign = f"{msg_id}.{timestamp}.".encode("utf-8") + body
        expected_sig = hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
        expected_sig_b64 = base64.b64encode(expected_sig).decode("utf-8")
        
        passed_signatures = signature_header.split(" ")
        for passed_sig in passed_signatures:
            if "," in passed_sig:
                version, signature = passed_sig.split(",", 1)
                if version == "v1" and hmac.compare_digest(signature, expected_sig_b64):
                    return True
        return False
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False

@router.post("")
async def handle_resend_webhook(
    request: Request,
    svix_id: str = Header(..., alias="svix-id"),
    svix_timestamp: str = Header(..., alias="svix-timestamp"),
    svix_signature: str = Header(..., alias="svix-signature"),
    db: AsyncSession = Depends(get_session),
):
    """
    Handle webhooks from Resend.
    """
    body = await request.body()
    
    # Verify signature if a secret is configured
    webhook_secret = settings.resend_web_hook_key
    if webhook_secret:
        is_valid = verify_svix_signature(
            secret=webhook_secret,
            msg_id=svix_id,
            timestamp=svix_timestamp,
            body=body,
            signature_header=svix_signature
        )
        if not is_valid:
            logger.warning("Invalid Resend webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("type")
    
    # We only care about email.delivered and email.opened
    if event_type not in ["email.delivered", "email.opened"]:
        return {"status": "ignored", "reason": "unhandled event type"}
    
    data = payload.get("data", {})
    to_emails = data.get("to", [])
    
    if not to_emails:
        return {"status": "ignored", "reason": "no recipient email found"}
    
    # We assume the first email address is the main recipient matching our tenant
    target_email = to_emails[0]
    
    target_status = 1 if event_type == "email.delivered" else 2

    try:
        # Find tenant by email
        result = await db.execute(select(Tenant).where(Tenant.email == target_email))
        tenant = result.scalars().first()
        
        if not tenant:
            logger.info(f"Resend webhook: No tenant found with email {target_email}")
            return {"status": "ignored", "reason": "tenant not found"}
        
        # We only upgrade the status. If it's already opened (2), don't revert to delivered (1).
        if not (tenant.email_status == 2 and target_status == 1):
            tenant.email_status = target_status
            await db.commit()
            logger.info(f"Resend webhook: Updated tenant {tenant.id} email_status to {target_status} for {target_email}")
            
        return {"status": "success"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error processing resend webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
