#!/usr/bin/env python3
"""
Pipeline Checkpoint — Save/restore full kernel state.
"""
import pickle
import gzip
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import asyncio

CHECKPOINT_DIR = Path.home() / ".quimeria" / "checkpoints"

class CheckpointManager:
    def __init__(self, kernel):
        self.kernel = kernel
        self.checkpoint_dir = CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.auto_enabled = False
        self.auto_interval_min = 30
        self.max_checkpoints = 10
        
    async def save(self, name: Optional[str] = None, tags: List[str] = None) -> dict:
        """Snapshot full kernel state."""
        name = name or f"auto_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        path = self.checkpoint_dir / f"{name}.ckpt.gz"
        
        state = {
            "name": name,
            "timestamp_ns": time.time_ns(),
            "version": "1.1.0",
            "tags": tags or [],
            
            # Kernel state
            "gmos_state": self.kernel.gmos_engine.get_state(),
            "hmm_state": self.kernel.gmos_engine.hmm.get_params() if hasattr(self.kernel.gmos_engine, 'hmm') else {},
            "lambda_thresholds": self.kernel.lambda_array.get_thresholds(),
            "mandra_config": self.kernel.mandra_gate.get_config(),
            "uqpce_order": self.kernel.uqpce.current_order,
            "fht_threshold": self.kernel.fht_engine.threshold,
            
            # Memory
            "stm_snapshot": list(self.kernel.hskm.stm),
            "ltm_indices": self.kernel.hskm.get_faiss_indices(),
            
            # Positions & queue
            "positions": [p.to_dict() for p in self.kernel.position_tracker.current()],
            "action_queue": [r.to_dict() for r in self.kernel.action_center.queue],
            "action_history": [r.to_dict() for r in self.kernel.action_center.history[-100:]],
            
            # Config
            "config": self.kernel.config_manager.export(),
            
            # History (last N bars)
            "bar_history": self.kernel.data_feed.get_history(n=1000),
        }
        
        # Compress and save
        with gzip.open(path, 'wb') as f:
            pickle.dump(state, f)
            
        # Cleanup old checkpoints
        await self._cleanup()
        
        size_mb = path.stat().st_size / (1024 * 1024)
        
        self.kernel.decision_logger.log({
            "type": "CHECKPOINT",
            "name": name,
            "size_mb": size_mb,
            "timestamp_ns": time.time_ns(),
        })
        
        return {
            "name": name,
            "path": str(path),
            "size_mb": round(size_mb, 2),
            "timestamp_ns": time.time_ns(),
        }
        
    async def load(self, name: str) -> dict:
        """Restore kernel state from checkpoint."""
        path = self.checkpoint_dir / f"{name}.ckpt.gz"
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint {name} not found")
            
        with gzip.open(path, 'rb') as f:
            state = pickle.load(f)
            
        # Restore kernel state
        self.kernel.gmos_engine.set_state(state['gmos_state'])
        self.kernel.lambda_array.set_thresholds(state['lambda_thresholds'])
        self.kernel.mandra_gate.set_config(state['mandra_config'])
        self.kernel.uqpce.set_order(state['uqpce_order'])
        self.kernel.fht_engine.set_threshold(state['fht_threshold'])
        
        # Restore memory
        self.kernel.hskm.stm = state['stm_snapshot']
        self.kernel.hskm.restore_faiss_indices(state['ltm_indices'])
        
        # Restore positions (paper only — live positions from broker)
        if self.kernel.config_manager.get('paper_mode'):
            self.kernel.position_tracker.restore(state['positions'])
            
        # Restore queue
        self.kernel.action_center.queue = [
            ApprovalRequest(**r) for r in state['action_queue']
        ]
        
        self.kernel.decision_logger.log({
            "type": "CHECKPOINT_RESTORE",
            "name": name,
            "timestamp_ns": time.time_ns(),
        })
        
        return {
            "restored": name,
            "timestamp_ns": time.time_ns(),
            "from_ns": state['timestamp_ns'],
            "age_seconds": (time.time_ns() - state['timestamp_ns']) / 1e9,
        }
        
    def list(self) -> List[dict]:
        """List available checkpoints."""
        checkpoints = []
        for path in sorted(self.checkpoint_dir.glob("*.ckpt.gz"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = path.stat()
            checkpoints.append({
                "name": path.stem.replace(".ckpt", ""),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "age_hours": round((time.time() - stat.st_mtime) / 3600, 1),
            })
        return checkpoints
        
    def delete(self, name: str) -> bool:
        path = self.checkpoint_dir / f"{name}.ckpt.gz"
        if path.exists():
            path.unlink()
            return True
        return False
        
    async def _cleanup(self):
        """Keep only max_checkpoints most recent."""
        all_ckpts = sorted(self.checkpoint_dir.glob("*.ckpt.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in all_ckpts[self.max_checkpoints:]:
            old.unlink()
            
    async def auto_save_loop(self):
        """Background auto-save every N minutes."""
        while self.auto_enabled:
            await asyncio.sleep(self.auto_interval_min * 60)
            if self.auto_enabled:
                await self.save(name=f"auto_{datetime.utcnow().strftime('%H%M%S')}")
                
    def enable_auto(self, interval_min: int = 30):
        self.auto_enabled = True
        self.auto_interval_min = interval_min
        asyncio.create_task(self.auto_save_loop())
        
    def disable_auto(self):
        self.auto_enabled = False
