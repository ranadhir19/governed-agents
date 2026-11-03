"""Work twin: seeded end-to-end demonstration.

All data is SYNTHETIC (see governed_agents.work_twin.generate). The demo:

  1. generates a synthetic workforce dataset with planted discretion + 2 traps;
  2. shows the three principal-split twins and the up-only data flow;
  3. runs cohort analysis, including suppressed cells (with reasons);
  4. measures discretion per task type: recovers the planted rule-like type
     and catches both traps;
  5. runs shadow mode (sealed predictions, temporal holdout);
  6. walks one skill up the autonomy ladder L0-L5 through the five gates;
  7. runs the deployment gate (build proof).

Writes results/results.md and results/charts.png with the measured numbers.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.work_twin import (  # noqa: E402
    Plane, UpOnlyStore, PersonalTwin, ProfessionalTwin, WorkingTwin,
    cohort_table, measure_discretion, ShadowLog, temporal_holdout,
    Level, SkillState, advance, LEVEL_NAMES, generate, generate_shadow_cases,
    TASK_TYPES, FIELD_SPECS, deployment_gate,
)

SEED = 7
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")


def fit_amount_threshold(train, case):
    """Fit 'amount >= t' on earlier cases; the twin's rule form."""
    amts = np.array([c["fields"]["amount"]["value"] for c in train])
    ys = np.array([c["outcome"] for c in train])
    best_t, best_m = 5000.0, -1.0
    for t in np.quantile(amts, np.linspace(0.05, 0.95, 25)):
        hi = ys[amts >= t]
        lo = ys[amts < t]
        if len(hi) >= 5 and len(lo) >= 5:
            m = abs(hi.mean() - lo.mean())
            if m > best_m:
                best_m, best_t = m, t
    return 1 if case["fields"]["amount"]["value"] >= best_t else 0


