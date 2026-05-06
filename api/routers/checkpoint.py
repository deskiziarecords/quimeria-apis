#!/usr/bin/env python3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/checkpoint", tags=["Checkpoints"])

class SaveRequest(BaseModel):
    name: Optional[str] = None
    tags: Optional[List[str]] = None

class LoadRequest(BaseModel):
    name: str

@router.post("/save")
async def save_checkpoint(req: SaveRequest, kernel=Depends(get_kernel)):
    return await kernel.checkpoint_manager.save(req.name, req.tags)

@router.post("/load")
async def load_checkpoint(req: LoadRequest, kernel=Depends(get_kernel)):
    return await kernel.checkpoint_manager.load(req.name)

@router.get("/list")
async def list_checkpoints(kernel=Depends(get_kernel)):
    return {"checkpoints": kernel.checkpoint_manager.list()}

@router.delete("/{name}")
async def delete_checkpoint(name: str, kernel=Depends(get_kernel)):
    if kernel.checkpoint_manager.delete(name):
        return {"deleted": name}
    raise HTTPException(status_code=404, detail="Checkpoint not found")

@router.post("/auto-enable")
async def enable_auto(interval_min: int = 30, kernel=Depends(get_kernel)):
    kernel.checkpoint_manager.enable_auto(interval_min)
    return {"auto_save": True, "interval_min": interval_min}

@router.post("/auto-disable")
async def disable_auto(kernel=Depends(get_kernel)):
    kernel.checkpoint_manager.disable_auto()
    return {"auto_save": False}
