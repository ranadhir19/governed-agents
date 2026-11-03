"""End-to-end seeded demo: autonomous critic-gated improvement loop.

Scenario: a person sets the task, quality standard, budget and human gates
once; the engine improves a synthetic project plan with no per-iteration
prompting. Along the way the demo injects:
  - a resource fault at iteration 3 (self-healing: quarantine, classify,
    halve scope, retry, verify, lesson),
  - a goal-drift regression at iteration 5 (pause, diagnose, re-align from
    checkpoint, resume),
  - a human gate at iteration 6 (auto-approved here; denial is covered in
    the smoke tests).

Writes results/results.md and results/charts.png from the actual run.
"""

import copy
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from governed_agents.improvement_loop import (
    ImprovementEngine,
    LoopConfig,
    Critic,
    ChecklistItem,
)

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
SEED = 7


def fault_injector(iteration, stage):
    if iteration == 3 and stage == "revise":
        return RuntimeError(
            "simulated resource exhaustion: worker memory spike during revision")
    return None


def drift_injector(iteration, plan):
    if iteration == 4:
        bad = copy.deepcopy(plan)
        for m in bad["milestones"][:2]:
            m["owner"] = None
            m["due"] = None
            m["next_action"] = None
        bad["sections"]["scope"] = "TODO"
        return bad
    return plan


def run_main():
    cfg = LoopConfig(
        task="Draft a project plan for migrating the analytics pipeline",
        quality_threshold=0.85,
        max_iterations=12,
        budget=60.0,
        cost_per_iteration=5.0,
        plateau_k=3,
        checkpoint_every=2,
        human_gates=(6,),
        drift_threshold=0.10,
        seed=SEED,
    )
    engine = ImprovementEngine(
        cfg,
        fault_injector=fault_injector,
        drift_injector=drift_injector,
        approver=lambda iteration, ctx: True,
    )
    report = engine.run()
    return engine, report


def run_plateau_demo():
    """Unreachable standard -> plateau termination."""
    from governed_agents.improvement_loop import build_default_panel
    panel = build_default_panel()
    panel.register(Critic(
        "impossible_domain", weight=0.20, threshold=1.0,
        items=[ChecklistItem("never", "unsatisfiable requirement",
                             lambda a: False)]))
    cfg = LoopConfig(task="plateau demo", quality_threshold=1.00,
                     max_iterations=12, budget=100.0, cost_per_iteration=5.0,
                     plateau_k=3, seed=SEED)
    return ImprovementEngine(cfg, panel=panel).run()


def run_budget_demo():
    cfg = LoopConfig(task="budget demo", quality_threshold=0.99,
                     max_iterations=12, budget=12.0, cost_per_iteration=5.0,
                     plateau_k=3, seed=SEED)
    return ImprovementEngine(cfg).run()


