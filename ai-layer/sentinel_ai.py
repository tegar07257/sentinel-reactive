#!/usr/bin/env python3
"""Sentinel AI layer — the running "AI in the loop" service (Minggu 2).

What it does, per run/cycle:
  1. Reads live state from both contracts (read-only eth_call):
       Lasna        Sentinel         largeSellCount, lastLargeSellAmount,
                                     lastLargeSellBlock, lastCronBlock,
                                     threshold
       Base Sepolia SentinelCallback lastAlertCount, lastAlertAmount,
                                     lastAlertBlock
  2. Fetches the full `LargeSell` event history from Lasna and the
     `Alert` history from Base Sepolia (eth_getLogs, adaptive chunks),
     so every detection carries its real amount + origin block, not just
     the latest counter values.
  3. For each detection not yet assessed, the deterministic classifier
     (classifier.py) assigns SINGLE_WHALE / BURST / CASCADE_RISK / NOISE
     from size-vs-threshold and window frequency; the local Ollama model
     adds a short narration when reachable (narrate.py), otherwise the
     record falls back to rules-only text.
  4. Appends one JSON object per detection to assessments.jsonl
     (append-only; re-runs never duplicate a count) and refreshes
     state.json with the counters it saw.

This layer is deliberately OFF-CHAIN: it reads, interprets and records.
It never signs, never sends, and holds no keys. Whether the assessment
should also be written back on-chain is evaluated in
../WEEK2-AI-LAYER-STATUS.md (design only, nothing deployed).

Usage:
  python3 sentinel_ai.py --once            # one pass, then exit
  python3 sentinel_ai.py --watch 30        # poll every 30 s (default)
  python3 sentinel_ai.py --once --no-model # skip Ollama narration
Env: SENTINEL_AI_MODEL (default qwen2.5:0.5b), SENTINEL_AI_OLLAMA_BASE.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chain import BASE_SEPOLIA, LASNA, SENTINEL  # noqa: E402
from classifier import classify, features  # noqa: E402
from keccak import topic0  # noqa: E402
from narrate import MODEL, narrate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ASSESSMENTS = os.path.join(HERE, "assessments.jsonl")
STATE = os.path.join(HERE, "state.json")

LARGESELL_TOPIC = topic0("LargeSell(uint256,uint256,uint256)")
ALERT_TOPIC = topic0("Alert(uint256,uint256,uint256)")

# Scan starts: comfortably before the 2026-11-14 deploys on both chains
# (Sentinel went live that morning; first organic alert ~origin block
# 58,518,904 on Base Sepolia). Ranges are small (tens of k blocks), so
# the adaptive chunker handles them in one or two requests.
LASNA_FROM = int(os.environ.get("SENTINEL_AI_LASNA_FROM", 8_250_000))
BASE_FROM = int(os.environ.get("SENTINEL_AI_BASE_FROM", 58_500_000))

WIB = timezone(timedelta(hours=7))


def eth_str(wei):
    """Exact wei -> ETH decimal string (integer math; float division
    smears the last digits, e.g. ...358 -> ...36)."""
    whole, frac = divmod(wei, 10 ** 18)
    if frac == 0:
        return str(whole)
    return f"{whole}.{frac:018d}".rstrip("0")


def now_iso():
    n = datetime.now(timezone.utc)
    return n.isoformat(), n.astimezone(WIB).isoformat()


def read_counters():
    c = {
        "threshold_wei": LASNA.eth_call_uint(SENTINEL, "threshold()"),
        "largeSellCount": LASNA.eth_call_uint(SENTINEL, "largeSellCount()"),
        "lastLargeSellAmount": LASNA.eth_call_uint(
            SENTINEL, "lastLargeSellAmount()"),
        "lastLargeSellBlock": LASNA.eth_call_uint(
            SENTINEL, "lastLargeSellBlock()"),
        "lastCronBlock": LASNA.eth_call_uint(SENTINEL, "lastCronBlock()"),
        "lastAlertCount": BASE_SEPOLIA.eth_call_uint(
            SENTINEL, "lastAlertCount()"),
        "lastAlertAmount": BASE_SEPOLIA.eth_call_uint(
            SENTINEL, "lastAlertAmount()"),
        "lastAlertBlock": BASE_SEPOLIA.eth_call_uint(
            SENTINEL, "lastAlertBlock()"),
        "lasna_head": LASNA.block_number(),
        "base_head": BASE_SEPOLIA.block_number(),
    }
    return c


def parse_largesell(log):
    data = log["data"][2:]
    return {
        "count": int(log["topics"][1], 16),
        "amount_wei": int(data[0:64], 16),
        "origin_block": int(data[64:128], 16),
        "lasna_block": int(log["blockNumber"], 16),
        "lasna_tx": log["transactionHash"],
    }


def parse_alert(log):
    data = log["data"][2:]
    return {
        "count": int(log["topics"][1], 16),
        "amount_wei": int(data[0:64], 16),
        "base_block": int(data[64:128], 16),
        "base_tx": log["transactionHash"],
    }


def load_assessed_counts():
    seen = set()
    if os.path.exists(ASSESSMENTS):
        with open(ASSESSMENTS) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("kind") == "assessment":
                    seen.add(rec["count"])
    return seen


def fallback_record(counters, utc_iso, wib_iso):
    """Used only if event history cannot be fetched but the counters
    prove detections exist: one snapshot record for the latest event,
    frequency unknown -> window of 1. Keeps the run honest: it says
    exactly what it could and could not read."""
    thr = counters["threshold_wei"]
    amt = counters["lastLargeSellAmount"]
    ev = {
        "count": counters["largeSellCount"],
        "amount_wei": amt,
        "amount_eth": eth_str(amt),
        "mult": round(amt / thr, 4) if thr else 0,
        "origin_block": counters["lastLargeSellBlock"],
        "lasna_block": None,
        "lasna_tx": None,
    }
    feat = {"window_blocks": None, "n_win": 1,
            "win_total_mult": ev["mult"], "rising": False,
            "note": "event history unavailable; counter state only"}
    cls = classify(ev, feat)
    return {
        "kind": "counter_snapshot",
        "count": ev["count"],
        "generated_at_utc": utc_iso,
        "generated_at_wib": wib_iso,
        "event": ev,
        "alert": None,
        "label": cls["label"],
        "reason": cls["reason"],
        "features": feat,
        "narration": None,
        "narration_source": "rules-fallback",
        "counters": counters,
    }


def run_once(use_model=True):
    utc_iso, wib_iso = now_iso()
    counters = read_counters()
    thr = counters["threshold_wei"]

    events, alerts = [], {}
    events_ok = True
    try:
        raw = LASNA.get_logs(SENTINEL, LARGESELL_TOPIC, LASNA_FROM,
                             counters["lasna_head"], initial_chunk=200_000)
        events = sorted((parse_largesell(l) for l in raw),
                        key=lambda e: e["count"])
    except Exception as e:  # noqa: BLE001
        events_ok = False
        print(f"[warn] LargeSell history fetch failed: {e}",
              file=sys.stderr)
    try:
        raw = BASE_SEPOLIA.get_logs(SENTINEL, ALERT_TOPIC, BASE_FROM,
                                    counters["base_head"],
                                    initial_chunk=10_000)
        alerts = {a["count"]: a for a in (parse_alert(l) for l in raw)}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Alert history fetch failed: {e}", file=sys.stderr)

    for e in events:
        e["amount_eth"] = eth_str(e["amount_wei"])
        e["mult"] = round(e["amount_wei"] / thr, 4) if thr else 0

    already = load_assessed_counts()
    new_records = []
    with open(ASSESSMENTS, "a") as out:
        for e in events:
            if e["count"] in already:
                continue
            feat = features(e, events)
            cls = classify(e, feat)
            rec = {
                "kind": "assessment",
                "count": e["count"],
                "generated_at_utc": utc_iso,
                "generated_at_wib": wib_iso,
                "event": e,
                "alert": alerts.get(e["count"]),
                "label": cls["label"],
                "reason": cls["reason"],
                "features": feat,
                "narration": None,
                "narration_source": "rules-fallback",
                "counters": {
                    "largeSellCount": counters["largeSellCount"],
                    "lastAlertCount": counters["lastAlertCount"],
                },
            }
            if use_model:
                text = narrate(rec)
                if text:
                    rec["narration"] = text
                    rec["narration_source"] = f"ollama:{MODEL}"
            if not rec["narration"]:
                rec["narration"] = (
                    f"Detection #{e['count']}: {cls['reason']}. "
                    f"Classified {cls['label']} by the deterministic "
                    f"rule engine.")
            out.write(json.dumps(rec) + "\n")
            new_records.append(rec)
        if not events and counters["largeSellCount"] > 0:
            snap_count = counters["largeSellCount"]
            if snap_count not in already:
                rec = fallback_record(counters, utc_iso, wib_iso)
                out.write(json.dumps(rec) + "\n")
                new_records.append(rec)

    state = {
        "updated_at_utc": utc_iso,
        "updated_at_wib": wib_iso,
        "counters": counters,
        "events_found": len(events),
        "alerts_found": len(alerts),
        "events_fetch_ok": events_ok,
        "total_assessed": len(already) + len(new_records),
        "new_this_run": len(new_records),
    }
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)

    print(f"[{wib_iso}] counters: largeSellCount="
          f"{counters['largeSellCount']} lastAlertCount="
          f"{counters['lastAlertCount']} threshold="
          f"{eth_str(thr)} ETH | events={len(events)} "
          f"alerts={len(alerts)} | new assessments={len(new_records)}")
    for r in new_records:
        ev = r["event"]
        print(f"  #{ev['count']:>2} {ev['amount_eth']:>22} ETH "
              f"({ev['mult']:>7}x) origin blk {ev['origin_block']} "
              f"-> {r['label']:<12} [{r['narration_source']}]")
    return state


def main():
    ap = argparse.ArgumentParser(description="Sentinel AI layer")
    ap.add_argument("--once", action="store_true",
                    help="single pass (default without --watch)")
    ap.add_argument("--watch", type=int, metavar="SEC", nargs="?",
                    const=30, default=None,
                    help="poll loop with interval seconds (default 30)")
    ap.add_argument("--no-model", action="store_true",
                    help="skip Ollama narration (rules-only records)")
    args = ap.parse_args()

    if args.watch:
        print(f"Sentinel AI layer watching every {args.watch}s "
              f"(Ctrl-C to stop)")
        while True:
            try:
                run_once(use_model=not args.no_model)
            except Exception as e:  # noqa: BLE001 — keep the watcher up
                print(f"[error] cycle failed: {e}", file=sys.stderr)
            time.sleep(args.watch)
    else:
        run_once(use_model=not args.no_model)


if __name__ == "__main__":
    main()
