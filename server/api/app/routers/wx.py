import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pub.services.dependencies import get_session
from pub.services.customer_service import AuthService
from pub.services.wx_service import WxService
from app.config import settings
from app.database import redis_manager
from app.utils.auth import get_current_account
from pub.models.customer import Account

router = APIRouter(tags=["wx"])

def get_wx_service() -> WxService:
    return WxService(
        app_id=settings.wx_app_id,
        app_secret=settings.wx_app_secret,
        redis_client=redis_manager.get_client()
    )

@router.get("/wx/callback")
async def wx_callback_get(
    signature: str = Query(None),
    timestamp: str = Query(None),
    nonce: str = Query(None),
    echostr: str = Query(None)
):
    """WeChat server verification endpoint"""
    if not all([signature, timestamp, nonce, echostr]):
        return Response(content="missing parameters")
        
    wx_service = get_wx_service()
    if wx_service.verify_signature(signature, timestamp, nonce):
        return Response(content=echostr)
    else:
        return Response(content="error")

@router.post("/wx/callback")
async def wx_callback_post(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """Handle WeChat XML events"""
    xml_data = await request.body()
    wx_service = get_wx_service()
    data = wx_service.parse_xml_event(xml_data)
    
    msg_type = data.get("MsgType")
    event = data.get("Event")
    event_key = data.get("EventKey", "")
    from_user = data.get("FromUserName")
    to_user = data.get("ToUserName")
    
    # EventKey for SCAN is "scene_str". For subscribe it is "qrscene_scene_str"
    scene_str = event_key
    if event == "subscribe" and scene_str.startswith("qrscene_"):
        scene_str = scene_str[8:]
        
    if msg_type == "event" and event in ["SCAN", "subscribe"] and scene_str:
        redis_client = redis_manager.get_client()
        # if scene_str is bind_xyz, we record that the user scanned it with their from_user (wx_user_id)
        if redis_client:
            redis_client.setex(f"wx_scan_{scene_str}", 300, from_user) # Keep status for 5 mins
            
        reply_msg = wx_service.create_xml_reply(from_user, to_user, "操作成功！请返回网页端查看。")
        return Response(content=reply_msg, media_type="application/xml")
        
    return Response(content="success")

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
