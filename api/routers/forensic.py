#!/usr/bin/env python3
from fastapi import APIRouter, WebSocket, Depends
from pydantic import BaseModel

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/forensic", tags=["Forensics"])

class ChatRequest(BaseModel):
    question: str

@router.get("/seismic")
async def get_seismic(kernel=Depends(get_kernel)):
    # P-wave, S-wave, Surface wave detection
    waves = kernel.forensic_sensors.seismic_analysis()
    return {
        "p_wave": waves.get('p', {}),
        "s_wave": waves.get('s', {}),
        "surface": waves.get('surface', {}),
        "anomaly_score": waves.get('anomaly', 0),
    }

@router.get("/spectral")
async def get_spectral_fingerprint(kernel=Depends(get_kernel)):
    # MIR spectrogram
    fingerprint = kernel.forensic_sensors.spectral_fingerprint()
    return {
        "fingerprint": fingerprint.tolist(),
        "manipulation_probability": kernel.forensic_sensors.detect_manipulation(),
        "spoofing_z_score": kernel.forensic_sensors.spoofing_z_score(),
    }

@router.post("/chat")
async def chat_forensic(req: ChatRequest, kernel=Depends(get_kernel)):
    return kernel.forensic_chatbot.query(req.question)

@router.get("/session/{session_id}")
async def get_session_report(session_id: str, kernel=Depends(get_kernel)):
    return kernel.forensic_reporter.generate_report(session_id)

@router.post("/scan")
async def run_scan(kernel=Depends(get_kernel)):
    return await kernel.forensic_sensors.full_scan()

@router.get("/alerts")
async def get_alerts(kernel=Depends(get_kernel)):
    return {"alerts": kernel.forensic_sensors.active_alerts()}
