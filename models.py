from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy import DateTime, func
Base = declarative_base()

class AgroData(Base):
    __tablename__ = "agro_data"

    id = Column(Integer, primary_key=True, index=True)
    crop_id = Column(Integer, nullable=False)
    maydon = Column(Integer, nullable=False)
    ekin_turi = Column(String, nullable=False)
    update_id = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)  # например: "create"
    crop_id = Column(Integer, nullable=True)
    update_id = Column(Integer, nullable=True)
    filename = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
