#!/usr/bin/env python3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import numpy as np

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/memory", tags=["HSKM Memory"])

class QueryRequest(BaseModel):
    vector: list[float]
    k: int = 5

class SearchRequest(BaseModel):
    text: str
    k: int = 5

@router.get("/stm")
async def get_stm(limit: int = 20, kernel=Depends(get_kernel)):
    stm = kernel.hskm.stm[-limit:]
    return {
        "count": len(kernel.hskm.stm),
        "capacity": kernel.hskm.stm_capacity,
        "fill_pct": len(kernel.hskm.stm) / kernel.hskm.stm_capacity * 100,
        "entries": [
            {
                "timestamp_ns": e.timestamp_ns,
                "metadata": e.metadata,
                "salience": e.salience,
                "outcome": e.outcome,
            }
            for e in stm
        ],
    }

@router.post("/stm/query")
async def query_stm(req: QueryRequest, kernel=Depends(get_kernel)):
    vector = np.array(req.vector)
    results = kernel.hskm.query_stm(vector, req.k)
    return {"results": [{"metadata": r.metadata, "salience": r.salience} for r in results]}

@router.get("/ltm")
async def get_ltm(kernel=Depends(get_kernel)):
    return {
        "count": kernel.hskm.ltm_count,
        "index_size": kernel.hskm.ltm_index.ntotal,
    }

@router.post("/ltm/search")
async def search_ltm(req: SearchRequest, kernel=Depends(get_kernel)):
    # Convert text to vector via embedding
    vector = kernel.embedding_model.encode(req.text)
    results = kernel.hskm.query_ltm(vector, req.k)
    return {"results": [{"metadata": r.metadata, "salience": r.salience} for r in results]}

@router.post("/consolidate")
async def consolidate_memory(kernel=Depends(get_kernel)):
    transferred = kernel.hskm.consolidate()
    return {"transferred_to_ltm": transferred, "stm_remaining": len(kernel.hskm.stm)}

@router.get("/attention")
async def get_attention(kernel=Depends(get_kernel)):
    # Return current attention weights from last forward pass
    return {"attention": kernel.hskm.last_attention.tolist() if hasattr(kernel.hskm, 'last_attention') else []}

@router.post("/attention/reset")
async def reset_attention(kernel=Depends(get_kernel)):
    kernel.hskm.query_proj = np.random.randn(kernel.hskm.dim, kernel.hskm.dim) * 0.02
    return {"status": "reset"}

@router.get("/salience")
async def get_salience(limit: int = 20, kernel=Depends(get_kernel)):
    recent = sorted(kernel.hskm.stm, key=lambda e: e.timestamp_ns, reverse=True)[:limit]
    return {"entries": [{"timestamp_ns": e.timestamp_ns, "salience": e.salience} for e in recent]}
