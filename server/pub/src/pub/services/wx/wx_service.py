import json
import logging
import hashlib
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

class WxService:
    def __init__(self, app_id: str, app_secret: str, redis_client):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redis_client = redis_client
        self._access_token_cache_key = f"wx_access_token_{app_id}"

    async def get_access_token(self) -> str:
        """Get the client credential access token for the Official Account"""
        # Try from cache
        if self.redis_client:
            token = self.redis_client.get(self._access_token_cache_key)
            if token:
                return token

        # Fetch from WeChat API
        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "access_token" in data:
                token = data["access_token"]
                expires_in = data.get("expires_in", 7200)
                # Cache token, subtract a bit from expires_in to be safe
                if self.redis_client:
                    self.redis_client.setex(self._access_token_cache_key, expires_in - 200, token)
                return token
            else:
                logger.error(f"Failed to get WeChat access token: {data}")
                raise Exception(f"WeChat API error: {data.get('errmsg')}")

    async def create_qr_code(self, scene_str: str, expire_seconds: int = 600) -> str:
        """Create a temporary parameter QR code and return the ticket URL"""
        access_token = await self.get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/qrcode/create?access_token={access_token}"
        
        payload = {
            "expire_seconds": expire_seconds,
            "action_name": "QR_STR_SCENE",
            "action_info": {
                "scene": {"scene_str": scene_str}
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "ticket" in data:
                return data["ticket"], data["url"]
            else:
                logger.error(f"Failed to create WeChat QR code: {data}")
                raise Exception(f"WeChat API error: {data.get('errmsg')}")

    async def send_custom_message(self, to_user_openid: str, text: str) -> bool:
        """Send a customer service text message to a specific user"""
        access_token = await self.get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
        
        payload = {
            "touser": to_user_openid,
            "msgtype": "text",
            "text": {
                "content": text
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("errcode") == 0:
                return True
            else:
                logger.error(f"Failed to send WeChat custom message: {data}")
                raise Exception(f"WeChat API error: {data.get('errmsg')}")

    async def send_template_message(self, to_user_openid: str, template_id: str, data: Dict[str, Any], url: Optional[str] = None, miniprogram: Optional[Dict[str, str]] = None) -> bool:
        """Send a template message to a specific user"""
        access_token = await self.get_access_token()
        api_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
        
        payload = {
            "touser": to_user_openid,
            "template_id": template_id,
            "data": data
        }
        if url:
            payload["url"] = url
        if miniprogram:
            payload["miniprogram"] = miniprogram
            
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload)
            response.raise_for_status()
            res_data = response.json()
            
            if res_data.get("errcode") == 0:
                return True
            else:
                logger.error(f"Failed to send WeChat template message: {res_data}")
                raise Exception(f"WeChat API error: {res_data.get('errmsg')}")

    @staticmethod
    def verify_signature(signature: str, timestamp: str, nonce: str, token: str = "sentinel_wx_token") -> bool:
        """Verify the WeChat server signature"""
        tmp_arr = [token, timestamp, nonce]
        tmp_arr.sort()
        tmp_str = "".join(tmp_arr)
        hash_str = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()
        return hash_str == signature

    @staticmethod
    def parse_xml_event(xml_data: bytes) -> Dict[str, str]:
        """Parse the WeChat XML message into a dictionary"""
        try:
            root = ET.fromstring(xml_data)
            result = {}
            for child in root:
                result[child.tag] = child.text
            return result
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML: {e}")
            return {}

    @staticmethod
    def create_xml_reply(to_user: str, from_user: str, content: str) -> str:
        """Create a basic text XML reply message"""
        import time
        return f"""<xml>
  <ToUserName><![CDATA[{to_user}]]></ToUserName>
  <FromUserName><![CDATA[{from_user}]]></FromUserName>
  <CreateTime>{int(time.time())}</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[{content}]]></Content>
</xml>"""
