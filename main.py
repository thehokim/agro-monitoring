from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from starlette.status import HTTP_401_UNAUTHORIZED
from minio import Minio
from io import BytesIO
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import secrets

# ————————— response models —————————
class FailedItem(BaseModel):
    file: str
    error: str

class UploadResponse(BaseModel):
    message: str                 # новое поле
    uploaded: List[str]
    failed: List[FailedItem]
    total: int

# ————————— app setup —————————
app = FastAPI()
security = HTTPBasic()
VALID_USERNAME = "uz-kosmos"
VALID_PASSWORD = "bmvFEj9WB39GKhqzuKmb"

minio_client = Minio(
    "192.168.20.30:9000",
    access_key=VALID_USERNAME,
    secret_key=VALID_PASSWORD,
    secure=False,
)
BUCKET_NAME = "uploads"
if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)

engine = create_engine(
    "postgresql+psycopg2://agro_user:agro_password@192.168.20.30:5434/agro_monitoring"
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def check_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if not (
        secrets.compare_digest(credentials.username, VALID_USERNAME)
        and secrets.compare_digest(credentials.password, VALID_PASSWORD)
    ):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ————————— endpoint с response_model —————————
@app.post(
    "/upload-agro/",
    response_model=UploadResponse,
    dependencies=[Depends(check_credentials)]
)
async def upload_agro_data(
    crop_id: int = Form(...),
    maydon: str = Form(...),
    ekin_turi: str = Form(...),
    update_id: int = Form(...),
    rasmlar: Optional[List[UploadFile]] = File(None, description="Список файлов"),
):
    db = SessionLocal()
    uploaded: List[str] = []
    failed: List[FailedItem] = []

    files = rasmlar or []

    for file in files:
        try:
            content = await file.read()
            minio_client.put_object(
                bucket_name=BUCKET_NAME,
                object_name=file.filename,
                data=BytesIO(content),
                length=len(content),
                content_type=file.content_type,
            )
            # здесь сохраняйте в БД, если нужно…
            uploaded.append(file.filename)
        except Exception as e:
            failed.append(FailedItem(file=file.filename, error=str(e)))

    if uploaded:
        db.commit()
        msg = f"Successfully sent {len(uploaded)} file(s)"
    else:
        db.rollback()
        msg = "No files were uploaded"

    db.close()

    return UploadResponse(
        message=msg,
        uploaded=uploaded,
        failed=failed,
        total=len(files)
    )
