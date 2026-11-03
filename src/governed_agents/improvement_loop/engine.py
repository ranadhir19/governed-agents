"""Improvement engine: the autonomous critic-gated loop.

A person sets the task, quality standard, budget and human gates ONCE up
front. The engine then drives propose -> critique -> diagnose -> revise ->
repeat with no per-iteration prompting.

Long-run guarantees built in:
- bounded autonomy (max iterations / budget),
- best-so-far retention,
- convergence and plateau detection (no improvement over k iterations),
- checkpoint and resume (memento pattern),
- human gates (pause for approval at configured points),
- append-only audit ledger,
- explicit termination reason: met_standard | plateau | budget_exhausted |
  halted_by_human.
"""

import copy
from dataclasses import dataclass, field

import numpy as np

from .critics import CriticPanel, build_default_panel
from .diagnostician import Diagnostician, Reviser, propose_plan
from .ledger import AuditLedger
from .checkpoints import CheckpointManager, CheckpointError
from .healing import (
    Fault,
    FaultCategory,
    Healer,
    GoalDriftMonitor,
)


class Termination:
    MET_STANDARD = "met_standard"
    PLATEAU = "plateau"
    BUDGET_EXHAUSTED = "budget_exhausted"
    HALTED_BY_HUMAN = "halted_by_human"


@dataclass
class LoopConfig:
    task: str
    quality_threshold: float = 0.85
    max_iterations: int = 12
    budget: float = 100.0
    cost_per_iteration: float = 5.0
    plateau_k: int = 3
    checkpoint_every: int = 2
    human_gates: tuple = ()
    drift_threshold: float = 0.10
    seed: int = 7


@dataclass
class RunReport:
    termination: str
    iterations_run: int
    best_score: float
    best_plan: dict
    score_history: list
    budget_spent: float
    budget_left: float
    checkpoints_taken: int
    faults: list
    healings: list
    drift_events: list
    lessons: list
    gate_decisions: list
    ledger_entries: int
    ledger_ok: bool
    monitor: list


