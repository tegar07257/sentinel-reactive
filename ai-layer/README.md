# Sentinel AI Layer (Minggu 2 — "AI in the loop")

Off-chain companion service for the Sentinel reactive contracts
(`../sentinel/`). The on-chain side detects large WETH transfers on
Base Sepolia and fires callbacks; this layer is the running AI system
that **reads every detection, interprets it, and records a decision**:

- deterministic rule classifier assigns the label
  (`SINGLE_WHALE` / `BURST` / `CASCADE_RISK` / `NOISE`) from the
  transfer's size vs the on-chain threshold and the frequency of
  recent detections — the model never decides labels (measured
  unreliable at 0.5b/1.5b in the Cortensor DriftCheck experiments);
- the local Ollama model (default `qwen2.5:0.5b`) writes a short
  narration of the decision when reachable; if it is not, the record
  falls back to rules-only text and says so (`narration_source`).

Read-only by construction: `eth_call` / `eth_getLogs` only, no keys,
no signing, no sending, mainnet never touched.

## Run

```bash
cd ai-layer
python3 keccak.py                 # self-test (selectors/topics)
python3 sentinel_ai.py --once     # one pass against live state
python3 sentinel_ai.py --watch 30 # poll every 30 s, assess new events
python3 sentinel_ai.py --once --no-model   # rules only, no Ollama
```

Optional: start the model server first for narrated records —
`ollama serve` (binary under `hidden_files/cortensor-setup/bin/`).
Without it the service still completes, with `rules-fallback` records.

## Files

| File | Role |
|---|---|
| `keccak.py` | Pure-Python Keccak-256 (stdlib hashlib is NIST SHA3, wrong digests) + self-test |
| `chain.py` | Read-only JSON-RPC client, endpoint failover, adaptive-chunk `eth_getLogs` |
| `classifier.py` | Deterministic label rules + documented thresholds |
| `narrate.py` | Ollama narration (proxy-env workaround from DriftCheck F-001) |
| `sentinel_ai.py` | The service: counters → event history → classify → append JSONL |
| `assessments.jsonl` | Append-only assessment records, one per detection count |
| `state.json` | Latest counters/heads seen by the service |

Env knobs: `SENTINEL_AI_MODEL`, `SENTINEL_AI_OLLAMA_BASE`,
`SENTINEL_AI_LASNA_FROM`, `SENTINEL_AI_BASE_FROM` (log scan starts).

Contracts read: Sentinel `0xE86A5E5D1bCC4c1bF68aecAA8D3763BF475e8AE0`
on Lasna (`https://lasna-rpc.rnk.dev`), SentinelCallback
`0x61D4b1F2bC65d578B00CC9CF64a83EA191Cd6245` on Base Sepolia
(`https://sepolia.base.org` + public fallbacks). Pair #3, hardened
redeploy of 15 Nov 2026 (see `../REDEPLOY-2026-11-15.md`).
