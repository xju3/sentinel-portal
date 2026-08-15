import uuid
import logging
import asyncio
import hashlib
import re
import secrets
import string
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pub.services import get_session
from pub.services import AuthService
from pub.services import WxService
from pub.services.customer.org_service import EmployeeService
from app.config import settings
from app.database import redis_manager
from app.services.wx_diagnosis_access_service import WxDiagnosisAccessService
from pub.utils.redis_keys import REDIS_KEY_WX_SCAN
from app.utils.auth import get_current_account
from pub.models.customer import Account
from pub.models.diagnosis import DiagnosisNotificationDelivery
from pub.utils.jwt_token import create_access_token
from pub.contract.auth import LoginResponse, RegisterRequest
from app.utils.response import success
from pydantic import BaseModel
from app.clients.email import EmailDeliveryError, send_registration_email
from pub.utils.jwt_token import create_password_setup_token
from urllib.parse import urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
from pub.services.wx.crypto import WXBizMsgCrypt

router = APIRouter(tags=["wx"])

def get_wx_service() -> WxService:
    return WxService(
        app_id=settings.wx_app_id,
        app_secret=settings.wx_app_secret,
        redis_client=redis_manager.get_client()
    )



@router.get("/wx/message")
async def wx_message_get(
    signature: str = Query(None),
    timestamp: str = Query(None),
    nonce: str = Query(None),
    echostr: str = Query(None)
):
    """WeChat server verification endpoint (Secure mode)"""
    if not all([signature, timestamp, nonce, echostr]):
        return Response(content="missing parameters")
        
    wx_service = get_wx_service()
    if wx_service.verify_signature(signature, timestamp, nonce, settings.wx_token):
        return Response(content=echostr)
    else:
        return Response(content="error")


@router.get("/wx-mini-app/push-message")
async def wx_mini_app_push_message_verify(
    signature: str = Query(None),
    timestamp: str = Query(None),
    nonce: str = Query(None),
    echostr: str = Query(None)
):
    """WeChat Mini Program message push server verification endpoint"""
    if not all([signature, timestamp, nonce, echostr]):
        return Response(content="missing parameters")

    wx_service = get_wx_service()
    if wx_service.verify_signature(signature, timestamp, nonce, settings.wx_mini_app_push_message_token):
        return Response(content=echostr)
    else:
        logger.warning("wx mini app push message signature verification failed")
        return Response(content="error")


# ── Mini App Login ──────────────────────────────────────────────────────────────

class MiniAppLoginRequest(BaseModel):
    code: str


