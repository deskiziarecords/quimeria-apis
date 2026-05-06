#!/usr/bin/env python3
"""
HSKM — Hierarchical Sparse Kernel Memory with learned attention.
"""
import numpy as np
import faiss
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import time

@dataclass
class MemoryEntry:
    vector: np.ndarray
    metadata: dict
    timestamp_ns: int
    outcome: Optional[float]  # PnL if this was a trade, or prediction error
    salience: float = 0.0  # Computed importance

class HSKMMemory:
    def __init__(self, dim: int = 128, stm_capacity: int = 1000):
        self.dim = dim
        self.stm: List[MemoryEntry] = []  # Short-term: exact, volatile
        self.stm_capacity = stm_capacity
        
        # Long-term: FAISS index
        self.ltm_index = faiss.IndexFlatIP(dim)  # Inner product = cosine if normalized
        self.ltm_entries: List[MemoryEntry] = []
        self.ltm_count = 0
        
        # Attention parameters
        self.query_proj = np.random.randn(dim, dim) * 0.02
        self.key_proj = np.random.randn(dim, dim) * 0.02
        self.value_proj = np.random.randn(dim, dim) * 0.02
        
        # Gating
        self.transfer_threshold = 0.7  # Salience to transfer STM→LTM
        
    def _compute_salience(self, entry: MemoryEntry) -> float:
        """Novelty × Significance × Recency."""
        # Novelty: distance from nearest neighbor in LTM
        if self.ltm_count > 0:
            query = entry.vector.reshape(1, -1)
            _, distances = self.ltm_index.search(query, 1)
            novelty = 1 - distances[0][0]  # Higher distance = more novel
        else:
            novelty = 1.0
            
        # Significance: |outcome| if trade, or prediction confidence
        significance = min(abs(entry.outcome or 0) / 10000, 1.0) if entry.outcome else 0.5
        
        # Recency decay
        age_seconds = (time.time_ns() - entry.timestamp_ns) / 1e9
        recency = np.exp(-age_seconds / 3600)  # 1-hour half-life
        
        return novelty * significance * recency
        
    def add(self, vector: np.ndarray, metadata: dict, outcome: Optional[float] = None):
        """Add to STM, compute salience, trigger transfer if needed."""
        entry = MemoryEntry(
            vector=vector / np.linalg.norm(vector),  # Normalize
            metadata=metadata,
            timestamp_ns=time.time_ns(),
            outcome=outcome,
        )
        entry.salience = self._compute_salience(entry)
        
        self.stm.append(entry)
        
        # Maintain STM size
        if len(self.stm) > self.stm_capacity:
            # Remove lowest salience
            self.stm.sort(key=lambda e: e.salience)
            removed = self.stm.pop(0)
            
            # Transfer to LTM if salient enough
            if removed.salience > self.transfer_threshold:
                self._transfer_to_ltm(removed)
                
    def _transfer_to_ltm(self, entry: MemoryEntry):
        """Move from STM to long-term FAISS storage."""
        self.ltm_index.add(entry.vector.reshape(1, -1))
        self.ltm_entries.append(entry)
        self.ltm_count += 1
        
    def query_stm(self, vector: np.ndarray, k: int = 5) -> List[MemoryEntry]:
        """Exact similarity search in STM."""
        query = vector / np.linalg.norm(vector)
        similarities = [
            (np.dot(query, e.vector), e)
            for e in self.stm
        ]
        similarities.sort(reverse=True)
        return [e for _, e in similarities[:k]]
        
    def query_ltm(self, vector: np.ndarray, k: int = 5) -> List[MemoryEntry]:
        """Approximate search in LTM via FAISS."""
        query = (vector / np.linalg.norm(vector)).reshape(1, -1)
        distances, indices = self.ltm_index.search(query, k)
        
        results = []
        for idx in indices[0]:
            if idx < len(self.ltm_entries):
                results.append(self.ltm_entries[idx])
        return results
        
    def attention_forward(self, query: np.ndarray, context: List[MemoryEntry]) -> Tuple[np.ndarray, np.ndarray]:
        """Sparse attention over memory context."""
        # Project query
        q = query @ self.query_proj
        
        # Project keys and values
        keys = np.stack([e.vector @ self.key_proj for e in context])
        values = np.stack([e.vector @ self.value_proj for e in context])
        
        # Compute attention scores
        scores = q @ keys.T  # [1, seq_len]
        
        # Sparsify: keep only top-k
        k_sparse = min(10, len(context))
        top_k_idx = np.argsort(scores[0])[-k_sparse:]
        
        # Softmax over sparse set
        sparse_scores = scores[0][top_k_idx]
        sparse_scores = np.exp(sparse_scores - np.max(sparse_scores))
        sparse_scores /= sparse_scores.sum()
        
        # Weighted sum of values
        attended = np.sum(sparse_scores[:, None] * values[top_k_idx], axis=0)
        
        return attended, sparse_scores
        
    def consolidate(self):
        """Force transfer of all STM above threshold to LTM."""
        transferred = 0
        remaining = []
        for entry in self.stm:
            if entry.salience > self.transfer_threshold:
                self._transfer_to_ltm(entry)
                transferred += 1
            else:
                remaining.append(entry)
        self.stm = remaining
        return transferred
        
    def get_faiss_indices(self):
        """Export LTM index for checkpoint."""
        return faiss.serialize_index(self.ltm_index)
        
    def restore_faiss_indices(self, serialized):
        """Restore LTM from checkpoint."""
        self.ltm_index = faiss.deserialize_index(serialized)
        self.ltm_count = self.ltm_index.ntotal
