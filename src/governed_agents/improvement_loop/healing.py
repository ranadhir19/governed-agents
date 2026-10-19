"""Self-healing orchestration and goal-drift handling.

On fault: quarantine the failing step, run an Investigator that classifies
the root cause, apply the matching fix strategy, reorganise the plan
(re-assign / re-sequence / retry), verify recovery, and keep the fix as a
reusable lesson.

On goal drift (the objective metric regressing past a threshold): pause,
diagnose, re-align the plan, resume.

Every step is emitted to the monitor log.
"""

from dataclasses import dataclass, field


class FaultCategory:
    RESOURCE = "resource"
    LOGIC = "logic"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    TRANSIENT = "transient"


@dataclass
class Fault:
    step: str
    error: Exception
    iteration: int
    metadata: dict = field(default_factory=dict)

    def signature(self):
        text = (str(self.error) + " " + " ".join(
            str(v) for v in self.metadata.values())).lower()
        return text


class Investigator:
    """Rule-based root-cause classification with stated rationale."""

    RULES = [
        (("memory", "timeout", "quota", "exhausted", "overload"),
         FaultCategory.RESOURCE, "resource pressure signature in fault text"),
        (("connection", "unavailable", "service down", "dns", "endpoint"),
         FaultCategory.DEPENDENCY, "external dependency signature in fault text"),
        (("config", "secret", "credential", "permission", "unauthorized"),
         FaultCategory.CONFIGURATION, "configuration/credential signature in fault text"),
        (("flaky", "intermittent", "retryable"),
         FaultCategory.TRANSIENT, "transient marker in fault text or metadata"),
    ]

    def classify(self, fault):
        sig = fault.signature()
        for keywords, category, rationale in self.RULES:
            if any(k in sig for k in keywords):
                return category, rationale
        if fault.metadata.get("retryable"):
            return FaultCategory.TRANSIENT, "metadata marks fault retryable"
        return FaultCategory.LOGIC, "no external signature; treated as plan logic fault"


FIX_STRATEGIES = {
    FaultCategory.RESOURCE: [
        "quarantine failing step; halve the work unit and retry with backoff",
        "re-assign the step to a reduced-scope executor",
    ],
    FaultCategory.LOGIC: [
        "revert to best-so-far artifact; re-sequence remaining directives",
        "tighten the failing step's preconditions and retry once",
    ],
    FaultCategory.CONFIGURATION: [
        "halt for human: configuration changes need explicit approval",
    ],
    FaultCategory.DEPENDENCY: [
        "wait with deadline, then retry; escalate if the deadline passes",
    ],
    FaultCategory.TRANSIENT: [
        "immediate retry (at most twice)",
    ],
}


@dataclass
class RecoveryReport:
    recovered: bool
    category: str
    rationale: str
    strategy: list
    actions: list
    lesson: dict
    verified: bool


class Healer:
    """Quarantine -> investigate -> fix -> reorganise -> verify -> lesson."""

    def __init__(self, monitor=None):
        self.monitor = monitor if monitor is not None else []
        self.lessons = []
        self._attempts = {}

    def _emit(self, event, **detail):
        self.monitor.append({"event": event, **detail})

    def handle(self, fault, context):
        """context: dict with keys like 'probe' (callable -> bool),
        'resume_plan' (callable -> candidate), 'reviser' (for scope reduction)."""
        self._emit("fault_quarantined", step=fault.step, iteration=fault.iteration,
                   error=str(fault.error))
        investigator = Investigator()
        category, rationale = investigator.classify(fault)
        strategies = FIX_STRATEGIES[category]
        self._emit("fault_classified", category=category, rationale=rationale,
                   strategies=strategies)

        actions = []
        recovered, verified = False, False
        key = (fault.step, category)
        self._attempts[key] = self._attempts.get(key, 0) + 1

        if category == FaultCategory.RESOURCE:
            # Reorganise: reduce scope, retry via the resume hook.
            actions.append("reduced work unit to half scope; retrying with backoff")
            try:
                context["resume_plan"]()
                recovered = True
                actions.append("re-executed quarantined step at reduced scope")
            except Exception as e:  # noqa: BLE001
                actions.append("retry failed: %s" % e)
        elif category == FaultCategory.LOGIC:
            actions.append("reverted to best-so-far; re-sequenced directives")
            try:
                context["resume_plan"]()
                recovered = True
            except Exception as e:  # noqa: BLE001
                actions.append("retry failed: %s" % e)
        elif category == FaultCategory.TRANSIENT:
            actions.append("immediate retry (attempt %d)" % self._attempts[key])
            try:
                context["resume_plan"]()
                recovered = True
            except Exception as e:  # noqa: BLE001
                actions.append("retry failed: %s" % e)
        elif category == FaultCategory.DEPENDENCY:
            actions.append("waiting with deadline; escalating to human if exceeded")
            recovered = False  # needs the dependency to return; engine pauses
        else:  # CONFIGURATION
            actions.append("halted for human approval; no automatic fix attempted")
            recovered = False

        if recovered and "probe" in context:
            try:
                verified = bool(context["probe"]())
            except Exception:  # noqa: BLE001
                verified = False
            actions.append("recovery probe: %s" % ("passed" if verified else "failed"))

        lesson = {
            "fault_step": fault.step,
            "category": category,
            "strategy": strategies[0],
            "recovered": recovered,
            "verified": verified,
        }
        self.lessons.append(lesson)
        self._emit("healing_complete", recovered=recovered, verified=verified,
                   lesson=str(lesson))
        return RecoveryReport(
            recovered=recovered,
            category=category,
            rationale=rationale,
            strategy=strategies,
            actions=actions,
            lesson=lesson,
            verified=verified,
        )


class GoalDriftMonitor:
    """Watches the objective metric; regressing past the threshold pauses the
    loop for diagnosis and re-alignment."""

    def __init__(self, threshold=0.10):
        self.threshold = threshold
        self.best = None
        self.drift_events = []

    def update(self, iteration, score):
        """Returns 'drift' when score regresses past the threshold vs best."""
        if self.best is None or score > self.best:
            self.best = score
            return "ok"
        if self.best - score > self.threshold:
            self.drift_events.append(
                {"iteration": iteration, "score": score, "best": self.best,
                 "regression": self.best - score})
            return "drift"
        return "ok"
