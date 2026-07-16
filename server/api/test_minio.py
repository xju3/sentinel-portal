import requests

url = "http://124.70.210.6:9000/ota/a.1.0.2/sentinel.bin?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=root%2F20260716%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20260716T115824Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=c0a737b655ddb118a1858a266c51506ffad8d4452846c33b00e3a10515bc48fa"

res = requests.put(url, data=b"hello", headers={"Content-Type": "application/octet-stream"})
print(res.status_code)
print(res.text)
