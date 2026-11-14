#!/usr/bin/env python3
"""Sentinel AI layer — deterministic event classifier.

Same design decision as DriftCheck (Cortensor #5, Minggu 1 notes): the
LABEL is decided by this rule module, never by the small local model —
qwen2.5:0.5b/1.5b classification was measured unreliable (~2/6 correct,
over-predicts cascades). The model only narrates (narrate.py).

Input per detected large transfer (one Sentinel `LargeSell` event):
  amount_wei    — transfer size
  mult          — amount / on-chain threshold (threshold = 0.001 ETH)
  window_events — all events whose ORIGIN block lies within WINDOW_BLOCKS
                  before this event's origin block (inclusive)
Derived features: n_win (count in window), win_total_mult (sum of mults
in window), rising (last three amounts in window strictly increasing).

Labels (first matching rule wins):
  CASCADE_RISK — n_win >= 3 AND (win_total_mult >= 100 OR rising):
                 a dense cluster of large transfers, heavy in aggregate
                 or accelerating — the pattern that precedes a cascade.
  BURST        — n_win >= 3: several large transfers close together,
                 but neither heavy enough nor accelerating.
  NOISE        — mult < 2 AND n_win <= 2: barely over the threshold and
                 essentially isolated. On this demo the known instances
                 are the deliberate 1.5x test triggers — real signal
                 should not page anyone for these.
  SINGLE_WHALE — everything else with mult >= 2: one genuinely large
                 transfer on its own.

WINDOW_BLOCKS = 300 origin blocks. Base Sepolia produces a block every
~2 s, so the window is ~10 minutes — the same order as DriftCheck's
30-minute swap window, tightened because reactive alerting is real-time.
All thresholds are constants here, printed into every record's evidence.
"""

WINDOW_BLOCKS = 300
CASCADE_TOTAL_MULT = 100
BURST_MIN_EVENTS = 3
NOISE_MAX_MULT = 2


def features(event, history):
    """Compute window features for `event` from the full event history
    (list of dicts with origin_block + amount_wei, sorted by count)."""
    win = [e for e in history
           if event["origin_block"] - WINDOW_BLOCKS <= e["origin_block"]
           <= event["origin_block"]]
    amounts = [e["amount_wei"] for e in win]
    rising = (len(amounts) >= 3
              and amounts[-3] < amounts[-2] < amounts[-1])
    return {
        "window_blocks": WINDOW_BLOCKS,
        "n_win": len(win),
        "win_total_mult": round(sum(e["mult"] for e in win), 2),
        "rising": rising,
    }


def classify(event, feat):
    mult = event["mult"]
    n_win = feat["n_win"]
    if n_win >= BURST_MIN_EVENTS and (
            feat["win_total_mult"] >= CASCADE_TOTAL_MULT or feat["rising"]):
        label = "CASCADE_RISK"
    elif n_win >= BURST_MIN_EVENTS:
        label = "BURST"
    elif mult < NOISE_MAX_MULT and n_win <= 2:
        label = "NOISE"
    elif mult >= NOISE_MAX_MULT:
        label = "SINGLE_WHALE"
    else:
        label = "NOISE"

    reason = {
        "CASCADE_RISK": (
            f"{n_win} large transfers within {WINDOW_BLOCKS} origin "
            f"blocks, aggregate {feat['win_total_mult']}x threshold"
            + (", amounts rising" if feat["rising"] else "")),
        "BURST": (
            f"{n_win} large transfers within {WINDOW_BLOCKS} origin "
            f"blocks, aggregate {feat['win_total_mult']}x threshold"),
        "NOISE": (
            f"marginal trigger at {mult:.2f}x threshold, "
            f"{n_win} event(s) in window — no dominant pattern"),
        "SINGLE_WHALE": (
            f"isolated large transfer at {mult:.2f}x threshold, "
            f"{n_win} event(s) in window"),
    }[label]
    return {"label": label, "reason": reason, "features": feat}
