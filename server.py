import os
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI(title="Agent Tracker Telemetry API")

# Automatically sanitize environment variables to prevent "Invalid URL" crashes
raw_url = os.getenv("SUPABASE_URL", "https://oujnywxeaptywriwobnt.supabase.co")
SUPABASE_URL = raw_url.strip("'\" []()").rstrip("/")

raw_key = (
    os.getenv("SUPABASE_SECRET_KEY") 
    or os.getenv("SUPABASE_KEY") 
    or "sb_secret_AREQgcbSq_Ms4UXa9upyDw_nK4t_Rkg"
)
SUPABASE_KEY = raw_key.strip("'\" []()")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as init_err:
        print(f"Supabase Client Init Error: {init_err}", flush=True)


class TelemetryPing(BaseModel):
    imei: str
    latitude: float
    longitude: float
    city: Optional[str] = "N/A"
    network_name: Optional[str] = "N/A"
    ip: Optional[str] = None


@app.get("/")
def read_root():
    return {
        "status": "online",
        "supabase_initialized": supabase is not None,
        "telemetry_endpoint": "/api/v1/telemetry",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    if not supabase:
        raise HTTPException(
            status_code=500, 
            detail="Supabase client uninitialized. Check SUPABASE_SECRET_KEY on Render."
        )
    return {"status": "healthy", "connection": "Supabase HTTPS REST API"}


@app.post("/api/v1/telemetry", status_code=200)
def receive_telemetry(data: TelemetryPing, request: Request):
    if not supabase:
        raise HTTPException(
            status_code=500, 
            detail="Database connection uninitialized. Ensure SUPABASE_SECRET_KEY is set on Render."
        )

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
        return {
            "status": "success",
            "message": "Telemetry packet stored successfully",
            "imei": data.imei,
            "timestamp": current_time
        }
    except Exception as e:
        error_msg = str(e)
        print(f"SUPABASE ERROR: {error_msg}", flush=True)
        raise HTTPException(status_code=500, detail=f"Supabase REST write error: {error_msg}")
