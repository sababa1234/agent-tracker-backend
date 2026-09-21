import os
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

DB_NAME = "telemetry.db"

def init_db():
    """Initializes the SQLite database and creates the telemetry table if missing."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            imei TEXT PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            city TEXT,
            network_name TEXT,
            ip TEXT,
            timestamp REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan handler to ensure database schema readiness at launch."""
    init_db()
    yield

app = FastAPI(
    title="IMEI Cloud Telemetry Backend",
    version="1.0.0",
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
    Performs an UPSERT (insert or update on duplicate IMEI/Device ID).
    """
    client_ip = data.ip if data.ip else (request.client.host if request.client else "N/A")
    current_time = time.time()

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO telemetry (imei, latitude, longitude, city, network_name, ip, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(imei) DO UPDATE SET
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                city = excluded.city,
                network_name = excluded.network_name,
                ip = excluded.ip,
                timestamp = excluded.timestamp
        """, (data.imei, data.latitude, data.longitude, data.city, data.network_name, client_ip, current_time))
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database write error: {str(e)}")

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

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT imei, latitude, longitude, city, network_name, ip, timestamp 
        FROM telemetry WHERE imei = ?
    """, (imei,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No telemetry recorded for this device")

    return {
        "imei": row[0],
        "latitude": row[1],
        "longitude": row[2],
        "city": row[3],
        "network_name": row[4],
        "ip": row[5],
        "timestamp": row[6]
    }

@app.get("/health")
def health_check():
    """Health status check endpoint."""
    return {"status": "healthy", "database": DB_NAME}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
