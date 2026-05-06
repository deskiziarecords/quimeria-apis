#!/usr/bin/env python3
"""
Action Center — Human-in-the-loop approval for QUIMERIA SMK.
"""
import asyncio
import time
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Literal
from enum import Enum
import uuid

class Mode(Enum):
    AUTO = "auto"           # Full autonomy, no human
    SEMI_AUTO = "semi"     # Human approval for large/risky trades
    MANUAL = "manual"      # All signals queue for review

@dataclass
class ApprovalRequest:
    signal_id: str
    timestamp_ns: int
    direction: str
    symbol: str
    size: float
    entry_zone: tuple[float, float]
    stop_loss: float
    take_profit: float
    delta_e: float
    confidence: float
    risk_amount_usdt: float
    regime: str
    reasoning: dict
    
    status: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: Optional[str] = None
    approved_at_ns: Optional[int] = None
    rejection_reason: Optional[str] = None
    
    def to_dict(self):
        d = asdict(self)
        d['entry_zone'] = list(self.entry_zone)
        return d

class ActionCenter:
    def __init__(self, kernel):
        self.kernel = kernel
        self.mode = Mode.SEMI_AUTO  # Default safe
        self.queue: List[ApprovalRequest] = []
        self.history: List[ApprovalRequest] = []
        self.auto_threshold_usdt = 10000.0  # Above this, require approval in semi mode
        self.max_queue_size = 50
        
    def set_mode(self, mode: str):
        self.mode = Mode(mode)
        self.kernel.decision_logger.log({
            "type": "MODE_CHANGE",
            "old_mode": self.mode.value,
            "new_mode": mode,
            "timestamp_ns": time.time_ns(),
        })
        
    def should_queue(self, signal: dict) -> bool:
        """Determine if signal needs human approval."""
        if self.mode == Mode.AUTO:
            return False
        if self.mode == Mode.MANUAL:
            return True
        # SEMI_AUTO: check thresholds
        if signal.get('risk_amount_usdt', 0) > self.auto_threshold_usdt:
            return True
        if signal.get('delta_e', 0) < 0.03:  # Low confidence
            return True
        if signal.get('confidence', 0) < 0.75:
            return True
        return False
        
    async def submit_signal(self, signal: dict) -> dict:
        """Called by kernel after Mandra authorization."""
        request = ApprovalRequest(
            signal_id=signal['signal_id'],
            timestamp_ns=time.time_ns(),
            direction=signal['direction'],
            symbol=signal['symbol'],
            size=signal['size'],
            entry_zone=signal['entry_zone'],
            stop_loss=signal['stop_loss'],
            take_profit=signal['take_profit'],
            delta_e=signal['delta_e'],
            confidence=signal['confidence'],
            risk_amount_usdt=signal.get('risk_amount_usdt', 0),
            regime=signal.get('regime', 'UNKNOWN'),
            reasoning=signal.get('reasoning', {}),
        )
        
        if not self.should_queue(signal):
            # Auto-approve
            request.status = "approved"
            request.approved_by = "SYSTEM_AUTO"
            request.approved_at_ns = time.time_ns()
            self.history.append(request)
            return {"action": "EXECUTE", "request": request.to_dict()}
            
        # Queue for human review
        if len(self.queue) >= self.max_queue_size:
            # Drop oldest pending
            dropped = [r for r in self.queue if r.status == "pending"][0]
            dropped.status = "rejected"
            dropped.rejection_reason = "Queue overflow"
            self.history.append(dropped)
            self.queue.remove(dropped)
            
        self.queue.append(request)
        self.kernel.decision_logger.log({
            "type": "QUEUED",
            "signal_id": request.signal_id,
            "timestamp_ns": time.time_ns(),
        })
        
        return {"action": "QUEUED", "request": request.to_dict()}
        
    def approve(self, signal_id: str, approved_by: str = "cli_user") -> Optional[dict]:
        """Human approves queued signal."""
        for req in self.queue:
            if req.signal_id == signal_id and req.status == "pending":
                req.status = "approved"
                req.approved_by = approved_by
                req.approved_at_ns = time.time_ns()
                self.queue.remove(req)
                self.history.append(req)
                
                # Trigger execution
                asyncio.create_task(self._execute_approved(req))
                
                return {"status": "approved", "request": req.to_dict()}
        return None
        
    def reject(self, signal_id: str, reason: str, rejected_by: str = "cli_user") -> Optional[dict]:
        """Human rejects queued signal."""
        for req in self.queue:
            if req.signal_id == signal_id and req.status == "pending":
                req.status = "rejected"
                req.approved_by = rejected_by
                req.rejection_reason = reason
                req.approved_at_ns = time.time_ns()
                self.queue.remove(req)
                self.history.append(req)
                
                self.kernel.decision_logger.log({
                    "type": "REJECTED",
                    "signal_id": signal_id,
                    "reason": reason,
                    "timestamp_ns": time.time_ns(),
                })
                
                return {"status": "rejected", "request": req.to_dict()}
        return None
        
    async def _execute_approved(self, request: ApprovalRequest):
        """Execute approved signal through broker gateway."""
        signal = {
            'signal_id': request.signal_id,
            'direction': request.direction,
            'symbol': request.symbol,
            'size': request.size,
            'entry_zone': request.entry_zone,
            'stop_loss': request.stop_loss,
            'take_profit': request.take_profit,
            'delta_e': request.delta_e,
            'mandra': 'AUTHORIZED',
        }
        await self.kernel.execute_signal(signal)
        
    def get_pending(self) -> List[dict]:
        return [r.to_dict() for r in self.queue if r.status == "pending"]
        
    def get_history(self, limit: int = 100) -> List[dict]:
        return [r.to_dict() for r in self.history[-limit:]]
        
    def get_stats(self) -> dict:
        total = len(self.history)
        approved = len([r for r in self.history if r.status == "approved"])
        rejected = len([r for r in self.history if r.status == "rejected"])
        auto = len([r for r in self.history if r.approved_by == "SYSTEM_AUTO"])
        
        return {
            "mode": self.mode.value,
            "pending_count": len([r for r in self.queue if r.status == "pending"]),
            "total_decisions": total,
            "approved": approved,
            "rejected": rejected,
            "auto_executed": auto,
            "avg_approval_time_ms": self._avg_approval_time(),
        }
        
    def _avg_approval_time(self) -> float:
        times = [
            (r.approved_at_ns - r.timestamp_ns) / 1e6
            for r in self.history
            if r.approved_at_ns and r.approved_by != "SYSTEM_AUTO"
        ]
        return sum(times) / len(times) if times else 0
