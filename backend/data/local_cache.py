# backend/data/local_cache.py — ADAPTED from eToro TUI
import sqlite3
import json

class SMKLocalCache:
    """
    SQLite cache for SMK state history.
    Enables equity curves, drawdowns, and longitudinal analytics
    without querying the main database.
    """
    
    def __init__(self, db_path: str = "smk_cache.db"):
        self.db = sqlite3.connect(db_path)
        self._init_schema()
    
    def _init_schema(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS smk_snapshots (
                timestamp REAL PRIMARY KEY,
                equity REAL,
                open_pnl REAL,
                hmm_regime TEXT,
                mandra_delta_e REAL,
                consciousness_score REAL,
                lambda_states TEXT,  -- JSON
                positions TEXT,      -- JSON
                alerts TEXT          -- JSON
            )
        """)
        
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                document_number TEXT,
                bar_id TEXT,
                action TEXT,
                instrument TEXT,
                size REAL,
                price REAL,
                delta_e REAL,
                mandra_passed INTEGER,
                lambda_fired TEXT,  -- JSON
                latency_ms REAL
            )
        """)
        
        self.db.commit()
    
    def snapshot(self, state: dict):
        """Store current SMK state"""
        self.db.execute("""
            INSERT INTO smk_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            state.get('equity'),
            state.get('open_pnl'),
            state.get('hmm_regime'),
            state.get('mandra_delta_e'),
            state.get('consciousness_score'),
            json.dumps(state.get('lambda_states', {})),
            json.dumps(state.get('positions', [])),
            json.dumps(state.get('alerts', []))
        ))
        self.db.commit()
    
    def get_equity_curve(self, hours: int = 24) -> list:
        """Fetch equity history for sparkline"""
        cursor = self.db.execute("""
            SELECT timestamp, equity FROM smk_snapshots
            WHERE timestamp > ?
            ORDER BY timestamp
        """, (time.time() - hours * 3600,))
        
        return [{'timestamp': r[0], 'equity': r[1]} for r in cursor.fetchall()]