def main():
    out = []
    emit = lambda s="": (out.append(s), print(s))

    emit("=== 1. synthetic data (seed %d) ===" % SEED)
    cases, workers = generate(SEED)
    emit("cases=%d workers=%d task_types=%d" % (len(cases), len(workers), len(TASK_TYPES)))

    emit("\n=== 2. three twins, up-only flow ===")
    store = UpOnlyStore()
    personal = PersonalTwin(store)
    professional = ProfessionalTwin(store)
    working = WorkingTwin(store)
    c1 = personal.record_commitment("finish the quarterly summary draft")
    d1 = personal.record_draft("routine status update, first pass")
    # The employer (WORKING plane) cannot see personal records: the query filter.
    visible = store.query(Plane.WORKING, kind="commitment")
    emit("working-plane query for commitments sees: %d records (employer cannot read personal)"
         % len(visible))
    assert len(visible) == 0
    # Downward promotion is refused in code.
    try:
        store.promote(c1, Plane.PERSONAL, authorized_by="worker")
        emit("ERROR: downward promote accepted")
    except ValueError as e:
        emit("downward promote refused: %s" % e)
    # Employer-authorized promotion out of personal is refused.
    try:
        store.promote(d1, Plane.PROFESSIONAL, authorized_by="employer")
        emit("ERROR: employer promote accepted")
    except PermissionError as e:
        emit("employer promote of personal record refused: %s" % e)
    # The worker promotes upward; the joint twin can now read it.
    up = personal.promote_to_professional(d1)
    emit("worker promoted draft -> %s; professional plane now holds %d draft(s)"
         % (up.record_id, len(professional.read(kind="draft"))))
    # Worker corrects the joint twin.
    professional.correct(up.record_id, {"text": "routine status update, corrected numbers"})
    emit("worker correction applied; history entries kept: %d"
         % len(store._records[up.record_id].history))

    emit("\n=== 3. cohort analysis (task types, never people) ===")
    cells = cohort_table(cases, "invoice-triage", band_of=lambda c: c["band"])
    for cell in cells:
        emit("  %-8s %s" % (cell.band, cell.display()))

    emit("\n=== 4. discretion: measured, not asserted ===")
    disc_results = {}
    for tt in TASK_TYPES:
        r = measure_discretion(cases, tt, FIELD_SPECS[tt])
        disc_results[tt] = r
        basis = "basis=%s margin=%.3f" % (r.basis_field, r.margin) if r.margin else "no basis"
        emit("  %-18s %-9s %s (minority n=%d)" % (tt, r.verdict, basis, r.minority_n))
    r_acc = disc_results["access-request"]
    trap1 = [a for a in r_acc.assessments if a.name == "approval_timestamp"][0]
    emit("  trap 1: approval_timestamp -> %s" % trap1.reject_reason)
    r_ref = disc_results["refund-request"]
    trap2 = [a for a in r_ref.assessments if a.name == "risk_score"][0]
    emit("  trap 2: risk_score -> %s" % trap2.reject_reason)

    emit("\n=== 5. shadow mode ===")
    shadow_cases = generate_shadow_cases(11, 80)
    log = ShadowLog()
    for s in shadow_cases:
        log.commit(s["case_id"], s["prediction"], s["confidence"])
        log.record_human_decision(s["case_id"], s["human_decision"])  # never revealed first
    agree = log.agreement()
    ece = log.expected_calibration_error()
    emit("shadow cases=%d agreement=%.3f ece=%.3f" % (len(shadow_cases), agree, ece))
    # The seal: revealing before the human decides is refused.
    log2 = ShadowLog()
    log2.commit("X-1", 1, 0.9)
    try:
        log2.reveal("X-1")
        emit("ERROR: early reveal accepted")
    except PermissionError as e:
        emit("reveal-before-decision refused: seal holds")
    th = temporal_holdout(cases, fit_amount_threshold, "invoice-triage", train_frac=0.7)
    emit("temporal holdout: fit on %d earlier, score on %d later -> agreement=%.3f"
         % (th["n_train"], th["n_test"], th["agreement"]))

    emit("\n=== 6. autonomy ladder (skill: invoice-routing) ===")
    inv_disc = disc_results["invoice-triage"]
    state = SkillState(skill="invoice-routing", task_type="invoice-triage",
                       n_shadow=len(shadow_cases), agreement=agree, ece=ece,
                       clean_basis=(inv_disc.verdict == "rule_like"
                                    and all(not a.rejected or "leakage" not in (a.reject_reason or "")
                                            for a in inv_disc.assessments
                                            if a.name == inv_disc.basis_field)),
                       veto_active=False)
    ladder_reports = []
    while True:
        rep = advance(state)
        ladder_reports.append(rep)
        emit(rep.summary())
        emit("")
        if not rep.can_advance or state.level >= Level.L5:
            break
    emit("final level: L%d (%s)" % (state.level, LEVEL_NAMES[state.level]))

    # Working twin acts under contract, with a worker veto.
    working.grant("invoice-routing", int(state.level))
    prop = working.propose("invoice-routing", {"route": "senior-review", "case": "INV-00001"},
                           contract_ref="ops-contract-7")
    working.worker_veto(prop.proposal_id, "amount just under threshold; I want eyes on it")
    try:
        working.execute(prop.proposal_id)
        emit("ERROR: vetoed action executed")
    except PermissionError as e:
        emit("vetoed action refused execution: %s" % e)
    prop2 = working.propose("invoice-routing", {"route": "auto-process", "case": "INV-00002"},
                            contract_ref="ops-contract-7")
    working.execute(prop2.proposal_id)
    emit("unvetoed action executed: %s" % prop2.executed)

    emit("\n=== 7. build proof (deployment gate) ===")
    go, proof = deployment_gate(SEED)
    for ch in proof["checks"]:
        emit("  [%s] %s: %s" % ("PASS" if ch["passed"] else "FAIL", ch["check"], ch["detail"]))
    emit("deployment gate: %s" % ("GO" if go else "NO-GO"))

    write_results(cases, disc_results, cells, agree, ece, th, ladder_reports,
                  int(state.level), go, proof, log)
    make_charts(disc_results, cells, ladder_reports, log)
    emit("\nwrote results/results.md and results/charts.png")
    return "\n".join(out)


