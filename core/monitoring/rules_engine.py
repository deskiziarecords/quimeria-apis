# core/monitoring/rules_engine.py — ADAPTED from eToro TUI
class SMKRulesEngine:
    """
    Local rules engine for SMK alerts.
    Evaluated on every pipeline tick (not just periodic refresh).
    """
    
    RULES = {
        'concentration_limit': {
            'condition': lambda state: state['max_concentration'] > 0.25,
            'severity': 'HIGH',
            'action': 'VETO_NEW_POSITIONS'
        },
        'mirror_drawdown': {
            'condition': lambda state: state['mirror_drawdown'] > 0.10,
            'severity': 'CRITICAL',
            'action': 'HALT_MIRROR'
        },
        'position_drawdown': {
            'condition': lambda state: state['position_drawdown'] > 0.05,
            'severity': 'ELEVATED',
            'action': 'REDUCE_SIZE'
        },
        'mandra_veto_streak': {
            'condition': lambda state: state['consecutive_vetos'] > 5,
            'severity': 'WARNING',
            'action': 'SWITCH_TO_CONSERVATIVE'
        },
        'latency_degradation': {
            'condition': lambda state: state['p95_latency_ms'] > 100,
            'severity': 'HIGH',
            'action': 'ALERT_TECH'
        },
        'liar_state_frequency': {
            'condition': lambda state: state['liar_rate_1h'] > 0.3,
            'severity': 'ELEVATED',
            'action': 'WIDEN_LAMBDA3_THRESHOLD'
        }
    }
    
    def evaluate(self, state: dict) -> list:
        """
        Evaluate all rules against current SMK state.
        Returns triggered alerts.
        """
        triggered = []
        
        for rule_id, rule in self.RULES.items():
            if rule['condition'](state):
                triggered.append({
                    'rule': rule_id,
                    'severity': rule['severity'],
                    'action': rule['action'],
                    'timestamp': time.time(),
                    'state_snapshot': state
                })
        
        # Auto-actions for CRITICAL
        for alert in triggered:
            if alert['severity'] == 'CRITICAL':
                self._execute_action(alert['action'])
        
        return triggered
    
    def _execute_action(self, action: str):
        """Execute automated response"""
        actions = {
            'VETO_NEW_POSITIONS': lambda: print("VETO: New positions blocked"),
            'HALT_MIRROR': lambda: print("HALT: Mirror trading stopped"),
            'REDUCE_SIZE': lambda: print("REDUCE: Position sizes halved"),
            'SWITCH_TO_CONSERVATIVE': lambda: print("PERSONA: Switched to CONSERVATIVE"),
            'ALERT_TECH': lambda: print("ALERT: Tech team notified"),
            'WIDEN_LAMBDA3_THRESHOLD': lambda: print("CALIBRATE: λ3 threshold widened")
        }
        
        if action in actions:
            actions[action]()
