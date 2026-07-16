from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel

app = FastAPI()

class UploadRes(BaseModel):
    file_url: str
    object_name: str

@app.post("/test-upload")
async def test_upload(version: str = Form(...), file: UploadFile = File(...)):
    return {"version": version, "filename": file.filename}
