#!/usr/bin/env python3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/symbolic", tags=["Symbolic Discovery"])

@router.get("/laws")
async def get_laws(min_confidence: float = 0.5, kernel=Depends(get_kernel)):
    return {"laws": kernel.symbolic_discovery.get_laws(min_confidence)}

@router.post("/discover")
async def trigger_discovery(target: str = "p_fused", max_laws: int = 5, kernel=Depends(get_kernel)):
    new_laws = kernel.symbolic_discovery.discover(target, max_laws)
    return {"discovered": len(new_laws), "laws": [l.to_dict() for l in new_laws]}

@router.get("/law/{law_id}")
async def get_law(law_id: str, kernel=Depends(get_kernel)):
    law = next((l for l in kernel.symbolic_discovery.laws if l.id == law_id), None)
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")
    return law.to_dict()

@router.post("/falsify/{law_id}")
async def falsify_law(law_id: str, kernel=Depends(get_kernel)):
    recent = kernel.data_feed.get_history(n=100)
    result = kernel.symbolic_discovery.falsify(law_id, recent)
    return result
