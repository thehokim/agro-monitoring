from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED
from minio import Minio
from io import BytesIO
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import AgroData, ActionLog
import secrets, logging

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


@app.post("/upload-agro/", dependencies=[Depends(check_credentials)])
async def upload_agro_data(
    crop_id: int = Form(...),
    maydon: str = Form(...),  # теперь строка
    ekin_turi: str = Form(...),
    update_id: int = Form(...),
    rasmlar: Optional[List[UploadFile]] = File(None, description="Список файлов"),  # необязательный
):
    db = SessionLocal()
    uploaded, failed = [], []

    # Если rasmlar пусто/None — превращаем в пустой список
    files = rasmlar or []

    try:
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

                db.add(
                    AgroData(
                        crop_id=crop_id,
                        maydon=maydon,
                        ekin_turi=ekin_turi,
                        update_id=update_id,
                        filename=file.filename,  # всегда строка, не None
                    )
                )
                db.add(
                    ActionLog(
                        action="create",
                        crop_id=crop_id,
                        update_id=update_id,
                        filename=file.filename,
                    )
                )

                uploaded.append(file.filename)

            except Exception as inner:
                failed.append({"file": file.filename, "error": str(inner)})

        # коммитим только если есть хотя бы один успешный upload
        if uploaded:
            db.commit()
        else:
            db.rollback()

        return {
            "uploaded": uploaded,
            "failed": failed,
            "total": len(files),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    finally:
        db.close()