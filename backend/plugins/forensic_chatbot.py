#!/usr/bin/env python3
"""
Forensic Chatbot — Natural language query interface.
"""
import re
from typing import Dict, List, Optional
from datetime import datetime

class ForensicChatbot:
    def __init__(self, kernel):
        self.kernel = kernel
        self.intents = {
            r"why (was|did) .* veto": self.explain_veto,
            r"why (was|did) .* reject": self.explain_veto,
            r"what (is|was) the (regime|state)": self.explain_regime,
            r"explain (signal|trade) .*": self.explain_signal,
            r"what (are|were) the sensors": self.explain_sensors,
            r"how (confident|sure) (are|were) we": self.explain_confidence,
            r"what happened at .*": self.explain_timestamp,
            r"show (me )?the (last|recent) .*": self.show_recent,
            r"compare .* to .*": self.compare_signals,
            r"what (would|could) happen if": self.hypothetical,
        }
        
    def query(self, question: str) -> dict:
        """Parse NL question and route to handler."""
        question_lower = question.lower().strip()
        
        for pattern, handler in self.intents.items():
            if re.search(pattern, question_lower):
                return handler(question_lower)
                
        # Fallback: keyword search in logs
        return self.fallback_search(question_lower)
        
    def explain_veto(self, q: str) -> dict:
        """Explain why a signal was vetoed."""
        # Extract signal ID if present
        match = re.search(r"(?:signal|trade|it)[\s-]+(\w+[-]?\d+)", q)
        signal_id = match.group(1) if match else "latest"
        
        if signal_id == "latest":
            veto = self.kernel.veto_log.latest()
        else:
            veto = self.kernel.veto_log.get(signal_id)
            
        if not veto:
            return {"answer": f"No veto found for {signal_id}", "sources": []}
            
        # Build explanation
        reasons = []
        if veto.get('delta_e', 0) < 0.02:
            reasons.append(f"Mandra Gate: ΔE {veto['delta_e']:.4f} below threshold 0.02")
        if veto.get('lambda3_phase', 0) > 1.57:
            reasons.append(f"Liar State: λ3 phase {veto['lambda3_phase']:.2f} > π/2")
        if not veto.get('macro_aligned', True):
            reasons.append("Macro Gate: DXY/lead asset divergence")
            
        return {
            "answer": f"Signal {signal_id} was vetoed because:\n" + "\n".join(f"• {r}" for r in reasons),
            "sources": ["mandra_kernels.py", "lambda_sensors/spectral_inversion.py"],
            "confidence": 0.95,
            "related_signals": self.kernel.signal_cache.nearby(veto['timestamp_ns']),
        }
        
    def explain_regime(self, q: str) -> dict:
        regime = self.kernel.gmos_engine.current_regime()
        return {
            "answer": f"Current regime: {regime.state_name} (probability {regime.prob:.1%}). "
                     f"Duration: {regime.duration_hours:.1f}h. "
                     f"HMM persistence: {regime.persistence:.2f}.",
            "sources": ["gmos_hmm_engine.py"],
            "confidence": regime.prob,
        }
        
    def explain_signal(self, q: str) -> dict:
        match = re.search(r"(?:signal|trade)[\s-]+(\w+[-]?\d+)", q)
        signal_id = match.group(1) if match else "latest"
        
        signal = self.kernel.signal_cache.get(signal_id)
        if not signal:
            return {"answer": f"Signal {signal_id} not found", "sources": []}
            
        return {
            "answer": f"Signal {signal_id}: {signal['direction']} {signal['symbol']} @ {signal['entry_zone']}. "
                     f"Confidence {signal['confidence']:.1%}, ΔE {signal['delta_e']:.4f}. "
                     f"Triggered by {signal['dominant_sensor']} dominance.",
            "sources": ["lambda_fusion_engine.py", "obnfe_debate_engine.py"],
            "confidence": signal['confidence'],
            "full_reasoning": signal.get('reasoning', {}),
        }
        
    def explain_sensors(self, q: str) -> dict:
        sensors = self.kernel.lambda_array.current_readings()
        return {
            "answer": "Current λ sensor array:\n" + "\n".join(
                f"• {s['id']}: {s['value']:.4f} ({s['status']}) — {s['description']}"
                for s in sensors
            ),
            "sources": ["lambda_sensors/"],
            "confidence": 0.99,
        }
        
    def explain_confidence(self, q: str) -> dict:
        uq = self.kernel.uqpce.last_result()
        return {
            "answer": f"PCE confidence interval: [{uq.ci_95_low:.5f}, {uq.ci_95_high:.5f}]. "
                     f"VaR(95%): {uq.var_95:.2f}. Signal confidence derives from "
                     f"λ7 macro alignment ({uq.sobol_lambda7:.1%} contribution).",
            "sources": ["core/kernel/uqpce_uncertainty.py"],
            "confidence": uq.confidence,
        }
        
    def explain_timestamp(self, q: str) -> dict:
        # Parse timestamp from query
        match = re.search(r"(\d{2}):(\d{2})", q)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            # Find events near this time today
            target_ns = int(datetime.utcnow().replace(hour=hour, minute=minute).timestamp() * 1e9)
        else:
            target_ns = time.time_ns() - 3600 * 1e9  # Default: 1 hour ago
            
        events = self.kernel.event_log.near(target_ns, window_ms=300000)
        return {
            "answer": f"At {datetime.fromtimestamp(target_ns/1e9).strftime('%H:%M')} UTC:\n" + "\n".join(
                f"• {e['type']}: {e['description']}" for e in events[:5]
            ),
            "sources": ["event_log"],
            "events": events,
        }
        
    def show_recent(self, q: str) -> dict:
        if "veto" in q:
            items = self.kernel.veto_log.tail(5)
            return {"answer": "Recent vetos:\n" + "\n".join(f"• {v['signal_id']}: {v['reason']}" for v in items)}
        elif "signal" in q:
            items = self.kernel.signal_cache.history(5)
            return {"answer": "Recent signals:\n" + "\n".join(f"• {s['id']}: {s['direction']} {s['symbol']}" for s in items)}
        else:
            return {"answer": "Specify what to show: vetos, signals, trades, etc."}
            
    def compare_signals(self, q: str) -> dict:
        # Extract two signal IDs
        ids = re.findall(r"(?:signal|trade)[\s-]+(\w+[-]?\d+)", q)
        if len(ids) < 2:
            return {"answer": "Need two signals to compare. Example: 'compare SIG-2847 to SIG-2848'"}
            
        s1, s2 = [self.kernel.signal_cache.get(i) for i in ids[:2]]
        if not s1 or not s2:
            return {"answer": "One or both signals not found"}
            
        return {
            "answer": f"Comparison:\n"
                     f"• Confidence: {s1['confidence']:.1%} vs {s2['confidence']:.1%}\n"
                     f"• ΔE: {s1['delta_e']:.4f} vs {s2['delta_e']:.4f}\n"
                     f"• Dominant sensor: {s1['dominant_sensor']} vs {s2['dominant_sensor']}\n"
                     f"• Outcome: {s1.get('outcome', 'N/A')} vs {s2.get('outcome', 'N/A')}",
            "similarity": self._compute_similarity(s1, s2),
        }
        
    def hypothetical(self, q: str) -> dict:
        # "What would happen if λ7 was 0.9?"
        match = re.search(r"(\w+)\s+(?:was|were)\s+([\d.]+)", q)
        if not match:
            return {"answer": "Specify parameter and value. Example: 'what if λ7 was 0.9?'"}
            
        param, value = match.group(1), float(match.group(2))
        
        # Run simulation with modified parameter
        result = self.kernel.simulator.what_if({param: value})
        
        return {
            "answer": f"If {param} = {value}:\n"
                     f"• Expected p_fused: {result['p_fused']:.4f}\n"
                     f"• Mandra would: {result['mandra_status']}\n"
                     f"• Expected PnL: ${result['expected_pnl']:.2f}",
            "simulation": result,
            "caveat": "This is a counterfactual simulation, not a prediction.",
        }
        
    def _compute_similarity(self, s1: dict, s2: dict) -> float:
        """Cosine similarity of signal feature vectors."""
        f1 = np.array([s1['confidence'], s1['delta_e'], s1.get('lambda7', 0), s1.get('lambda3', 0)])
        f2 = np.array([s2['confidence'], s2['delta_e'], s2.get('lambda7', 0), s2.get('lambda3', 0)])
        return np.dot(f1, f2) / (np.linalg.norm(f1) * np.linalg.norm(f2))
        
    def fallback_search(self, q: str) -> dict:
        """Keyword search across all logs."""
        keywords = q.split()
        results = self.kernel.decision_logger.search(keywords, limit=10)
        
        return {
            "answer": f"Found {len(results)} relevant log entries for '{' '.join(keywords)}':\n" + "\n".join(
                f"• [{datetime.fromtimestamp(r['ts']/1e9).strftime('%H:%M')}] {r['type']}: {r['summary']}"
                for r in results
            ),
            "sources": ["decision_logger", "event_log"],
            "confidence": 0.7,
        }
