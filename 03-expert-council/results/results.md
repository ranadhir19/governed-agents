# 03-expert-council: results (seed 7)

## Demo proposal verdict
- Novelty: 9/10
- Rigour: 5/10
- Feasibility: 6/10
- Impact: 5/10
- Governance-fit: 4/10
- Risk: 3/10
- mean: 5.33
- recommendation: revise
- experts routed: 6
- citations: 12

## Routing precision (24 synthetic labelled briefs, seed 123)
Limitation: briefs are generated from the same concept vocabulary the classifier uses, so scores measure routing machinery, not real-world generalisation.
- aiml: P=1.000 R=1.000 F1=1.000
- fmlm: P=0.600 R=1.000 F1=0.750
- data: P=0.333 R=1.000 F1=0.500
- gov: P=1.000 R=1.000 F1=1.000
- arch: P=0.778 R=1.000 F1=0.875
- sec: P=0.833 R=1.000 F1=0.909
- agents: P=1.000 R=1.000 F1=1.000
- mlops: P=0.286 R=1.000 F1=0.444
- mean: P=0.729 R=1.000 F1=0.810

## Cultivation (critic overall per expert)
- aiml: 0.492 -> 0.550 -> 0.608 -> 0.658 (grades Practitioner -> Senior)
- fmlm: 0.518 -> 0.577 -> 0.625 -> 0.683 (grades Practitioner -> Senior)
- data: 0.518 -> 0.577 -> 0.635 -> 0.685 (grades Practitioner -> Senior)
- gov: 0.518 -> 0.577 -> 0.635 -> 0.685 (grades Practitioner -> Senior)
- arch: 0.492 -> 0.550 -> 0.608 -> 0.658 (grades Practitioner -> Senior)
- sec: 0.492 -> 0.550 -> 0.608 -> 0.658 (grades Practitioner -> Senior)
- agents: 0.492 -> 0.550 -> 0.608 -> 0.658 (grades Practitioner -> Senior)
- mlops: 0.492 -> 0.550 -> 0.608 -> 0.658 (grades Practitioner -> Senior)

- registry entries: 30
- audit chain valid: True
