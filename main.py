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

from models import ActionLog, AgroData

# —————— модели ответа ——————
class FailedItem(BaseModel):
    file: str
    error: str

class UploadResponse(BaseModel):
    message: str
    uploaded: List[str]
    failed: List[FailedItem]
    total: int

# —————— приложение и клиенты ——————
app = FastAPI()
security = HTTPBasic()

VALID_USERNAME = "uz-kosmos"
VALID_PASSWORD = "bmvFEj9WB39GKhqzuKmb"

minio_client = Minio(
    "192.168.20.30:9000",
    access_key=VALID_USERNAME,
    secret_key=VALID_PASSWORD,
    secure=False
)
BUCKET = "uploads"
if not minio_client.bucket_exists(BUCKET):
    minio_client.make_bucket(BUCKET)

engine = create_engine(
    "postgresql+psycopg2://agro_user:agro_password@192.168.20.30:5434/agro_monitoring"
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def check_credentials(creds: HTTPBasicCredentials = Depends(security)):
    if not (
        secrets.compare_digest(creds.username, VALID_USERNAME) and
        secrets.compare_digest(creds.password, VALID_PASSWORD)
    ):
        raise HTTPException(
            HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"}
        )
    return creds.username

# —————— сам эндпоинт ——————
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
    rasmlar: Optional[List[UploadFile]] = File(None),
):
    files = rasmlar or []
    uploaded: List[str] = []
    failed: List[FailedItem] = []
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit

    with SessionLocal() as db:
        # Сохранение базовых данных независимо от файлов
        db.add(AgroData(
            crop_id=crop_id,
            maydon=maydon,
            ekin_turi=ekin_turi,
            update_id=update_id,
            filename=None  # None если нет файла
        ))
        db.add(ActionLog(
            action="create",
            crop_id=crop_id,
            update_id=update_id,
            filename=None  # None если нет файла
        ))

        # Обработка файлов, если они есть
        for f in files:
            try:
                data = await f.read()
                if len(data) > MAX_FILE_SIZE:
                    failed.append(FailedItem(file=f.filename, error="File size exceeds 10MB limit"))
                    continue

                minio_client.put_object(
                    bucket_name=BUCKET,
                    object_name=f.filename,
                    data=BytesIO(data),
                    length=len(data),
                    content_type=f.content_type
                )

                # Обновление записи с именем файла, если файл успешно загружен
                agro_data = db.query(AgroData).filter_by(crop_id=crop_id, update_id=update_id).first()
                if agro_data:
                    agro_data.filename = f.filename
                db.add(ActionLog(
                    action="create",
                    crop_id=crop_id,
                    update_id=update_id,
                    filename=f.filename
                ))
                uploaded.append(f.filename)
            except Exception as e:
                failed.append(FailedItem(file=f.filename, error=str(e)))

        # Коммит в любом случае, так как базовые данные уже добавлены
        db.commit()
        msg = "Data saved successfully"
        if uploaded:
            msg += f", and {len(uploaded)} file(s) uploaded"
        elif failed:
            msg += f", but no files were uploaded due to errors"

    return UploadResponse(
        message=msg,
        uploaded=uploaded,
        failed=failed,
        total=len(files)
    )