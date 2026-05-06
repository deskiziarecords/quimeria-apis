#!/usr/bin/env python3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/tune", tags=["Self-Tuning"])

class StartRequest(BaseModel):
    generations: Optional[int] = None

@router.get("/status")
async def get_status(kernel=Depends(get_kernel)):
    opt = kernel.optimizer
    return {
        "running": opt.running,
        "current_generation": opt.current_generation,
        "total_generations": opt.generations,
        "population_size": opt.population_size,
        "pareto_size": len(opt.pareto_front),
        "best_delta_e": max((p.fitness["accuracy"] - p.fitness["max_drawdown"] for p in opt.pareto_front), default=0),
    }

@router.post("/start")
async def start_tuning(req: StartRequest, kernel=Depends(get_kernel)):
    if kernel.optimizer.running:
        raise HTTPException(status_code=409, detail="Optimization already running")
    if req.generations:
        kernel.optimizer.generations = req.generations
    asyncio.create_task(kernel.optimizer.run())
    return {"status": "started", "generations": kernel.optimizer.generations}

@router.post("/stop")
async def stop_tuning(kernel=Depends(get_kernel)):
    kernel.optimizer.stop()
    return {"status": "stopped", "stopped_at_generation": kernel.optimizer.current_generation}

@router.get("/pareto")
async def get_pareto(kernel=Depends(get_kernel)):
    return {"front": kernel.optimizer.get_pareto_front()}

@router.post("/apply")
async def apply_best(kernel=Depends(get_kernel)):
    genome = kernel.optimizer.apply_best()
    if not genome:
        raise HTTPException(status_code=404, detail="No Pareto front available")
    return {"applied": genome}

@router.get("/history")
async def get_history(limit: int = 500, kernel=Depends(get_kernel)):
    return {"generations": kernel.optimizer.history[-limit:]}
