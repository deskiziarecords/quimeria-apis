#!/usr/bin/env python3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Literal

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/action", tags=["Action Center"])

class ModeRequest(BaseModel):
    mode: Literal["auto", "semi", "manual"]

class ApprovalRequest(BaseModel):
    signal_id: str
    approved_by: str = "api_user"

class RejectionRequest(BaseModel):
    signal_id: str
    reason: str
    rejected_by: str = "api_user"

@router.get("/mode")
async def get_mode(kernel=Depends(get_kernel)):
    return {
        "mode": kernel.action_center.mode.value,
        "threshold_usdt": kernel.action_center.auto_threshold_usdt,
        "pending_count": len(kernel.action_center.get_pending()),
    }

@router.post("/mode")
async def set_mode(req: ModeRequest, kernel=Depends(get_kernel)):
    old = kernel.action_center.mode.value
    kernel.action_center.set_mode(req.mode)
    return {"previous": old, "current": req.mode}

@router.get("/queue")
async def get_queue(kernel=Depends(get_kernel)):
    return {"pending": kernel.action_center.get_pending()}

@router.post("/queue/{signal_id}/approve")
async def approve(signal_id: str, req: ApprovalRequest, kernel=Depends(get_kernel)):
    result = kernel.action_center.approve(signal_id, req.approved_by)
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found or already decided")
    return result

@router.post("/queue/{signal_id}/reject")
async def reject(signal_id: str, req: RejectionRequest, kernel=Depends(get_kernel)):
    result = kernel.action_center.reject(signal_id, req.reason, req.rejected_by)
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found or already decided")
    return result

@router.get("/history")
async def get_history(limit: int = 100, kernel=Depends(get_kernel)):
    return {"history": kernel.action_center.get_history(limit)}

@router.get("/stats")
async def get_stats(kernel=Depends(get_kernel)):
    return kernel.action_center.get_stats()
