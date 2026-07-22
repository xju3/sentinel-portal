import base64
import socket
import struct
import time
import random
import string
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import hashlib

class PKCS7Encoder:
    """PKCS7 padding for AES-CBC, WeChat uses block size 32"""
    block_size = 32

    @classmethod
    def encode(cls, text_bytes):
        text_length = len(text_bytes)
        amount_to_pad = cls.block_size - (text_length % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
        pad = bytearray([amount_to_pad] * amount_to_pad)
        return text_bytes + pad

    @classmethod
    def decode(cls, decrypted_bytes):
        pad = decrypted_bytes[-1]
        if pad < 1 or pad > cls.block_size:
            pad = 0
        return decrypted_bytes[:-pad]

class WXBizMsgCrypt:
    def __init__(self, token: str, encoding_aes_key: str, app_id: str):
        self.token = token
        self.app_id = app_id
        # WeChat encoding_aes_key is base64 string minus the trailing '='. Total 43 chars.
        self.key = base64.b64decode(encoding_aes_key + "=")
        assert len(self.key) == 32, "EncodingAESKey invalid length"

    def decrypt(self, encrypted_xml: str, msg_signature: str, timestamp: str, nonce: str) -> str:
        """Decrypts the Encrypt node in the XML and returns the plaintext XML."""
        # 1. Verify signature
        if self.get_signature(timestamp, nonce, encrypted_xml) != msg_signature:
            raise ValueError("Invalid signature")

        # 2. Decrypt
        encrypted_bytes = base64.b64decode(encrypted_xml)
        iv = self.key[:16]
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(encrypted_bytes) + decryptor.finalize()
        
        decrypted = PKCS7Encoder.decode(decrypted_padded)
        
        # 3. Parse WeChat format: 16-byte random + 4-byte length + msg + app_id
        content = decrypted[16:]
        xml_len = socket.ntohl(struct.unpack("I", content[:4])[0])
        xml_content = content[4: xml_len + 4].decode('utf-8')
        from_app_id = content[xml_len + 4:].decode('utf-8')
        
        if from_app_id != self.app_id:
            raise ValueError("Invalid AppId")
            
        return xml_content

    def encrypt(self, reply_xml: str, nonce: str, timestamp: str = None) -> dict:
        """Encrypts the reply XML and returns a dict with Encrypt, MsgSignature, TimeStamp, Nonce."""
        if timestamp is None:
            timestamp = str(int(time.time()))
            
        # 16-byte random string
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16)).encode('utf-8')
        
        xml_bytes = reply_xml.encode('utf-8')
        app_id_bytes = self.app_id.encode('utf-8')
        
        # Format: random_str + length + xml + app_id
        msg = random_str + struct.pack("I", socket.htonl(len(xml_bytes))) + xml_bytes + app_id_bytes
        padded_msg = PKCS7Encoder.encode(msg)
        
        iv = self.key[:16]
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_bytes = encryptor.update(padded_msg) + encryptor.finalize()
        
        encrypted_xml = base64.b64encode(encrypted_bytes).decode('utf-8')
        
        signature = self.get_signature(timestamp, nonce, encrypted_xml)
        
        return {
            "Encrypt": encrypted_xml,
            "MsgSignature": signature,
            "TimeStamp": timestamp,
            "Nonce": nonce
        }
        
    def generate_encrypted_xml_response(self, reply_xml: str, nonce: str, timestamp: str = None) -> str:
        """Generates the final XML string to return to WeChat."""
        encrypted_data = self.encrypt(reply_xml, nonce, timestamp)
        return f"""<xml>
<Encrypt><![CDATA[{encrypted_data['Encrypt']}]]></Encrypt>
<MsgSignature><![CDATA[{encrypted_data['MsgSignature']}]]></MsgSignature>
<TimeStamp>{encrypted_data['TimeStamp']}</TimeStamp>
<Nonce><![CDATA[{encrypted_data['Nonce']}]]></Nonce>
</xml>"""

    def get_signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        """Calculate WeChat message signature"""
        sort_list = [self.token, timestamp, nonce, encrypt]
        sort_list.sort()
        sha = hashlib.sha1()
        sha.update("".join(sort_list).encode('utf-8'))
        return sha.hexdigest()
