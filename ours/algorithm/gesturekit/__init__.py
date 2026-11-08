"""gesturekit: head-gesture command recognition from earbud IMU.

Stages (each its own module, each replaceable):
    io        load recordings into one Recording format (collector v3 sessions, EarSet, old AirPods takes)
    qc        quality checks on a recording
    frames    calibrated head frame (gravity + calibration nods)
    detect    causal motion detector -> variable-length events
    features  physical features per event (registry)
    classify  event classifiers (registry)
    decode    gate + pair decoder -> commands
    label     cue log -> labelled events (ground truth)
    pipeline  wires the stages together, offline and online
    simulate  synthetic v3 sessions for end-to-end tests
    evaluate  event, false-alarm and command metrics
"""