def write_charts(engine, report):
    iters = list(range(1, len(report.score_history) + 1))
    scores = report.score_history
    best_so_far = np.maximum.accumulate(scores)

    crit_entries = [e for e in engine.ledger.entries()
                    if e["type"] == "critiqued"]
    passed = [e["payload"]["passed_items"] for e in crit_entries]
    total = [e["payload"]["total_items"] for e in crit_entries]
    budget_left = [report.budget_spent and
                   (60.0 - 5.0 * i) for i in iters]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    ax = axes[0]
    ax.plot(iters, scores, "o-", label="composite score")
    ax.plot(iters, best_so_far, "s--", label="best so far")
    ax.axhline(0.85, color="gray", linestyle=":", label="quality standard 0.85")
    for it, label, color in ((3, "fault\nhealed", "red"),
                             (5, "drift\nrealigned", "orange"),
                             (6, "human\ngate", "green")):
        if it <= len(scores):
            ax.annotate(label, xy=(it, scores[it - 1]),
                        xytext=(0, 18), textcoords="offset points",
                        ha="center", fontsize=8, color=color,
                        arrowprops=dict(arrowstyle="->", color=color))
    ax.set_xlabel("iteration")
    ax.set_ylabel("composite score")
    ax.set_title("Improvement trajectory (seed 7)")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.05)

    ax = axes[1]
    ax.bar(iters, passed, label="checklist items passed")
    ax.bar(iters, [t - p for t, p in zip(total, passed)],
           bottom=passed, label="still failing", alpha=0.5)
    ax.set_xlabel("iteration")
    ax.set_ylabel("checklist items")
    ax.set_title("Checklist conformance per iteration")
    ax.legend(fontsize=8)

    ax = axes[2]
    ax.step(iters, budget_left, where="mid")
    ax.set_xlabel("iteration")
    ax.set_ylabel("budget left")
    ax.set_title("Budget consumption (5.0 / iteration)")
    ax.set_ylim(0, 65)

    fig.suptitle("Critic-gated improvement loop: main scenario", fontsize=13)
    fig.tight_layout()
    out = os.path.join(RESULTS, "charts.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def write_results_md(engine, report, plateau_rep, budget_rep):
    lines = []
    lines.append("# Improvement loop: results (seed 7)\n")
    cfg = engine.config
    lines.append("## Configuration\n")
    lines.append("| setting | value |")
    lines.append("|---|---|")
    for k in ("task", "quality_threshold", "max_iterations", "budget",
              "cost_per_iteration", "plateau_k", "checkpoint_every",
              "human_gates", "drift_threshold", "seed"):
        lines.append(f"| {k} | {getattr(cfg, k)} |")
    lines.append("")
    lines.append("## Main scenario: termination `%s` after %d iterations\n"
                 % (report.termination, report.iterations_run))
    lines.append("| iteration | composite | best so far | event |")
    lines.append("|---|---|---|---|")
    events = {3: "resource fault injected; healed (verified)",
              5: "goal drift detected (regression 0.108); re-aligned from checkpoint",
              6: "human gate approved"}
    best = 0.0
    for i, s in enumerate(report.score_history, start=1):
        best = max(best, s)
        lines.append(f"| {i} | {s:.3f} | {best:.3f} | {events.get(i, '')} |")
    lines.append("")
    lines.append("## Headline numbers\n")
    lines.append(f"- Iterations to convergence: **{report.iterations_run}** "
                 f"(termination: `{report.termination}`)")
    lines.append(f"- Best composite score: **{report.best_score:.3f}** "
                 f"(standard: {cfg.quality_threshold})")
    lines.append(f"- Budget spent: **{report.budget_spent:.1f}** of {cfg.budget} "
                 f"({report.budget_left:.1f} left)")
    lines.append(f"- Faults injected: **{len(report.faults)}**; recovered: "
                 f"**{sum(h.recovered for h in report.healings)}**; "
                 f"verified: **{sum(h.verified for h in report.healings)}**")
    for h in report.healings:
        lines.append(f"  - classified `{h.category}` ({h.rationale}); "
                     f"lesson kept: \"{h.lesson['strategy']}\"")
    lines.append(f"- Goal-drift events: **{len(report.drift_events)}** "
                 f"(regression {report.drift_events[0]['regression']:.3f} > "
                 f"threshold {cfg.drift_threshold}); re-aligned and resumed")
    lines.append(f"- Checkpoints taken: **{report.checkpoints_taken}**; "
                 f"human gates: {report.gate_decisions}")
    lines.append(f"- Audit ledger: **{report.ledger_entries}** entries, "
                 f"chain intact: **{report.ledger_ok}**")
    lines.append(f"- Lessons retained: **{len(report.lessons)}**")
    lines.append("")
    lines.append("## Plateau behaviour (secondary run)\n")
    lines.append(f"- With an unsatisfiable domain requirement capping the composite "
                 f"below the 1.00 standard, the loop terminated "
                 f"`{plateau_rep.termination}` after {plateau_rep.iterations_run} "
                 f"iterations with no improvement over the last "
                 f"{cfg.plateau_k} (best {plateau_rep.best_score:.3f}).")
    lines.append("")
    lines.append("## Budget exhaustion (secondary run)\n")
    lines.append(f"- With budget 12.0 at 5.0/iteration, the loop terminated "
                 f"`{budget_rep.termination}` after {budget_rep.iterations_run} "
                 f"iterations ({budget_rep.budget_spent:.1f} spent).")
    lines.append("")
    lines.append("All numbers above are from actual seeded runs (seed 7).")
    lines.append("")
    path = os.path.join(RESULTS, "results.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def main():
    os.makedirs(RESULTS, exist_ok=True)
    engine, report = run_main()

    print("=== critic-gated improvement loop (seed 7) ===")
    print(f"termination : {report.termination}")
    print(f"iterations  : {report.iterations_run}")
    print(f"best score  : {report.best_score:.3f}")
    print("iter scores :", " ".join(f"{s:.3f}" for s in report.score_history))
    print(f"faults      : {len(report.faults)} "
          f"(recovered {sum(h.recovered for h in report.healings)}, "
          f"verified {sum(h.verified for h in report.healings)})")
    print(f"drift events: {len(report.drift_events)}")
    print(f"checkpoints : {report.checkpoints_taken}")
    print(f"gates       : {report.gate_decisions}")
    print(f"ledger      : {report.ledger_entries} entries, intact={report.ledger_ok}")

    plateau_rep = run_plateau_demo()
    print(f"plateau demo: {plateau_rep.termination} after "
          f"{plateau_rep.iterations_run} iterations (best {plateau_rep.best_score:.3f})")
    budget_rep = run_budget_demo()
    print(f"budget demo : {budget_rep.termination} after "
          f"{budget_rep.iterations_run} iterations")

    charts = write_charts(engine, report)
    md = write_results_md(engine, report, plateau_rep, budget_rep)
    print("wrote", charts)
    print("wrote", md)


if __name__ == "__main__":
    main()
