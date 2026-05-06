#!/usr/bin/env python3
"""
PySIPS Symbolic Law Discovery — Learn equations from data.
"""
import sympy as sp
from sympy import symbols, simplify, latex
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import random

@dataclass
class DiscoveredLaw:
    id: str
    equation: str  # SymPy string
    latex: str
    variables: List[str]
    bic: float  # Bayesian Information Criterion
    confidence: float  # 0-1
    falsifiable: bool
    falsification_attempts: int
    falsification_failures: int
    
    def to_dict(self):
        return {
            "id": self.id,
            "equation": self.equation,
            "latex": self.latex,
            "variables": self.variables,
            "bic": self.bic,
            "confidence": self.confidence,
            "falsifiable": self.falsifiable,
            "survival_rate": 1 - (self.falsification_failures / max(self.falsification_attempts, 1)),
        }

class SymbolicLawDiscovery:
    def __init__(self, kernel):
        self.kernel = kernel
        self.laws: List[DiscoveredLaw] = []
        self.max_complexity = 10  # Max nodes in expression tree
        self.operators = ['+', '-', '*', '/', '**', 'log', 'exp', 'sin', 'cos', 'tanh']
        
    def _generate_candidate(self, variables: List[str], complexity: int) -> sp.Expr:
        """Generate random symbolic expression."""
        if complexity == 0:
            # Return variable or constant
            if random.random() < 0.7:
                return sp.Symbol(random.choice(variables))
            else:
                return sp.Rational(random.randint(1, 10), random.randint(1, 10))
                
        op = random.choice(self.operators)
        
        if op in ['log', 'exp', 'sin', 'cos', 'tanh']:
            arg = self._generate_candidate(variables, complexity - 1)
            return getattr(sp, op)(arg)
        else:
            left = self._generate_candidate(variables, complexity - 1)
            right = self._generate_candidate(variables, complexity - 1)
            return getattr(sp, op)(left, right)
            
    def _fit_coefficients(self, expr: sp.Expr, data: np.ndarray, target: np.ndarray) -> Tuple[sp.Expr, float]:
        """Fit free coefficients via least squares."""
        # Extract symbols that look like coefficients (c1, c2, etc.)
        coeffs = [s for s in expr.free_symbols if str(s).startswith('c')]
        
        if not coeffs:
            # No coefficients to fit, evaluate as-is
            f = sp.lambdify([s for s in expr.free_symbols if str(s) in ['λ1', 'λ3', 'λ7', 'ATR', 'ΔE']], expr, 'numpy')
            try:
                pred = f(**{k: data[:, i] for i, k in enumerate(['λ1', 'λ3', 'λ7', 'ATR', 'ΔE'])})
                mse = np.mean((pred - target) ** 2)
            except:
                mse = float('inf')
            return expr, mse
            
        # Create numerical function
        var_names = [str(s) for s in expr.free_symbols if s not in coeffs]
        f = sp.lambdify(coeffs + [sp.Symbol(v) for v in var_names], expr, 'numpy')
        
        # Optimize coefficients
        from scipy.optimize import minimize
        def loss(c):
            try:
                pred = f(c, *[data[:, i] for i in range(len(var_names))])
                return np.mean((pred - target) ** 2)
            except:
                return float('inf')
                
        result = minimize(loss, x0=np.ones(len(coeffs)), method='Nelder-Mead')
        
        # Substitute optimized coefficients
        optimized = expr
        for i, c in enumerate(coeffs):
            optimized = optimized.subs(c, result.x[i])
            
        return optimized, result.fun
        
    def discover(self, target_variable: str = "p_fused", max_laws: int = 5) -> List[DiscoveredLaw]:
        """Discover symbolic laws from recent data."""
        # Get historical data
        data = self.kernel.data_feed.get_history(n=5000)
        
        # Prepare feature matrix
        features = ['λ1', 'λ3', 'λ7', 'ATR', 'ΔE', 'imbalance', 'funding_rate']
        X = np.array([[getattr(bar, f, 0) for f in features] for bar in data])
        y = np.array([getattr(bar, target_variable, 0) for bar in data])
        
        # Generate and test candidates
        candidates = []
        for complexity in range(2, self.max_complexity + 1):
            for _ in range(20):  # 20 candidates per complexity
                try:
                    expr = self._generate_candidate(features, complexity)
                    fitted, mse = self._fit_coefficients(expr, X, y)
                    
                    # Calculate BIC
                    n = len(y)
                    k = len([s for s in fitted.free_symbols if str(s).startswith('c')])
                    bic = n * np.log(mse + 1e-10) + k * np.log(n)
                    
                    candidates.append((fitted, bic, mse))
                except:
                    continue
                    
        # Sort by BIC, keep best
        candidates.sort(key=lambda x: x[1])
        
        new_laws = []
        for i, (expr, bic, mse) in enumerate(candidates[:max_laws]):
            law = DiscoveredLaw(
                id=f"LAW-{len(self.laws) + i + 1:04d}",
                equation=str(expr),
                latex=latex(expr),
                variables=sorted([str(s) for s in expr.free_symbols]),
                bic=bic,
                confidence=1 / (1 + np.exp((bic + 2000) / 500)),  # Sigmoid on BIC
                falsifiable=True,
                falsification_attempts=0,
                falsification_failures=0,
            )
            new_laws.append(law)
            
        self.laws.extend(new_laws)
        return new_laws
        
    def falsify(self, law_id: str, recent_data: List[dict]) -> dict:
        """Test law against recent data — Popperian falsification."""
        law = next((l for l in self.laws if l.id == law_id), None)
        if not law:
            return {"error": "Law not found"}
            
        law.falsification_attempts += 1
        
        # Evaluate law on recent data
        try:
            expr = sp.sympify(law.equation)
            f = sp.lambdify([sp.Symbol(v) for v in law.variables], expr, 'numpy')
            
            predictions = []
            actuals = []
            for bar in recent_data:
                inputs = [getattr(bar, v, 0) for v in law.variables]
                pred = f(*inputs)
                predictions.append(pred)
                actuals.append(bar.p_fused)
                
            predictions = np.array(predictions)
            actuals = np.array(actuals)
            
            # Check if predictions are within 10% of actual
            errors = np.abs(predictions - actuals) / (np.abs(actuals) + 1e-10)
            failure_rate = np.mean(errors > 0.1)
            
            if failure_rate > 0.3:  # >30% significant deviation
                law.falsification_failures += 1
                law.confidence *= 0.9
                
            return {
                "law_id": law_id,
                "tested_on": len(recent_data),
                "failure_rate": failure_rate,
                "confidence_after": law.confidence,
                "survived": failure_rate <= 0.3,
            }
            
        except Exception as e:
            law.falsification_failures += 1
            return {"error": str(e), "law_id": law_id, "survived": False}
            
    def get_laws(self, min_confidence: float = 0.5) -> List[dict]:
        return [l.to_dict() for l in self.laws if l.confidence >= min_confidence]
