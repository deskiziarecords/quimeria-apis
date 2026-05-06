#!/usr/bin/env python3
"""
BluePyOpt Self-Tuning — Multi-objective parameter optimization.
"""
import asyncio
import time
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Callable
from datetime import datetime
import random
import numpy as np

@dataclass
class Individual:
    """One parameter set."""
    genome: Dict[str, float]  # λ thresholds, Mandra ΔE, FHT threshold, etc.
    fitness: Optional[Dict[str, float]] = None  # accuracy, latency, drawdown
    generation: int = 0
    rank: int = 0  # Pareto rank
    crowding_distance: float = 0.0

class NSGA2Optimizer:
    def __init__(self, kernel):
        self.kernel = kernel
        self.population_size = 64
        self.generations = 500
        self.current_generation = 0
        self.population: List[Individual] = []
        self.pareto_front: List[Individual] = []
        self.running = False
        self.history: List[dict] = []
        
        # Parameter bounds
        self.bounds = {
            "lambda1_threshold": (0.5, 0.8),
            "lambda3_phase": (0.785, 2.356),  # π/4 to 3π/4
            "mandra_delta_e": (0.005, 0.08),
            "fht_threshold": (0.5, 0.9),
            "kelly_fraction": (0.05, 0.5),
            "adelic_radius": (0.001, 0.05),
            "uqpce_order": (1, 5),
        }
        
    def _random_genome(self) -> Dict[str, float]:
        return {
            param: random.uniform(low, high)
            for param, (low, high) in self.bounds.items()
        }
        
    def _evaluate(self, individual: Individual) -> Dict[str, float]:
        """Evaluate individual on historical data."""
        # Apply parameters to kernel (in paper mode)
        old_params = self._get_current_params()
        self._apply_params(individual.genome)
        
        # Run backtest on last 30 days
        results = self.kernel.backtest_evaluator.run(
            start_days_ago=30,
            end_days_ago=0,
        )
        
        # Restore original params
        self._apply_params(old_params)
        
        return {
            "accuracy": results.win_rate,
            "latency_ms": results.avg_pipeline_ms,
            "max_drawdown": results.max_drawdown,
            "sharpe": results.sharpe_ratio,
            "profit_factor": results.profit_factor,
        }
        
    def _dominates(self, a: Individual, b: Individual) -> bool:
        """Check if a dominates b (minimize latency and drawdown, maximize accuracy)."""
        better_in_one = False
        for obj in ["accuracy", "latency_ms", "max_drawdown"]:
            # Note: for drawdown and latency, lower is better
            direction = -1 if obj in ["latency_ms", "max_drawdown"] else 1
            diff = direction * (a.fitness[obj] - b.fitness[obj])
            if diff > 0:
                better_in_one = True
            elif diff < 0:
                return False
        return better_in_one
        
    def _non_dominated_sort(self, population: List[Individual]) -> List[List[Individual]]:
        """NSGA-II non-dominated sorting."""
        fronts = [[]]
        for p in population:
            p.dominated_count = 0
            p.dominating_set = []
            
        for i, p in enumerate(population):
            for j, q in enumerate(population):
                if i == j:
                    continue
                if self._dominates(p, q):
                    p.dominating_set.append(j)
                elif self._dominates(q, p):
                    p.dominated_count += 1
                    
            if p.dominated_count == 0:
                p.rank = 0
                fronts[0].append(p)
                
        i = 0
        while len(fronts[i]) > 0:
            next_front = []
            for p in fronts[i]:
                for j in p.dominating_set:
                    q = population[j]
                    q.dominated_count -= 1
                    if q.dominated_count == 0:
                        q.rank = i + 1
                        next_front.append(q)
            i += 1
            fronts.append(next_front)
            
        return fronts[:-1]  # Remove empty last front
        
    def _crowding_distance(self, front: List[Individual]):
        """Calculate crowding distance for diversity."""
        if len(front) <= 2:
            for p in front:
                p.crowding_distance = float('inf')
            return
            
        for p in front:
            p.crowding_distance = 0
            
        for obj in ["accuracy", "latency_ms", "max_drawdown"]:
            front.sort(key=lambda x: x.fitness[obj])
            front[0].crowding_distance = float('inf')
            front[-1].crowding_distance = float('inf')
            
            f_min = front[0].fitness[obj]
            f_max = front[-1].fitness[obj]
            
            for i in range(1, len(front) - 1):
                distance = abs(front[i+1].fitness[obj] - front[i-1].fitness[obj])
                if f_max - f_min > 0:
                    distance /= (f_max - f_min)
                front[i].crowding_distance += distance
                
    def _tournament_select(self, population: List[Individual]) -> Individual:
        """Binary tournament selection."""
        a, b = random.sample(population, 2)
        if a.rank < b.rank:
            return a
        elif a.rank > b.rank:
            return b
        return a if a.crowding_distance > b.crowding_distance else b
        
    def _crossover(self, a: Individual, b: Individual) -> Individual:
        """Simulated binary crossover (SBX)."""
        child_genome = {}
        for param, (low, high) in self.bounds.items():
            if random.random() < 0.5:
                child_genome[param] = a.genome[param]
            else:
                child_genome[param] = b.genome[param]
        return Individual(genome=child_genome, generation=self.current_generation)
        
    def _mutate(self, individual: Individual) -> Individual:
        """Polynomial mutation."""
        for param, (low, high) in self.bounds.items():
            if random.random() < 0.1:  # 10% mutation rate
                individual.genome[param] = random.uniform(low, high)
        return individual
        
    async def run_generation(self) -> dict:
        """Execute one generation."""
        if self.current_generation == 0:
            # Initialize population
            self.population = [
                Individual(genome=self._random_genome(), generation=0)
                for _ in range(self.population_size)
            ]
            
        # Evaluate all individuals
        for ind in self.population:
            if ind.fitness is None:
                ind.fitness = self._evaluate(ind)
                await asyncio.sleep(0)  # Yield control
                
        # Non-dominated sort
        fronts = self._non_dominated_sort(self.population)
        self.pareto_front = fronts[0]
        
        # Crowding distance
        for front in fronts:
            self._crowding_distance(front)
            
        # Selection, crossover, mutation
        offspring = []
        while len(offspring) < self.population_size:
            parent1 = self._tournament_select(self.population)
            parent2 = self._tournament_select(self.population)
            child = self._crossover(parent1, parent2)
            child = self._mutate(child)
            offspring.append(child)
            
        # Environmental selection (elitism)
        combined = self.population + offspring
        fronts = self._non_dominated_sort(combined)
        
        new_population = []
        for front in fronts:
            if len(new_population) + len(front) <= self.population_size:
                new_population.extend(front)
            else:
                self._crowding_distance(front)
                front.sort(key=lambda x: -x.crowding_distance)
                remaining = self.population_size - len(new_population)
                new_population.extend(front[:remaining])
                break
                
        self.population = new_population
        self.current_generation += 1
        
        # Record history
        gen_stats = {
            "generation": self.current_generation,
            "pareto_size": len(self.pareto_front),
            "best_accuracy": max(p.fitness["accuracy"] for p in self.pareto_front),
            "best_latency_ms": min(p.fitness["latency_ms"] for p in self.pareto_front),
            "avg_drawdown": sum(p.fitness["max_drawdown"] for p in self.pareto_front) / len(self.pareto_front),
            "timestamp_ns": time.time_ns(),
        }
        self.history.append(gen_stats)
        
        return gen_stats
        
    async def run(self):
        """Full optimization loop."""
        self.running = True
        while self.running and self.current_generation < self.generations:
            await self.run_generation()
            await asyncio.sleep(0.1)  # Brief pause between gens
        self.running = False
        
    def stop(self):
        self.running = False
        
    def get_pareto_front(self) -> List[dict]:
        return [
            {
                "genome": p.genome,
                "fitness": p.fitness,
                "rank": p.rank,
                "crowding_distance": p.crowding_distance,
            }
            for p in sorted(self.pareto_front, key=lambda x: -x.fitness["accuracy"])
        ]
        
    def apply_best(self):
        """Apply best individual to kernel."""
        if not self.pareto_front:
            return None
        best = max(self.pareto_front, key=lambda x: x.fitness["accuracy"] - x.fitness["max_drawdown"])
        self._apply_params(best.genome)
        return best.genome
        
    def _get_current_params(self) -> Dict[str, float]:
        return {
            "lambda1_threshold": self.kernel.lambda_array.get_threshold("λ1"),
            "lambda3_phase": self.kernel.lambda_array.get_threshold("λ3"),
            "mandra_delta_e": self.kernel.mandra_gate.threshold,
            "fht_threshold": self.kernel.fht_engine.threshold,
            "kelly_fraction": self.kernel.position_tracker.kelly_fraction,
            "adelic_radius": self.kernel.adelic_router.radius,
            "uqpce_order": self.kernel.uqpce.current_order,
        }
        
    def _apply_params(self, params: Dict[str, float]):
        self.kernel.lambda_array.set_threshold("λ1", params["lambda1_threshold"])
        self.kernel.lambda_array.set_threshold("λ3", params["lambda3_phase"])
        self.kernel.mandra_gate.threshold = params["mandra_delta_e"]
        self.kernel.fht_engine.set_threshold(params["fht_threshold"])
        self.kernel.position_tracker.kelly_fraction = params["kelly_fraction"]
        self.kernel.adelic_router.radius = params["adelic_radius"]
        self.kernel.uqpce.set_order(int(params["uqpce_order"]))