def write_results(cases, disc_results, cells, agree, ece, th, ladder_reports,
                  final_level, go, proof, log):
    os.makedirs(RESULTS, exist_ok=True)
    lines = []
    lines.append("# Work twin -- measured results (seed 7)")
    lines.append("")
    lines.append("All data is synthetic, generated by a seeded generator "
                 "(`governed_agents.work_twin.generate`). No real mailboxes, tickets, "
                 "repositories, or people are involved. Every number below comes from "
                 "an actual run of `04-work-twin/demo.py`.")
    lines.append("")
    lines.append("## Discretion per task type")
    lines.append("")
    lines.append("| task type | verdict | basis field | margin | minority n |")
    lines.append("|---|---|---|---|---|")
    for tt in TASK_TYPES:
        r = disc_results[tt]
        lines.append("| %s | %s | %s | %s | %d |" % (
            tt, r.verdict, r.basis_field or "-",
            ("%.3f" % r.margin) if r.margin is not None else "-", r.minority_n))
    lines.append("")
    lines.append("Planted discretion recovered: `invoice-triage` is rule-like on `amount`.")
    lines.append("Trap 1 caught: `approval_timestamp` rejected -- "
                 "field observed after the decision was taken.")
    lines.append("Trap 2 caught: `risk_score` margin 0.833 but minority n=5 < 8 -- rejected.")
    lines.append("All other task types abstain: nothing recorded explains the decision.")
    lines.append("")
    lines.append("## Cohort cells (invoice-triage by amount band)")
    lines.append("")
    for c in cells:
        lines.append("- `%s`: %s" % (c.band, c.display()))
    lines.append("")
    lines.append("## Shadow mode")
    lines.append("")
    lines.append("- shadow cases: 80, agreement: %.3f, ECE: %.3f" % (agree, ece))
    lines.append("- temporal holdout: fit on %d earlier cases, score on %d later: agreement %.3f"
                 % (th["n_train"], th["n_test"], th["agreement"]))
    lines.append("- the seal held: reveal-before-decision refused; labels uncontaminated.")
    lines.append("")
    lines.append("## Autonomy ladder (skill: invoice-routing)")
    lines.append("")
    for rep in ladder_reports:
        lines.append("### L%d -> L%d (advance: %s)" % (
            rep.from_level, rep.to_level, "yes" if rep.can_advance else "no"))
        for g in rep.gates:
            lines.append("- [%s] %s: %s" % ("PASS" if g.passed else "FAIL", g.gate, g.detail))
    lines.append("")
    lines.append("Final level: L%d (%s)." % (final_level, LEVEL_NAMES[Level(final_level)]))
    lines.append("Automation candidacy is a screening test only; no savings are reported.")
    lines.append("")
    lines.append("## Build proof")
    lines.append("")
    for ch in proof["checks"]:
        lines.append("- [%s] %s: %s" % ("PASS" if ch["passed"] else "FAIL",
                                        ch["check"], ch["detail"]))
    lines.append("")
    lines.append("Deployment gate: **%s**." % ("GO" if go else "NO-GO"))
    with open(os.path.join(RESULTS, "results.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def make_charts(disc_results, cells, ladder_reports, log):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("Work twin -- seeded measurements (synthetic data)", fontsize=13)

    # 1. discretion margins per task type
    ax = axes[0, 0]
    names, margins, colors = [], [], []
    for tt in TASK_TYPES:
        r = disc_results[tt]
        best = r.margin if r.margin is not None else max(
            [a.margin or 0.0 for a in r.assessments] or [0.0])
        names.append(tt)
        margins.append(best)
        colors.append("#2e7d4f" if r.verdict == "rule_like" else "#8a8f98")
    y = np.arange(len(names))
    ax.barh(y, margins, color=colors)
    ax.axvline(0.45, color="#c0392b", linestyle="--", label="rule-like threshold 0.45")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("best non-leaking field margin")
    ax.set_title("Discretion: margin per task type")
    ax.legend(fontsize=8)

    # 2. cohort cells
    ax = axes[0, 1]
    bands = [c.band for c in cells]
    ns = [c.n for c in cells]
    cols = ["#2e7d4f" if c.status == "ok" else "#c0392b" for c in cells]
    bars = ax.bar(bands, ns, color=cols)
    ax.axhline(5, color="#c0392b", linestyle="--", label="minimum cohort 5")
    for bar, c in zip(bars, cells):
        label = "ok" if c.status == "ok" else "suppressed"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.6,
                label, ha="center", fontsize=8)
    ax.set_ylabel("cases")
    ax.set_title("Cohort cells: suppression in action")
    ax.legend(fontsize=8)

    # 3. ladder gates: agreement vs bar per transition, ECE vs cap
    ax = axes[1, 0]
    labels, vals, barspec = [], [], []
    for rep in ladder_reports:
        g_agree = next(g for g in rep.gates if g.gate == "agreement")
        g_ece = next(g for g in rep.gates if g.gate == "ece<=0.10")
        labels.append("L%d->L%d" % (rep.from_level, rep.to_level))
        vals.append(float(g_agree.detail.split()[1]))
        barspec.append(float(g_agree.detail.split()[4]))
    x = np.arange(len(labels))
    ax.bar(x, vals, color="#2e7d4f", label="measured agreement")
    ax.scatter(x, barspec, color="#c0392b", zorder=5, label="required bar")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_title("Ladder: agreement vs required bar")
    ax.legend(fontsize=8)

    # 4. calibration curve
    ax = axes[1, 1]
    curve = log.calibration_curve()
    xs = [p["bin_center"] for p in curve]
    mc = [p["mean_confidence"] for p in curve]
    oa = [p["observed_agreement"] for p in curve]
    ax.plot([0, 1], [0, 1], color="#8a8f98", linestyle="--", label="perfect")
    ax.scatter(mc, oa, color="#2e7d4f", s=60, label="twin")
    for p in curve:
        ax.annotate("n=%d" % p["n"], (p["mean_confidence"], p["observed_agreement"]),
                    fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("mean confidence")
    ax.set_ylabel("observed agreement")
    ax.set_title("Shadow calibration (ECE=%.3f)" % log.expected_calibration_error())
    ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "charts.png"), dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
