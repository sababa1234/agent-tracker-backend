import os
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oujnywxeaptywriwobnt.supabase.co")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "sb_secret_AREQgcbSq_Ms4UXa9upyDw_nK4t_Rkg")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="IMEI Cloud Telemetry Backend", version="2.0.0")

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

    payload = {
        "imei": data.imei,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "city": data.city,
        "network_name": data.network_name,
        "ip": client_ip,
        "timestamp": current_time
    }

    try:
        response = supabase.table("telemetry").upsert(payload).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase REST write error: {str(e)}")

    return {
        "status": "success",
        "message": "Telemetry packet stored",
        "imei": data.imei,
        "timestamp": current_time
    }

@app.get("/api/v1/telemetry/{imei}")
def get_telemetry(imei: str):
    try:
        response = supabase.table("telemetry").select("*").eq("imei", imei).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="No telemetry recorded for this device")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase query error: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "healthy", "connection": "Supabase HTTPS REST API"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
