#!/usr/bin/env python3
"""Sentinel AI layer — model narration (the model's ONLY job here).

Mirrors DriftCheck's narrate.py exactly in spirit and mechanics: the
local Ollama model receives the label ALREADY DECIDED by classifier.py
plus the rule reason, and writes one short explanation. It never decides
or changes a label. Any failure (server down, model missing, timeout)
returns None and the caller falls back to a rules-only sentence —
narration is decoration, the record stands without it.

Localhost gotcha (FINDINGS F-001 from Cortensor): the sandbox proxy vars
break URL parsing for 127.0.0.1, so proxy env is stripped before the
call and a no-proxy opener is used.
"""
import json
import os
import urllib.request

BASE = os.environ.get("SENTINEL_AI_OLLAMA_BASE", "http://127.0.0.1:11434/v1")
MODEL = os.environ.get("SENTINEL_AI_MODEL", "qwen2.5:0.5b")

SYS = ("You are the narrator of Sentinel, a reactive-contract watchdog. "
       "You are given one detected large WETH transfer on Base Sepolia "
       "testnet and the classification label decided by a rule engine. "
       "Write ONE short paragraph (max 2 sentences) in plain English "
       "explaining why the label fits the numbers. Do not change the "
       "label. Copy every number EXACTLY as given — never compute, "
       "convert or round numbers yourself. Always finish your "
       "sentences.")

PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy")

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _clean_env():
    for k in PROXY_VARS:
        os.environ.pop(k, None)


def narrate(record, timeout=120):
    """Return narration text, or None on any failure (non-fatal)."""
    _clean_env()
    ev = record["event"]
    feat = record["features"]
    body = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 120,
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user", "content":
             f"Detection #{ev['count']}.\n"
             f"Transfer size: {ev['amount_eth']} ETH.\n"
             f"Alert threshold: 0.001 ETH, so this transfer is "
             f"{ev['mult']} times the threshold.\n"
             f"Origin block: {ev['origin_block']}.\n"
             f"Large transfers in the surrounding window: "
             f"{feat['n_win']}, totalling {feat['win_total_mult']} "
             f"times the threshold.\n"
             f"Label: {record['label']}\n"
             f"Rule reason: {record['reason']}"},
        ],
    }
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _opener.open(req, timeout=timeout) as r:
            resp = json.load(r)
        text = (resp["choices"][0]["message"].get("content") or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 — narration failure is non-fatal
        return None