@router.post("/wx-mini-app/login")
async def wx_mini_app_login(
    payload: MiniAppLoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """Exchange a wx.login() code for user binding status.

    Returns:
      registered=True  + JWT token + tenant info  if the openid is bound to an account.
      registered=False + openid                   if not registered yet.
    """
    try:
        session_data = await WxService.jscode2session(
            mini_app_id=settings.wx_mini_app_id,
            mini_app_secret=settings.wx_mini_app_secret,
            code=payload.code,
        )
    except Exception as e:
        logger.error(f"jscode2session failed: {e}")
        raise HTTPException(status_code=502, detail="微信登录验证失败，请稍后重试")

    mini_open_id: str = session_data["openid"]
    union_id: Optional[str] = session_data.get("unionid")

    account = None
    if union_id:
        account = await AuthService.get_account_by_wx_union_id(session, union_id)

    if account is None:
        account = await AuthService.get_account_by_wx_mini_open_id(session, mini_open_id)

    if account is None:
        return success({"registered": False, "openid": mini_open_id, "unionid": union_id})
        
    # Silent binding: if account found via union_id but missing mini_open_id
    if account.wx_mini_open_id != mini_open_id or (union_id and account.wx_union_id != union_id):
        await AuthService.bind_account_wx_mini(session, account, mini_open_id, union_id)

    tenant_name: Optional[str] = None
    contact_name: Optional[str] = None
    tenant = await AuthService.get_tenant_by_id(session, account.tenant_id)
    if tenant:
        tenant_name = str(tenant.name)
    if account.contact_id:
        contact = await AuthService.get_contact_by_id(session, account.contact_id)
        if contact:
            contact_name = str(contact.name)

    expires_in = settings.jwt_access_token_expires_minutes * 60
    access_token = create_access_token(
        subject=str(account.id),
        tenant_id=str(account.tenant_id),
        username=account.username,
        jwt_secret_key=settings.jwt_secret_key,
        admin=account.admin,
        contact_id=str(account.contact_id) if account.contact_id else None,
        flag=account.flag,
        expires_minutes=settings.jwt_access_token_expires_minutes,
    )

    return success({
        "registered": True,
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "account_id": str(account.id),
        "tenant_id": str(account.tenant_id),
        "tenant_name": tenant_name,
        "contact_id": str(account.contact_id) if account.contact_id else None,
        "contact_name": contact_name,
    })


# ── Mini App Login With Password ───────────────────────────────────────────────

class MiniAppLoginWithPasswordRequest(BaseModel):
    username: str
    password: str
    openid: str
    unionid: Optional[str] = None

@router.post("/wx-mini-app/bind-login")
async def wx_mini_app_bind_login(
    payload: MiniAppLoginWithPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Login with username/password and bind the WeChat mini-app identity."""
    account = await AuthService.get_account_by_credentials(
        session, payload.username, payload.password
    )
    if account is None:
        raise HTTPException(status_code=401, detail="用户名或密码不正确")

    # Bind openid (and unionid)
    await AuthService.bind_account_wx_mini(session, account, payload.openid, payload.unionid)

    tenant_name: Optional[str] = None
    contact_name: Optional[str] = None
    tenant = await AuthService.get_tenant_by_id(session, account.tenant_id)
    if tenant:
        tenant_name = str(tenant.name)
    if account.contact_id:
        contact = await AuthService.get_contact_by_id(session, account.contact_id)
        if contact:
            contact_name = str(contact.name)

    expires_in = settings.jwt_access_token_expires_minutes * 60
    access_token = create_access_token(
        subject=str(account.id),
        tenant_id=str(account.tenant_id),
        username=account.username,
        jwt_secret_key=settings.jwt_secret_key,
        admin=account.admin,
        contact_id=str(account.contact_id) if account.contact_id else None,
        flag=account.flag,
        expires_minutes=settings.jwt_access_token_expires_minutes,
    )

    return success({
        "registered": True,
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "account_id": str(account.id),
        "tenant_id": str(account.tenant_id),
        "tenant_name": tenant_name,
        "contact_id": str(account.contact_id) if account.contact_id else None,
        "contact_name": contact_name,
    })


# ── Mini App Register ────────────────────────────────────────────────────────────

USERNAME_FLAG_EMAIL = 1
PASSWORD_SETUP_PREFIX = "!setup:"


def _mini_company_slug(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    return slug or "tenant"


def _mini_normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _mini_password_setup_marker(nonce: str) -> str:
    digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    return f"{PASSWORD_SETUP_PREFIX}{digest}"


def _mini_build_password_setup_url(token: str) -> str:
    portal = urlsplit(settings.portal_login_url)
    query = urlencode({"token": token})
    return urlunsplit((portal.scheme, portal.netloc, "/set-password", query, ""))


async def _mini_generate_unique_tenant_code(session: AsyncSession) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(8):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        existing = await AuthService.get_tenant_by_code(session, code)
        if existing is None:
            return code
    raise HTTPException(status_code=500, detail="Unable to generate unique tenant code")


class MiniAppRegisterRequest(BaseModel):
    company_name: str
    contact_name: str
    phone: str
    email: str
    openid: str  # mini app openid obtained from /wx-mini-app/login
    unionid: Optional[str] = None


@router.post("/wx-mini-app/register")
async def wx_mini_app_register(
    payload: MiniAppRegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new tenant account from the Mini Program.

    After successful registration the openid is bound to the new account.
    A password-setup email is sent to the provided address.
    """
    normalized_phone = _mini_normalize_phone(payload.phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    company_name = payload.company_name.strip()
    contact_name = payload.contact_name.strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="公司名称不能为空")
    if not contact_name:
        raise HTTPException(status_code=400, detail="联系人姓名不能为空")

    # Verify openid hasn't been registered yet
    existing = await AuthService.get_account_by_wx_mini_open_id(session, payload.openid)
    if existing:
        raise HTTPException(status_code=400, detail="该微信账号已注册，请勿重复注册")
        
    if payload.unionid:
        existing_union = await AuthService.get_account_by_wx_union_id(session, payload.unionid)
        if existing_union:
            raise HTTPException(status_code=400, detail="该微信账号已绑定其他租户，请勿重复注册")

    tenant_code = await _mini_generate_unique_tenant_code(session)
    slug = _mini_company_slug(company_name)
    setup_nonce = secrets.token_urlsafe(32)
    password_marker = _mini_password_setup_marker(setup_nonce)

    try:
        result = await AuthService.register(
            session=session,
            username=email,
            email=email,
            normalized_phone=normalized_phone,
            company_name=company_name,
            contact_name=contact_name,
            login_channel="email",
            account_flag=USERNAME_FLAG_EMAIL,
            tenant_code=tenant_code,
            tenant_mqtt_server=f"mqtt.{slug}.portal.local",
            tenant_api_server=f"api.{slug}.portal.local",
            password_value=password_marker,
        )
        setup_token = create_password_setup_token(
            subject=str(result["account_id"]),
            nonce=setup_nonce,
            jwt_secret_key=settings.jwt_secret_key,
            expires_minutes=settings.password_setup_token_expires_minutes,
        )
        await asyncio.to_thread(
            send_registration_email,
            recipient=email,
            contact_name=contact_name,
            company_name=company_name,
            password_setup_url=_mini_build_password_setup_url(setup_token),
        )
        # Bind openid to the new account
        account = await AuthService.get_account(session, result["account_id"])
        if account:
            await AuthService.bind_account_wx_mini(session, account, payload.openid, payload.unionid)
        else:
            await AuthService.commit(session)
    except EmailDeliveryError as exc:
        await AuthService.rollback(session)
        raise HTTPException(
            status_code=503,
            detail="注册邮件发送失败，账号未创建，请稍后重试",
        ) from exc
    except HTTPException:
        raise
    except Exception:
        await AuthService.rollback(session)
        raise

    return success({
        "message": "注册成功，请查收邮件完成密码设置",
        "account_id": str(result["account_id"]),
        "tenant_id": str(result["tenant_id"]),
    })


async def handle_wx_event_message(wx_service: WxService, data: dict, from_user: str, to_user: str, session: AsyncSession) -> str:
    """Handle event messages (subscribe, unsubscribe, scan, etc.) and return plain reply XML or empty string."""
    event = data.get("Event")
    event_key = data.get("EventKey") or ""
    
    async def process_scene(scene: str) -> str:
        redis_client = redis_manager.get_client()
        if not redis_client:
            return ""
            
        if scene.startswith("bind_"):
            existing_account = await AuthService.get_account_by_wx_user_id(session, from_user)
            target_account_id = scene.split("_")[1]
            if existing_account and str(existing_account.id) != target_account_id:
                return wx_service.create_xml_reply(from_user, to_user, "绑定失败：此微信已被其他账号绑定，请勿重复绑定！")
            else:
                redis_client.setex(REDIS_KEY_WX_SCAN.format(scene=scene), 300, from_user)
                return wx_service.create_xml_reply(from_user, to_user, "扫码成功！请返回网页端完成绑定。")
                
        elif scene.startswith("empbind_"):
            existing_employee = await EmployeeService.get_employee_by_wx_user_id(session, from_user)
            target_employee_id = scene.split("_")[1]
            if existing_employee and str(existing_employee.id) != target_employee_id:
                return wx_service.create_xml_reply(from_user, to_user, "绑定失败：此微信已被其他员工绑定，请勿重复绑定！")
            else:
                redis_client.setex(REDIS_KEY_WX_SCAN.format(scene=scene), 300, from_user)
                return wx_service.create_xml_reply(from_user, to_user, "扫码成功！请返回网页端完成员工绑定。")
                
        elif scene.startswith("login_"):
            existing_account = await AuthService.get_account_by_wx_user_id(session, from_user)
            if not existing_account:
                return wx_service.create_xml_reply(from_user, to_user, "登录失败：此微信尚未绑定任何系统账号！")
            else:
                redis_client.setex(REDIS_KEY_WX_SCAN.format(scene=scene), 300, from_user)
                return wx_service.create_xml_reply(from_user, to_user, "扫码成功！正在登录系统...")
                
        else:
            redis_client.setex(REDIS_KEY_WX_SCAN.format(scene=scene), 300, from_user)
            return wx_service.create_xml_reply(from_user, to_user, "操作成功！请返回网页端查看。")
    
    if event == "subscribe":
        scene_str = event_key
        if scene_str.startswith("qrscene_"):
            scene_str = scene_str[8:]
            
        if scene_str:
            # Scanned QR code to subscribe
            return await process_scene(scene_str)
        else:
            # Normal subscribe
            welcome_text = "欢迎关注上海朗湖智能科技！\n在这里您可以随时掌握设备健康状态，接收实时报警信息。"
            return wx_service.create_xml_reply(from_user, to_user, welcome_text)
            
    elif event == "SCAN":
        scene_str = event_key
        if scene_str:
            return await process_scene(scene_str)
            
    elif event == "unsubscribe":
        logger.info(f"User {from_user} unsubscribed.")
        return ""
        
    return ""

async def handle_wx_text_message(wx_service: WxService, data: dict, from_user: str, to_user: str) -> str:
    """Handle normal text messages and return plain reply XML or empty string."""
    content = data.get("Content", "")
    logger.info(f"User {from_user} sent text: {content}")
    # 可以在这里添加自动回复功能，目前默认忽略返回空串
    return ""

@router.post("/wx/message")
async def wx_message_post(
    request: Request,
    msg_signature: str = Query(None),
    timestamp: str = Query(None),
    nonce: str = Query(None),
    session: AsyncSession = Depends(get_session)
):
    """Handle WeChat XML events in Secure Mode"""
    try:
        xml_data = await request.body()
        wx_service = get_wx_service()
        
        if not settings.wx_encoding_aes_key:
            logger.error("Missing wx_encoding_aes_key in settings!")
            print("Missing wx_encoding_aes_key in settings!")
            return Response(content="server missing EncodingAESKey", status_code=500)
            
        crypt = WXBizMsgCrypt(
            token=settings.wx_token,
            encoding_aes_key=settings.wx_encoding_aes_key,
            app_id=settings.wx_app_id
        )
        
        try:
            # Parse outer XML to get Encrypt field
            outer_xml = ET.fromstring(xml_data)
            encrypt = outer_xml.find("Encrypt").text
        except Exception as e:
            logger.error(f"Failed to parse outer XML: {e}")
            return Response(content="invalid xml", status_code=400)
            
        try:
            # Decrypt
            decrypted_xml_str = crypt.decrypt(encrypt, msg_signature, timestamp, nonce)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return Response(content="decryption failed", status_code=403)
            
        # Now we have the real XML
        data = wx_service.parse_xml_event(decrypted_xml_str.encode('utf-8'))
        
        logger.info(f"Received WeChat message (Secure): {data}")
        print(f"Received WeChat message (Secure): {data}")
        
        msg_type = data.get("MsgType")
        from_user = data.get("FromUserName")
        to_user = data.get("ToUserName")
        
        account = await AuthService.get_account_by_wx_user_id(session, from_user)
        if account:
            logger.info(f"Sender Identity: System User '{account.username}' (Account ID: {account.id})")
            print(f"Sender Identity: System User '{account.username}' (Account ID: {account.id})")
        else:
            logger.info(f"Sender Identity: Unbound WeChat User (OpenID: {from_user})")
            print(f"Sender Identity: Unbound WeChat User (OpenID: {from_user})")
            
        reply_xml_str = ""
        if msg_type == "event":
            reply_xml_str = await handle_wx_event_message(wx_service, data, from_user, to_user, session)
        elif msg_type == "text":
            reply_xml_str = await handle_wx_text_message(wx_service, data, from_user, to_user)
        else:
            logger.info(f"Unhandled message type: {msg_type}")
            
        if reply_xml_str:
            encrypted_reply = crypt.generate_encrypted_xml_response(reply_xml_str, nonce)
            return Response(content=encrypted_reply, media_type="application/xml")
            
        return Response(content="success")
    except Exception as e:
        logger.error(f"Unexpected error in wx_message_post: {e}", exc_info=True)
        print(f"Unexpected error in wx_message_post: {e}")
        return Response(content=f"Internal Server Error: {str(e)}", status_code=500)

@router.get("/wx/bind-qrcode")
async def get_bind_qrcode(
    target_account_id: str = Query(...),
    current_account: Account = Depends(get_current_account),
):
    """Generate a QR code ticket for binding WeChat"""
    # Only admin should probably bind for others, or a user for themselves.
    if not current_account.admin and str(current_account.id) != target_account_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    wx_service = get_wx_service()
    scene_str = f"bind_{target_account_id}_{uuid.uuid4().hex[:8]}"
    ticket, url = await wx_service.create_qr_code(scene_str)
    
    return {
        "code": 200,
        "data": {
            "ticket": ticket,
            "scene_str": scene_str,
            "qr_url": url,
            "qr_img_url": f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={ticket}"
        }
    }

@router.get("/wx/empbind-qrcode")
async def get_empbind_qrcode(
    target_employee_id: str = Query(...),
    current_account: Account = Depends(get_current_account),
):
    """Generate a QR code ticket for binding WeChat to an employee"""
    wx_service = get_wx_service()
    scene_str = f"empbind_{target_employee_id}_{uuid.uuid4().hex[:8]}"
    ticket, url = await wx_service.create_qr_code(scene_str)
    
    return {
        "code": 200,
        "data": {
            "ticket": ticket,
            "url": url,
            "scene_str": scene_str
        }
    }

@router.get("/wx/bind-status")
async def get_bind_status(
    scene_str: str = Query(...),
    current_account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session)
):
    """Poll the binding status"""
    redis_client = redis_manager.get_client()
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not configured")
        
    wx_user_id = redis_client.get(REDIS_KEY_WX_SCAN.format(scene=scene_str))
    if wx_user_id:
        # Binding successful
        account_id_str = scene_str.split("_")[1]
        
        # if not current_account.admin and str(current_account.id) != account_id_str:
        #     raise HTTPException(status_code=403, detail="Permission denied")
            
        # 校验微信是否已被其他账号绑定
        existing_account = await AuthService.get_account_by_wx_user_id(session, wx_user_id)
        if existing_account and str(existing_account.id) != account_id_str:
            redis_client.delete(REDIS_KEY_WX_SCAN.format(scene=scene_str))
            raise HTTPException(status_code=400, detail="此微信号已绑定其他账号，请勿重复绑定")
        
        # Update database
        try:
            account_uuid = uuid.UUID(account_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid account ID format")
            
        db_account = await AuthService.get_account(session, account_uuid)
        if db_account:
            union_id = None
            try:
                wx_service = get_wx_service()
                user_info = await wx_service.get_user_info(wx_user_id)
                union_id = user_info.get("unionid")
            except Exception as e:
                logger.warning(f"Failed to fetch user info for unionid during account bind: {e}")
                
            await AuthService.bind_account_wx(session, db_account, wx_user_id, union_id)
            
            # Clean up redis
            redis_client.delete(REDIS_KEY_WX_SCAN.format(scene=scene_str))
            return {"code": 200, "message": "success"}
    
    return {"code": 202, "message": "waiting"}

@router.get("/wx/empbind-status")
async def get_empbind_status(
    scene_str: str = Query(...),
    current_account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session)
):
    """Poll the employee binding status"""
    redis_client = redis_manager.get_client()
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not configured")
        
    wx_user_id = redis_client.get(REDIS_KEY_WX_SCAN.format(scene=scene_str))
    if wx_user_id:
        employee_id_str = scene_str.split("_")[1]
            
        existing_employee = await EmployeeService.get_employee_by_wx_user_id(session, wx_user_id)
        if existing_employee and str(existing_employee.id) != employee_id_str:
            redis_client.delete(REDIS_KEY_WX_SCAN.format(scene=scene_str))
            raise HTTPException(status_code=400, detail="此微信号已绑定其他员工，请勿重复绑定")
        
        try:
            employee_uuid = uuid.UUID(employee_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid employee ID format")
            
        db_employee = await EmployeeService.get_employee_by_id(session, employee_uuid)
        if db_employee:
            union_id = None
            try:
                wx_service = get_wx_service()
                user_info = await wx_service.get_user_info(wx_user_id)
                union_id = user_info.get("unionid")
            except Exception as e:
                logger.warning(f"Failed to fetch user info for unionid during employee bind: {e}")
                
            await EmployeeService.bind_employee_wx(session, db_employee, wx_user_id, union_id)
            
            redis_client.delete(REDIS_KEY_WX_SCAN.format(scene=scene_str))
            return {"code": 200, "message": "success"}
    
    return {"code": 202, "message": "waiting"}

@router.get("/wx/login-qrcode")
async def get_login_qrcode():
    """Generate a QR code ticket for WeChat login"""
    wx_service = get_wx_service()
    scene_str = f"login_{uuid.uuid4().hex[:8]}"
    ticket, url = await wx_service.create_qr_code(scene_str)
    
    return success({
        "ticket": ticket,
        "scene_str": scene_str,
        "qr_url": url,
        "qr_img_url": f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={ticket}"
    })

@router.get("/wx/login-status")
async def get_login_status(
    scene_str: str = Query(...),
    session: AsyncSession = Depends(get_session)
):
    """Poll the login status"""
    redis_client = redis_manager.get_client()
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not configured")
        
    wx_user_id = redis_client.get(REDIS_KEY_WX_SCAN.format(scene=scene_str))
    if wx_user_id:
        account = await AuthService.get_account_by_wx_user_id(session, wx_user_id)
        if not account:
            # Clean up redis
            redis_client.delete(REDIS_KEY_WX_SCAN.format(scene=scene_str))
            # Instead of HTTP error, we return 404 code so frontend can show specific message without throwing global error if possible.
            # But standard is HTTPException. Let's use it.
            raise HTTPException(status_code=404, detail="此微信号没有绑定相应平台账号")
            
        # Clean up redis
        redis_client.delete(REDIS_KEY_WX_SCAN.format(scene=scene_str))
            
        tenant_name = None
        contact_name = None
        tenant = await AuthService.get_tenant_by_id(session, account.tenant_id)
        if tenant:
            tenant_name = str(tenant.name)
            
        if account.contact_id:
            contact = await AuthService.get_contact_by_id(session, account.contact_id)
            if contact:
                contact_name = str(contact.name)

        expires_in = settings.jwt_access_token_expires_minutes * 60
        access_token = create_access_token(
            subject=str(account.id),
            tenant_id=str(account.tenant_id),
            username=account.username,
            jwt_secret_key=settings.jwt_secret_key,
            admin=account.admin,
            contact_id=str(account.contact_id) if account.contact_id else None,
            flag=account.flag,
            expires_minutes=settings.jwt_access_token_expires_minutes,
        )

        return success(LoginResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            account_id=account.id,
            username=account.username,
            tenant_id=account.tenant_id,
            tenant_name=tenant_name,
            contact_id=account.contact_id,
            contact_name=contact_name,
            flag=account.flag,
        ))
    
    # Still waiting
    return {"code": 202, "message": "waiting"}

class SendMsgRequest(BaseModel):
    wx_open_id: str
    message_text: str

@router.post("/wx/test-send-msg")
async def test_send_msg(
    req: SendMsgRequest
):
    """Test sending a customer service message to a specific user"""
    wx_service = get_wx_service()
    try:
        await wx_service.send_custom_message(req.wx_open_id, req.message_text)
        return success({"message": "消息发送成功"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"消息发送失败: {str(e)}")

class SendTemplateRequest(BaseModel):
    wx_open_id: str

@router.post("/wx/test-send-template")
async def test_send_template(
    req: SendTemplateRequest
):
    """Test sending a template message to a specific user"""
    wx_service = get_wx_service()
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        template_id = "gkcCWWRQrMMvypWKQypnfcA3dlU4CM3m9uhzmxKe6KE"
        data = {
            "character_string11": {
                "value": "DEV-TEST-001"
            },
            "thing2": {
                "value": "测试告警传感器"
            },
            "time3": {
                "value": current_time
            },
            "thing18": {
                "value": "测试触发的模拟故障"
            },
            "phrase20": {
                "value": "严重"
            }
        }
        await wx_service.send_template_message(
            to_user_openid=req.wx_open_id, 
            template_id=template_id, 
            data=data,
            url="https://langhu.ai" # 填写实际的详情页面链接
        )
        return success({"message": "模板消息发送成功"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板消息发送失败: {str(e)}")


@router.get("/wx/diagnosis/entry")
async def wx_diagnosis_entry(
    request: Request,
    delivery_id: UUID = Query(..., description="Notification delivery id"),
    session: AsyncSession = Depends(get_session),
):
    delivery = await session.get(DiagnosisNotificationDelivery, delivery_id)
    if delivery is None or delivery.report_id is None:
        raise HTTPException(status_code=404, detail="Diagnosis delivery not found")
    state = WxDiagnosisAccessService.create_signed_state(
        delivery_id=delivery.id,
        report_id=delivery.report_id,
        fault_type=delivery.fault_type,
    )
    authorize_url = WxDiagnosisAccessService.build_oauth_authorize_url(
        request=request,
        state_token=state,
    )
    return RedirectResponse(authorize_url, status_code=302)


@router.get("/wx/diagnosis/callback")
async def wx_diagnosis_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    result = await WxDiagnosisAccessService.authorize_callback(
        session=session,
        request=request,
        code=code,
        state_token=state,
    )
    response = RedirectResponse(result.redirect_url, status_code=302)
    response.set_cookie(
        key=settings.wx_diagnosis_cookie_name,
        value=result.cookie_value,
        max_age=result.cookie_max_age,
        httponly=True,
        secure=settings.wx_diagnosis_cookie_secure,
        samesite="lax",
        path=result.cookie_path,
    )
    return response
