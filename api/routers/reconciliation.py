#!/usr/bin/env python3
from fastapi import APIRouter, Depends

from api.dependencies import get_kernel, verify_api_key

router = APIRouter(prefix="/api/reconciliation", tags=["Reconciliation"])

@router.get("/status")
async def get_status(kernel=Depends(get_kernel)):
    return kernel.reconciliation.get_status()

@router.get("/discrepancies")
async def get_discrepancies(kernel=Depends(get_kernel)):
    return {"discrepancies": kernel.reconciliation.get_discrepancies()}

@router.post("/run")
async def run_reconciliation(kernel=Depends(get_kernel)):
    await kernel.reconciliation.run_reconciliation()
    return kernel.reconciliation.get_status()
