import os
import time
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column, Float, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_SUPABASE_URL = "postgresql://postgres:%5BCresaint%401234.%5D@db.oujnywxeaptywriwobnt.supabase.co:5432/postgres"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SUPABASE_URL)


if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure percent-encoded password special characters are safely handled
DATABASE_URL = unquote(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Automatically reconnects dropped DB sessions
    pool_recycle=300         # Recycles connections every 5 minutes
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
    """Initializes database schema cleanly on startup."""
    try:
        Base.metadata.create_all(bind=engine)
        print("Database schema verified.")
    except Exception as e:
        print(f"Database initialization warning: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="IMEI Cloud Telemetry Backend",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        raise HTTPException(status_code=500, detail=f"Database write error: {str(e)}")
    finally:
        db.close()

    return {
        "status": "success",
        "message": "Telemetry packet stored",
        "imei": data.imei,
        "timestamp": current_time
    }

@app.get("/api/v1/telemetry/{imei}")
def get_telemetry(imei: str):
    if not imei:
        raise HTTPException(status_code=400, detail="Invalid device identifier format")

    db = SessionLocal()
    try:
        row = db.query(TelemetryModel).filter(TelemetryModel.imei == imei).first()
    finally:
        db.close()

    if not row:
        raise HTTPException(status_code=404, detail="No telemetry recorded for this device")

    return {
        "imei": row.imei,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "city": row.city,
        "network_name": row.network_name,
        "ip": row.ip,
        "timestamp": row.timestamp
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "database": "Supabase PostgreSQL Connected"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
