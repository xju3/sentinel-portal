import uuid
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pub.services import get_session
from pub.services import AuthService
from pub.services import WxService
from app.config import settings
from app.database import redis_manager
from app.utils.auth import get_current_account
from pub.models.customer import Account
from pub.utils.jwt_token import create_access_token
from pub.contract.auth import LoginResponse
from app.utils.response import success
from pydantic import BaseModel
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

async def handle_wx_event_message(wx_service: WxService, data: dict, from_user: str, to_user: str) -> str:
    """Handle event messages (subscribe, unsubscribe, scan, etc.) and return plain reply XML or empty string."""
    event = data.get("Event")
    event_key = data.get("EventKey") or ""
    
    if event == "subscribe":
        scene_str = event_key
        if scene_str.startswith("qrscene_"):
            scene_str = scene_str[8:]
            
        if scene_str:
            # Scanned QR code to subscribe
            redis_client = redis_manager.get_client()
            if redis_client:
                redis_client.setex(f"wx_scan_{scene_str}", 300, from_user)
            return wx_service.create_xml_reply(from_user, to_user, "操作成功！请返回网页端查看。")
        else:
            # Normal subscribe
            welcome_text = "欢迎关注上海朗湖智能科技！\n在这里您可以随时掌握设备健康状态，接收实时报警信息。"
            return wx_service.create_xml_reply(from_user, to_user, welcome_text)
            
    elif event == "SCAN":
        scene_str = event_key
        if scene_str:
            redis_client = redis_manager.get_client()
            if redis_client:
                redis_client.setex(f"wx_scan_{scene_str}", 300, from_user)
            return wx_service.create_xml_reply(from_user, to_user, "操作成功！请返回网页端查看。")
            
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
            reply_xml_str = await handle_wx_event_message(wx_service, data, from_user, to_user)
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
    ticket = await wx_service.create_qr_code(scene_str)
    
    return {
        "code": 200,
        "data": {
            "ticket": ticket,
            "scene_str": scene_str,
            "qr_url": f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={ticket}"
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
        
    wx_user_id = redis_client.get(f"wx_scan_{scene_str}")
    if wx_user_id:
        # Binding successful
        account_id_str = scene_str.split("_")[1]
        
        if not current_account.admin and str(current_account.id) != account_id_str:
            raise HTTPException(status_code=403, detail="Permission denied")
            
        # Update database
        db_account = await AuthService.get_account(session, account_id_str)
        if db_account:
            await AuthService.bind_account_wx(session, db_account, wx_user_id)
            
            # Clean up redis
            redis_client.delete(f"wx_scan_{scene_str}")
            
            return {"code": 200, "message": "success"}
    
    return {"code": 202, "message": "waiting"}

@router.get("/wx/login-qrcode")
async def get_login_qrcode():
    """Generate a QR code ticket for WeChat login"""
    wx_service = get_wx_service()
    scene_str = f"login_{uuid.uuid4().hex[:8]}"
    ticket = await wx_service.create_qr_code(scene_str)
    
    return success({
        "ticket": ticket,
        "scene_str": scene_str,
        "qr_url": f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={ticket}"
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
        
    wx_user_id = redis_client.get(f"wx_scan_{scene_str}")
    if wx_user_id:
        account = await AuthService.get_account_by_wx_user_id(session, wx_user_id)
        if not account:
            # Clean up redis
            redis_client.delete(f"wx_scan_{scene_str}")
            # Instead of HTTP error, we return 404 code so frontend can show specific message without throwing global error if possible.
            # But standard is HTTPException. Let's use it.
            raise HTTPException(status_code=404, detail="此微信号没有绑定相应平台账号")
            
        # Clean up redis
        redis_client.delete(f"wx_scan_{scene_str}")
            
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
    account_id: str
    message_text: str

@router.post("/wx/test-send-msg")
async def test_send_msg(
    req: SendMsgRequest,
    session: AsyncSession = Depends(get_session)
):
    """Test sending a customer service message to a specific user"""
    # Get account
    account = await AuthService.get_account(session, req.account_id)
    if not account or not account.wx_user_id:
        raise HTTPException(status_code=400, detail="此账号不存在或尚未绑定微信")
        
    wx_service = get_wx_service()
    try:
        await wx_service.send_custom_message(account.wx_user_id, req.message_text)
        return success({"message": "消息发送成功"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"消息发送失败: {str(e)}")
