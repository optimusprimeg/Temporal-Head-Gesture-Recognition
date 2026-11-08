# Feature screening rule

Version 2, 2026-11-06. Written after seeing the EarSet results below, and fixed **before any pilot or main-round
data**: the same untouched script decides on our data, so the choice cannot be tuned to our results. (It was not
fixed before EarSet; do not claim that.) Version 1 differed only in rule 3 (it compared against person, not
person + style) and in applying the rule to all gestures at once; revised after an independent review.

## Model (`r/variance_components.R`)

For each feature, z-scored, on gesture events only (label ≠ none):

    feature ~ gesture + (1 | person) + (1 | person:gesture)          lme4, REML

Shares of total variance: **gesture** (variance of the fixed-effect predictions), **person** (person intercept),
**style** (person × gesture), **repetition** (residual). 95 % CI from a parametric bootstrap (100 draws while
exploring; **at least 500 for the paper**). On main-round data add `(1 | device)` and `(1 | person:session)`.

## Keep a feature for a contrast if all three hold

1. gesture share ≥ 0.30
2. gesture share ≥ 2 × (person + style)
3. lower CI of the gesture share > upper CI of (person + style)

## Applied per contrast, not over all gestures at once

A feature that separates one pair (loop direction for circle cw vs ccw) has almost no variance across the whole
vocabulary, and with gestures on different axes the axis features take the whole gesture share by construction.
So run the rule on:

- **all motions** (which features say *which* gesture in general), and
- **each confusable pair**: tilt L vs R, turn L vs R, circle cw vs ccw, and any pair the confusion matrix flags.

A feature is kept if it passes for all motions **or** for at least one pair.

## What the rule does not judge

- **Gesture vs non-gesture.** Only gesture events are modelled. Speed and size are person-specific *among*
  gestures but separate gestures from talking and face motion for everyone (EarSet: event accuracy 0.77 → 0.92,
  false commands 1.5 → 0.4 per hour on unseen people). Judge them by leave-one-person-out and cross-device tests,
  not by this rule.
- Features that fail are not deleted. They are reported, and used only after per-person (or per-device)
  normalisation, never raw across devices.

## When it is applied

- Descriptive, on all data: the paper's feature table (which features measure the gesture, which the person).
- Inside every leave-one-person-out fold when it selects the classifier's features: fit on the training people
  only, so the test person never influences the selection.
- The test of the rule itself: leave-one-person-out and cross-device accuracy for (a) kept features, (b) all
  features raw, (c) all features with per-person normalisation, in **both** device directions. Compare (a) with
  (b) separately from (c), so feature selection and enrollment are not confounded.

## Result on EarSet (30 people, nod/shake/tilt, `results/variance_components.md`)

Detector quiet_scale 3.0 (2026-11-07). Kept (all motions): share_x, share_y, share_z (gesture 0.90-0.98,
person + style ≤ 0.06). Partly by construction: nod, shake and tilt each turn about a different axis.
Not kept: speed, size, peaks (person + style 0.34-0.67). Same kept set as with quiet_scale 1.0 (0.85-0.91 gesture). Signed features cannot be judged: EarSet has no
direction pairs. On the old 4-person AirPods data they separate tilt L/R (0.52 → 0.94) and circle cw/ccw
(0.54 → 0.97); with 4 people that is supporting evidence, the formal check is on pilot data.
