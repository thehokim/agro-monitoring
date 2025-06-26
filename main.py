from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED
from minio import Minio
from io import BytesIO
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, AgroData, ActionLog
import secrets

# Настройка FastAPI
app = FastAPI()
security = HTTPBasic()

# Учетка для входа
VALID_USERNAME = "uz-kosmos"
VALID_PASSWORD = "bmvFEj9WB39GKhqzuKmb"

# Подключение к Minio
minio_client = Minio(
    "localhost:9000",
    access_key=VALID_USERNAME,
    secret_key=VALID_PASSWORD,
    secure=False
)

BUCKET_NAME = "uploads"
if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)

# Подключение к PostgreSQL
DATABASE_URL = "postgresql+psycopg2://agro_user:agro_password@192.168.20.30:5434/agro_monitoring"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Авторизация
def check_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if not (
        secrets.compare_digest(credentials.username, VALID_USERNAME) and
        secrets.compare_digest(credentials.password, VALID_PASSWORD)
    ):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Эндпоинт загрузки
@app.post("/upload-agro/")
async def upload_agro_data(
    crop_id: int = Form(...),
    maydon: int = Form(...),
    ekin_turi: str = Form(...),
    update_id: int = Form(...),
    rasm: UploadFile = File(...),
    username: str = Depends(check_credentials)
):
    db = SessionLocal()
    try:
        content = await rasm.read()
        file_stream = BytesIO(content)
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=rasm.filename,
            data=file_stream,
            length=len(content),
            content_type=rasm.content_type
        )

        # ⬇️ Сохраняем данные
        agro_data = AgroData(
            crop_id=crop_id,
            maydon=maydon,
            ekin_turi=ekin_turi,
            update_id=update_id,
            filename=rasm.filename
        )
        db.add(agro_data)

        # ⬇️ Добавляем лог
        log = ActionLog(
            action="create",
            crop_id=crop_id,
            update_id=update_id,
            filename=rasm.filename
        )
        db.add(log)

        db.commit()
        return {"msg": "Ma'lumotlar yuklandi", "file": rasm.filename}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()