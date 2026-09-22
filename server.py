import os
import time
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Column, Float, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Safely encode special characters ([ ] @) in your password
DB_USER = "postgres"
DB_PASS = quote_plus("[Cresaint@1234.]")  # Encodes to %5BCresaint%401234.%5D safely for SQLAlchemy
DB_HOST = "db.oujnywxeaptywriwobnt.supabase.co"
DB_PORT = "5432"
DB_NAME = "postgres"

DEFAULT_SUPABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SUPABASE_URL)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verifies DB connection before issuing queries
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TelemetryModel(Base):
    __tablename__ = "telemetry"
    imei = Column(String, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    city = Column(String)
    network_name = Column(String)
    ip = Column(String)
    timestamp = Column(Float, nullable=False)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Database init error: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="IMEI Cloud Telemetry Backend", version="2.0.0", lifespan=lifespan)

class TelemetryPing(BaseModel):
    imei: str = Field(..., min_length=1)
    latitude: float
    longitude: float
    city: Optional[str] = "N/A"
    network_name: Optional[str] = "N/A"
    ip: Optional[str] = None

@app.post("/api/v1/telemetry", status_code=200)
def receive_telemetry(data: TelemetryPing, request: Request):
    client_ip = data.ip if data.ip else (request.client.host if request.client else "N/A")
    current_time = time.time()

    db = SessionLocal()
    try:
        telemetry_item = TelemetryModel(
            imei=data.imei,
            latitude=data.latitude,
            longitude=data.longitude,
            city=data.city,
            network_name=data.network_name,
            ip=client_ip,
            timestamp=current_time
        )
        db.merge(telemetry_item)
        db.commit()
    except Exception as e:
        db.rollback()
        # Returns the explicit internal error to aid debugging
        raise HTTPException(status_code=500, detail=f"Database write error: {str(e)}")
    finally:
        db.close()

    return {
        "status": "success",
        "message": "Telemetry packet stored",
        "imei": data.imei,
        "timestamp": current_time
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
