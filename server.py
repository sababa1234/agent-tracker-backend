import os
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI(
    title="Agent Tracker Telemetry API",
    description="Backend service for tracking IMEI telemetry data using Supabase"
)

# Initialize Supabase client using environment variables configured in Render
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


class TelemetryPing(BaseModel):
    imei: str
    latitude: float
    longitude: float
    city: Optional[str] = "N/A"
    network_name: Optional[str] = "N/A"
    ip: Optional[str] = None


@app.get("/")
def read_root():
    """Root route to eliminate 404 errors on root domain access."""
    return {
        "status": "online",
        "service": "IMEI Cloud Telemetry Backend",
        "telemetry_endpoint": "/api/v1/telemetry",
        "health_endpoint": "/health",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Health status endpoint."""
    if not supabase:
        raise HTTPException(
            status_code=500, 
            detail="Supabase client not initialized. Check SUPABASE_URL and SUPABASE_KEY environment variables."
        )
    return {
        "status": "healthy",
        "connection": "Supabase HTTPS REST API"
    }


@app.post("/api/v1/telemetry", status_code=200)
def receive_telemetry(data: TelemetryPing, request: Request):
    """Receives telemetry packets from the Android app and logs them into Supabase."""
    if not supabase:
        raise HTTPException(
            status_code=500, 
            detail="Database connection uninitialized on backend server"
        )

    # Determine client IP if not provided in payload
    client_ip = data.ip if data.ip else (request.client.host if request.client else "N/A")
    current_time = time.time()

    payload = {
        "imei": data.imei,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "city": data.city or "N/A",
        "network_name": data.network_name or "N/A",
        "ip": client_ip,
        "timestamp": current_time
    }

    try:
        response = supabase.table("telemetry").upsert(payload).execute()
    except Exception as e:
        # Logs exact error to Render console for easy debugging
        print(f"SUPABASE ERROR: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Supabase REST write error: {str(e)}"
        )

    return {
        "status": "success",
        "message": "Telemetry packet stored successfully",
        "imei": data.imei,
        "timestamp": current_time
    }
