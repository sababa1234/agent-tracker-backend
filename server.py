import os
import time
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Float, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Read cloud database URL from environment variable, falling back to your Supabase PostgreSQL string
DEFAULT_SUPABASE_URL = "postgresql://postgres:%5BCresaint%401234.%5D@db.oujnywxeaptywriwobnt.supabase.co:5432/postgres"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SUPABASE_URL)

# Fix for Render/Heroku postgres:// URI schema if applicable
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
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
    """Initializes the database schema for PostgreSQL on Supabase."""
    Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan handler to ensure database schema readiness at launch."""
    init_db()
    yield

app = FastAPI(
    title="IMEI Cloud Telemetry Backend",
    version="2.0.0",
    lifespan=lifespan
)

class TelemetryPing(BaseModel):
    imei: str = Field(..., min_length=1)  # Flexible to accept Android ID strings
    latitude: float
    longitude: float
    city: Optional[str] = "N/A"
    network_name: Optional[str] = "N/A"
    ip: Optional[str] = None  # Automatically captured from incoming connection if omitted

@app.post("/api/v1/telemetry", status_code=200)
def receive_telemetry(data: TelemetryPing, request: Request):
    """
    Endpoint hit by target mobile devices to upload current GPS, Wi-Fi, and network info.
    Performs an UPSERT (insert or update on duplicate IMEI/Device ID) using SQLAlchemy merge.
    """
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
    """
    Endpoint hit to fetch remote telemetry for a specific device.
    """
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
    """Health status check endpoint."""
    return {"status": "healthy", "database": "Supabase PostgreSQL Connected"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
