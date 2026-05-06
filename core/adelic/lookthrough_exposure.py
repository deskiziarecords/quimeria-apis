# core/adelic/lookthrough_exposure.py — ADAPTED from eToro TUI
class LookthroughExposureAggregator:
    """
    Aggregates total sovereign exposure across:
    - Direct positions (Schur Router)
    - Internalized matches (Internal Matching Engine)
    - Pending orders (Smart Order Splitter)
    - Synthetic hedges (Adaptive Rebalancer)
    
    "What am I actually exposed to?"
    """
    
    def __init__(self):
        self.exposures = {}  # instrument → net exposure
    
    def aggregate(self, 
                  positions: list,
                  pending_orders: list,
                  internal_book: dict,
                  hedges: list) -> dict:
        """
        True exposure = direct + pending + internal - hedges
        """
        exposure = {}
        
        # Direct positions
        for pos in positions:
            sym = pos['instrument']
            exposure[sym] = exposure.get(sym, 0) + pos['signed_exposure']
        
        # Pending orders (weighted by fill probability)
        for order in pending_orders:
            sym = order['instrument']
            prob = order.get('fill_probability', 0.5)
            exposure[sym] = exposure.get(sym, 0) + order['signed_exposure'] * prob
        
        # Internal book (matched but not yet settled)
        for sym, book in internal_book.items():
            exposure[sym] = exposure.get(sym, 0) + book['net_exposure']
        
        # Subtract hedges
        for hedge in hedges:
            sym = hedge['instrument']
            exposure[sym] = exposure.get(sym, 0) - hedge['signed_exposure']
        
        # Per-instrument breakdown
        breakdown = {}
        for sym, net in exposure.items():
            breakdown[sym] = {
                'net_exposure': net,
                'direction': 'LONG' if net > 0 else 'SHORT' if net < 0 else 'FLAT',
                'abs_exposure': abs(net),
                'concentration_pct': 0  # Will compute against total
            }
        
        # Concentration metrics
        total_abs = sum(b['abs_exposure'] for b in breakdown.values())
        for sym in breakdown:
            breakdown[sym]['concentration_pct'] = breakdown[sym]['abs_exposure'] / total_abs if total_abs > 0 else 0
        
        # Risk flags
        flags = []
        for sym, b in breakdown.items():
            if b['concentration_pct'] > 0.25:
                flags.append(f"HIGH_CONCENTRATION: {sym} {b['concentration_pct']:.1%}")
        
        return {
            'total_exposure': sum(exposure.values()),
            'gross_exposure': total_abs,
            'net_exposure': sum(exposure.values()),
            'per_instrument': breakdown,
            'risk_flags': flags,
            'diversification_score': 1.0 - max(b['concentration_pct'] for b in breakdown.values()) if breakdown else 0
        }