class ImprovementEngine:
    def __init__(
        self,
        config,
        panel=None,
        proposer=None,
        reviser=None,
        approver=None,
        fault_injector=None,
        drift_injector=None,
    ):
        self.config = config
        self.panel = panel or build_default_panel()
        self.proposer = proposer or propose_plan
        self.reviser = reviser or Reviser(capability=4)
        self.diagnostician = Diagnostician()
        # approver(iteration, context) -> bool; default auto-approves (recorded)
        self.approver = approver or (lambda iteration, ctx: True)
        self.fault_injector = fault_injector  # (iteration, stage) -> Exception|None
        self.drift_injector = drift_injector  # (iteration, plan) -> plan
        self.rng = np.random.default_rng(config.seed)
        self.ledger = AuditLedger("improvement-loop")
        self.checkpoints = CheckpointManager()
        self.monitor = []
        self.healer = Healer(monitor=self.monitor)
        self.drift = GoalDriftMonitor(threshold=config.drift_threshold)
        self._candidate = None
        self._last_applied_items = []

    # -- helpers ---------------------------------------------------------
    def _emit(self, event, **detail):
        self.monitor.append({"event": event, **detail})

    def _maybe_fault(self, iteration, stage):
        if self.fault_injector is None:
            return
        exc = self.fault_injector(iteration, stage)
        if exc is not None:
            raise exc

    # -- main loop --------------------------------------------------------
    def run(self):
        cfg = self.config
        budget_left = cfg.budget
        self.ledger.append("run_started", {"task": cfg.task,
                                           "quality_threshold": cfg.quality_threshold,
                                           "budget": cfg.budget,
                                           "max_iterations": cfg.max_iterations})
        self._emit("run_started", task=cfg.task)

        self._candidate = self.proposer(cfg.task, self.rng)
        self.ledger.append("proposed", {"iteration": 0})
        self._emit("proposed", iteration=0)

        best_plan, best_score, best_critique = None, -1.0, None
        score_history = []
        since_improvement = 0
        checkpoints_taken = 0
        faults, healings, gate_decisions = [], [], []
        termination, iterations_run = None, 0

        for iteration in range(1, cfg.max_iterations + 1):
            iterations_run = iteration
            self._emit("iteration_started", iteration=iteration)

            # Human gate: pause for approval at configured points.
            if iteration in tuple(cfg.human_gates):
                ctx = {"iteration": iteration, "best_score": best_score,
                       "budget_left": budget_left}
                approved = bool(self.approver(iteration, ctx))
                gate_decisions.append({"iteration": iteration, "approved": approved})
                self.ledger.append("human_gate", {"iteration": iteration,
                                                  "approved": approved})
                self._emit("human_gate", iteration=iteration, approved=approved)
                if not approved:
                    termination = Termination.HALTED_BY_HUMAN
                    break

            # Budget gate.
            if budget_left < cfg.cost_per_iteration:
                termination = Termination.BUDGET_EXHAUSTED
                self._emit("budget_exhausted", iteration=iteration)
                break
            budget_left -= cfg.cost_per_iteration

            # Critique (faults here are quarantined + healed).
            try:
                self._maybe_fault(iteration, "critique")
                critique = self.panel.evaluate(self._candidate)
            except Exception as exc:  # noqa: BLE001
                recovered = self._handle_fault(
                    Fault(step="critique", error=exc, iteration=iteration,
                          metadata={"stage": "critique"}),
                    faults, healings)
                if not recovered:
                    termination = Termination.HALTED_BY_HUMAN
                    break
                continue

            score = critique.composite
            score_history.append(score)
            self.ledger.append("critiqued", {"iteration": iteration, "score": score,
                                             "passed_items": critique.passed_items,
                                             "total_items": critique.total_items})
            self._emit("critiqued", iteration=iteration, score=round(score, 4))

            improved = score > best_score + 1e-12
            if improved:
                best_score = score
                best_plan = copy.deepcopy(self._candidate)
                best_critique = critique
                since_improvement = 0
            else:
                since_improvement += 1

            # Goal-drift watch: pause, diagnose, re-align, resume.
            if self.drift.update(iteration, score) == "drift":
                self.ledger.append("drift_detected",
                                   self.drift.drift_events[-1])
                self._emit("drift_detected", **self.drift.drift_events[-1])
                self._realign(iteration, best_plan, best_critique)
                continue

            # Termination checks.
            if score >= cfg.quality_threshold:
                termination = Termination.MET_STANDARD
                self._emit("standard_met", iteration=iteration, score=round(score, 4))
                break
            if since_improvement >= cfg.plateau_k:
                termination = Termination.PLATEAU
                self._emit("plateau", iteration=iteration,
                           k=cfg.plateau_k, best=round(best_score, 4))
                break

            # Checkpoint (memento).
            if iteration % cfg.checkpoint_every == 0:
                ckpt = self.checkpoints.capture(
                    iteration, best_plan, best_score, self.ledger, healthy=True)
                checkpoints_taken += 1
                self.ledger.append("checkpoint", {"seq": ckpt.seq,
                                                  "iteration": iteration,
                                                  "provisional": ckpt.provisional})
                self._emit("checkpoint_taken", seq=ckpt.seq, iteration=iteration)

            # Diagnose -> revise.
            directives = self.diagnostician.diagnose(critique)
            self._emit("diagnosed", iteration=iteration,
                       directives=len(directives))
            try:
                self._maybe_fault(iteration, "revise")
                new_plan, applied = self.reviser.revise(
                    self._candidate, directives, self.rng)
                self._last_applied_items = [d.item for d in directives[:applied]]
                if self.drift_injector is not None:
                    new_plan = self.drift_injector(iteration, new_plan)
                self._candidate = new_plan
                self.ledger.append("revised", {"iteration": iteration,
                                              "directives_applied": applied})
                self._emit("revised", iteration=iteration, applied=applied)
            except Exception as exc:  # noqa: BLE001
                recovered = self._handle_fault(
                    Fault(step="revise", error=exc, iteration=iteration,
                          metadata={"stage": "revise"}),
                    faults, healings)
                if not recovered:
                    termination = Termination.HALTED_BY_HUMAN
                    break
                continue

        if termination is None:
            termination = Termination.PLATEAU  # ran out of iterations flat
        self.ledger.append("run_terminated",
                           {"reason": termination,
                            "iterations": iterations_run,
                            "best_score": best_score})
        self._emit("run_terminated", reason=termination)

        return RunReport(
            termination=termination,
            iterations_run=iterations_run,
            best_score=best_score,
            best_plan=best_plan,
            score_history=score_history,
            budget_spent=cfg.budget - budget_left,
            budget_left=budget_left,
            checkpoints_taken=checkpoints_taken,
            faults=faults,
            healings=healings,
            drift_events=list(self.drift.drift_events),
            lessons=list(self.healer.lessons),
            gate_decisions=gate_decisions,
            ledger_entries=self.ledger.count(),
            ledger_ok=self.ledger.verify(),
            monitor=list(self.monitor),
        )

    # -- fault handling ----------------------------------------------------
    def _handle_fault(self, fault, faults, healings):
        faults.append({"step": fault.step, "iteration": fault.iteration,
                       "error": str(fault.error)})
        self.ledger.append("fault", {"step": fault.step,
                                     "iteration": fault.iteration,
                                     "error": str(fault.error)})

        engine = self

        def resume_plan():
            # Reorganised plan: halve the work unit (resource strategy) and
            # re-execute from the last known-good candidate.
            reduced = Reviser(capability=max(1, engine.reviser.capability // 2))
            directives = engine.diagnostician.diagnose(
                engine.panel.evaluate(engine._candidate))
            new_plan, _ = reduced.revise(engine._candidate, directives, engine.rng)
            engine._candidate = new_plan

        def probe():
            engine.panel.evaluate(engine._candidate)
            return True

        report = self.healer.handle(
            fault, {"resume_plan": resume_plan, "probe": probe})
        healings.append(report)
        self.ledger.append("healed", {"recovered": report.recovered,
                                     "verified": report.verified,
                                     "category": report.category})
        return report.recovered

    # -- drift re-alignment --------------------------------------------------
    def _realign(self, iteration, best_plan, best_critique):
        """Pause, diagnose the regression, re-align from checkpoint, resume."""
        ckpt = self.checkpoints.latest_restorable()
        if ckpt is not None:
            try:
                payload = self.checkpoints.restore(ckpt, FaultCategory.LOGIC,
                                                   self.ledger)
                restored = payload["best_plan"]
                self._emit("drift_restored_from_checkpoint", seq=ckpt.seq)
            except CheckpointError as e:  # noqa: BLE001
                restored = copy.deepcopy(best_plan)
                self._emit("drift_restore_refused", reason=str(e))
        else:
            restored = copy.deepcopy(best_plan)
            self._emit("drift_restored_from_memory", reason="no checkpoint yet")

        # Re-sequence: skip the directives that produced the regression.
        directives = [d for d in self.diagnostician.diagnose(best_critique)
                      if d.item not in self._last_applied_items]
        new_plan, applied = self.reviser.revise(restored, directives, self.rng)
        self._candidate = new_plan
        self._last_applied_items = [d.item for d in directives[:applied]]
        self.ledger.append("drift_realigned",
                           {"iteration": iteration,
                            "directives_reapplied": applied,
                            "skipped": len(self.diagnostician.diagnose(best_critique)) - len(directives)})
        self._emit("drift_realigned", iteration=iteration, reapplied=applied)
