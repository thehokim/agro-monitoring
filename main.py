# main.py
from typing import List, Optional
from io import BytesIO
import secrets
import logging

from fastapi import (
    FastAPI, UploadFile, File, Form,
    Depends, HTTPException
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED

from minio import Minio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import AgroData, ActionLog          # <-- ваши ORM-модели

# ------------------------------------------------------------------------------
# 1) FastAPI + Basic-auth
app = FastAPI()
security = HTTPBasic()

VALID_USERNAME = "uz-kosmos"
VALID_PASSWORD = "bmvFEj9WB39GKhqzuKmb"

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

# ------------------------------------------------------------------------------
# 2) MinIO
MINIO_ENDPOINT = "192.168.20.30:9000"
BUCKET_NAME = "uploads"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=VALID_USERNAME,
    secret_key=VALID_PASSWORD,
    secure=False,
)

if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)

# ------------------------------------------------------------------------------
# 3) Postgres + SQLAlchemy
DATABASE_URL = (
    "postgresql+psycopg2://agro_user:agro_password@192.168.20.30:5434/agro_monitoring"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ------------------------------------------------------------------------------
# 4) API-энд-поинт
@app.post("/upload-agro/", dependencies=[Depends(check_credentials)])
async def upload_agro_data(
    crop_id: int = Form(...),
    maydon: str = Form(...),                         # <-- теперь строка
    ekin_turi: str = Form(...),
    update_id: int = Form(...),
    rasmlar: Optional[List[UploadFile]] = File(      # <-- теперь опционально
        None,
        description="Список файлов (может отсутствовать)"
    ),
):
    """
    Загружает список файлов `rasmlar` (может быть пустой) и сохраняет
    метаданные в Postgres + сами файлы в MinIO.
    """
    db = SessionLocal()
    uploaded, failed = [], []
    rasmlar = rasmlar or []        # если файлы не пришли – работаем с пустым списком

    try:
        for file in rasmlar:
            try:
                data = await file.read()
                minio_client.put_object(
                    BUCKET_NAME,
                    file.filename,
                    data=BytesIO(data),
                    length=len(data),
                    content_type=file.content_type,
                )
                uploaded.append(file.filename)

            except Exception as inner:
                failed.append({"file": file.filename, "error": str(inner)})

        # даже если файлов нет – фиксируем сам факт вызова
        db.add(
            AgroData(
                crop_id=crop_id,
                maydon=maydon,
                ekin_turi=ekin_turi,
                update_id=update_id,
                filename=",".join(uploaded) if uploaded else None,
            )
        )
        db.add(
            ActionLog(
                action="create",
                crop_id=crop_id,
                update_id=update_id,
                filename=",".join(uploaded) if uploaded else None,
            )
        )
        db.commit()

        return {"uploaded": uploaded, "failed": failed, "total": len(rasmlar)}

    except Exception as e:
        db.rollback()
        logging.exception(e)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    finally:
        db.close()
