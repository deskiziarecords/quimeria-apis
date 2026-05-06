#!/usr/bin/env python3
"""
Three-Way Reconciliation — Signal / Execution / Settlement.
"""
import time
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime

@dataclass
class ReconciliationEntry:
    signal_id: str
    timestamp_ns: int
    
    # Signal side (SMK)
    signal_direction: str
    signal_symbol: str
    signal_size: float
    signal_price: float
    
    # Execution side (Broker)
    execution_order_id: Optional[str]
    execution_status: Optional[str]  # filled, partial, rejected
    execution_avg_price: Optional[float]
    execution_filled_size: Optional[float]
    execution_timestamp_ns: Optional[int]
    
    # Settlement side (Ledger)
    ledger_entry_id: Optional[str]
    ledger_realized_pnl: Optional[float]
    ledger_fee: Optional[float]
    ledger_settled: bool = False
    
    # Match status
    status: str = "pending"  # pending, matched, discrepancy

class ThreeWayMatch:
    def __init__(self, kernel):
        self.kernel = kernel
        self.entries: Dict[str, ReconciliationEntry] = {}
        
    def register_signal(self, signal: dict):
        """Called when SMK generates a signal."""
        entry = ReconciliationEntry(
            signal_id=signal['signal_id'],
            timestamp_ns=time.time_ns(),
            signal_direction=signal['direction'],
            signal_symbol=signal['symbol'],
            signal_size=signal['size'],
            signal_price=signal.get('entry_price', 0),
            execution_order_id=None,
            execution_status=None,
            execution_avg_price=None,
            execution_filled_size=None,
            execution_timestamp_ns=None,
            ledger_entry_id=None,
            ledger_realized_pnl=None,
            ledger_fee=None,
        )
        self.entries[signal['signal_id']] = entry
        
    def register_execution(self, signal_id: str, execution: dict):
        """Called on broker fill notification."""
        if signal_id not in self.entries:
            return  # Orphan execution
            
        entry = self.entries[signal_id]
        entry.execution_order_id = execution.get('order_id')
        entry.execution_status = execution.get('status')
        entry.execution_avg_price = execution.get('avg_price')
        entry.execution_filled_size = execution.get('filled_size')
        entry.execution_timestamp_ns = time.time_ns()
        
        self._check_match(entry)
        
    def register_settlement(self, signal_id: str, ledger: dict):
        """Called on ledger update."""
        if signal_id not in self.entries:
            return
            
        entry = self.entries[signal_id]
        entry.ledger_entry_id = ledger.get('entry_id')
        entry.ledger_realized_pnl = ledger.get('realized_pnl')
        entry.ledger_fee = ledger.get('fee')
        entry.ledger_settled = True
        
        self._check_match(entry)
        
    def _check_match(self, entry: ReconciliationEntry):
        """Verify all three sides agree."""
        discrepancies = []
        
        # Signal vs Execution
        if entry.execution_status == "filled":
            if abs(entry.signal_size - (entry.execution_filled_size or 0)) > 0.0001:
                discrepancies.append("SIZE_MISMATCH")
            if abs(entry.signal_price - (entry.execution_avg_price or 0)) > 0.00001:
                discrepancies.append("PRICE_SLIPPAGE")
                
        # Execution vs Settlement
        if entry.ledger_settled and entry.execution_status == "filled":
            if entry.ledger_entry_id is None:
                discrepancies.append("MISSING_LEDGER")
                
        entry.status = "discrepancy" if discrepancies else "matched"
        
        if discrepancies:
            self.kernel.decision_logger.log({
                "type": "RECONCILIATION_DISCREPANCY",
                "signal_id": entry.signal_id,
                "discrepancies": discrepancies,
                "timestamp_ns": time.time_ns(),
            })
            
    def get_status(self) -> dict:
        total = len(self.entries)
        matched = sum(1 for e in self.entries.values() if e.status == "matched")
        discrepancies = sum(1 for e in self.entries.values() if e.status == "discrepancy")
        pending = total - matched - discrepancies
        
        return {
            "total_signals": total,
            "matched": matched,
            "discrepancies": discrepancies,
            "pending": pending,
            "match_rate": matched / total if total > 0 else 0,
            "last_reconciled_ns": max((e.execution_timestamp_ns or 0 for e in self.entries.values()), default=0),
        }
        
    def get_discrepancies(self) -> List[dict]:
        return [
            {
                "signal_id": e.signal_id,
                "symbol": e.signal_symbol,
                "issues": [d for d in ["SIZE_MISMATCH", "PRICE_SLIPPAGE", "MISSING_LEDGER"] if d in str(e.__dict__)],
                "signal_price": e.signal_price,
                "execution_price": e.execution_avg_price,
                "age_seconds": (time.time_ns() - e.timestamp_ns) / 1e9,
            }
            for e in self.entries.values()
            if e.status == "discrepancy"
        ]
        
    async def run_reconciliation(self):
        """Manual full reconciliation sweep."""
        # Re-query broker for all open orders
        # Re-query ledger for all unsettled entries
        # Match everything
        pass
