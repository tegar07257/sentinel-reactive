# Sentinel — a Reactive watchdog with an AI layer that audits its own loop

**Reactive Omni Buildathon · Track: Reactive Meets AI**

Sentinel watches WETH transfers on **Base Sepolia** from a Reactive
contract on **Lasna**. Every transfer at or above a threshold is counted
on-chain and triggers a cross-chain `alert()` callback back to Base
Sepolia — no keeper, no cron job, no off-chain trigger: the contract
reacts by itself. On top of that loop runs an **AI layer**: a local,
read-only agent service that reads *every* detection, classifies it with
a deterministic rule engine, has a local LLM narrate the decision, and —
most importantly — **audits the loop at event level**, which is how it
caught a callback that the on-chain counters said had happened but
actually hadn't (finding F-AI-1 below).

Everything here is testnet. No mainnet, no real funds.

## The loop

```
Base Sepolia                     Lasna (Reactive)                  Base Sepolia
─────────────                    ────────────────                  ────────────
WETH Transfer ──event──▶ Sentinel.react() ──requestCallback──▶ SentinelCallback.alert()
(amount ≥ 0.001 ETH)     counts it, emits                         records count,
                         LargeSell(count,                         amount, block;
                         amount, block)                           emits Alert(...)
                                  │
                                  ▼
                         AI layer (off-chain, read-only):
                         reads LargeSell + Alert events,
                         classifies, narrates, appends
                         one assessment record per detection
```

1. `Sentinel` (Lasna, chain 5318007) subscribes in its constructor to
   ERC-20 `Transfer` events of WETH (`0x4200000000000000000000000000000000000006`)
   on Base Sepolia (chain 84532), and to Cron100 ticks.
2. In `react()` — callable only by the Reactive system contract — a
   transfer `≥ threshold` (0.001 ETH) increments `largeSellCount`,
   stores the amount and origin block, emits `LargeSell`, and requests
   a callback.
3. The callback lands on `SentinelCallback` (Base Sepolia), which only
   accepts calls from the authorized callback proxy + sender, stores
   `lastAlertCount / lastAlertAmount / lastAlertBlock`, and emits
   `Alert`.
4. The AI layer polls both chains' events and counters, matches each
   `LargeSell` with its `Alert`, classifies the detection, and writes
   an append-only JSONL assessment.

Both contracts were deployed from the same wallet at nonce 0, so —
conveniently — **both live at the same address**:

| Contract | Chain | Address |
|---|---|---|
| Sentinel | Lasna (5318007) | `0xb78d73DEfCcCD42f3A6bbca4E05aF9149320c3C9` |
| SentinelCallback | Base Sepolia (84532) | `0xb78d73DEfCcCD42f3A6bbca4E05aF9149320c3C9` |

Explorers:
[Sentinel on Reactscan (Lasna)](https://lasna.reactscan.net/address/0xb78d73DEfCcCD42f3A6bbca4E05aF9149320c3C9) ·
[SentinelCallback on Basescan (Base Sepolia)](https://sepolia.basescan.org/address/0xb78d73DEfCcCD42f3A6bbca4E05aF9149320c3C9)

Deploy transactions: callback
[`0xfd50ead7…e4db`](https://sepolia.basescan.org/tx/0xfd50ead776cb334992491d8be7398542a938ff10cd21f35a8f2c3c9fc793e4db) (Base Sepolia),
Sentinel `0x6dfbcbe1e8735a421d45b027c53efab7888c980130e0627263f87cd39c17dedd` (Lasna).

**Verified live (14 Nov 2026):** 20 detections, 20 callbacks at counter
level. The first organic detection was a WETH transfer of
**0.070873991024375358 ETH** (70.87× the threshold) at Base Sepolia
block 58518904; its callback arrived 6 blocks later.
Detection tx (Lasna): `0xe9310189575b458113f3c7acd4118d590b09215640b4fd61d8f5dfa434158a8d`;
callback tx (Base Sepolia): `0xc68073a51b6d3a04db35699a85addc3d1177f465c04c9e48926fbb54d8270daa`.

## The hard lesson: Reactive debt silently pauses everything

The loop worked exactly once — then went silent for hours while three
deliberate test triggers were ignored. Balance looked fine. The real
cause, per the official Reactive economy docs:

> **While a contract carries `debt` to the system contract, the system
> contract does not call `react()` at all — for any subscription.**
> Matching events queue up; they are not lost, just never delivered.

What happened: the 0.05 lREACT deployment funding lost ~0.0422 lREACT
to two `subscribe()` charges; the first reaction's bill exceeded what
was left, recording **debt of 0.0113278 lREACT** and blacklisting the
contract. A plain 0.05 lREACT transfer top-up did **not** help —
transfers neither settle debt nor create reserves, so the money sat
stranded in a dead contract.

**The fix** is the documented one: `SYSTEM.depositTo(contract)` —
it settles outstanding debt first and turns the remainder into
reserves. After `depositTo` on Lasna (0.05, then 0.15, then 0.25
lREACT as queued bursts drained reserves) and 0.005 ETH to the Base
Sepolia callback proxy, the queued triggers were delivered in order
and the counters ran 1 → 4 → 9 → 20, callbacks 1:1. The `Sentinel`
source now also exposes a `coverDebt()` wrapper (the official
`AbstractPayer` pattern) so the contract can settle debt from its own
balance without an external `depositTo`.

Measured costs on Lasna (basefee 100 gwei, `_extraGas` 100,000): one
reaction + callback cycle ≈ 0.011–0.03 lREACT; one Cron tick
≈ 0.01253 lREACT; one subscription ≈ 0.0211 lREACT. The Cron
subscription itself was proven correct in isolation (a probe contract
received 4 consecutive ticks exactly every 100 blocks) — on Sentinel
it simply never got a funded window of ≥100 blocks, because the
transfer queue always drained the reserves first.

**Operational rule that falls out of this: top up with `depositTo`
~0.25–0.5 lREACT immediately before a demo, and demo right away.**

## The AI layer (`ai-layer/`)

A Python service (standard library only — no pip installs, no API
keys) that is part of the running system, not a build-time tool:

- **Deterministic classifier labels; the model never labels.**
  Features per detection: `mult` = amount / on-chain threshold, and a
  300-origin-block window (≈10 min) with event count, total size, and
  a rising-sequence flag. First matching rule wins:
  **CASCADE_RISK** (≥3 events in window and window total ≥ 100×, or a
  rising sequence) → **BURST** (≥3 events in window) → **NOISE**
  (mult < 2, quiet window) → **SINGLE_WHALE** (the rest).
- **A local LLM only narrates.** Ollama `qwen2.5:0.5b` writes a short
  explanation of the already-decided label. If the model is
  unreachable, the record falls back to rules-only text and says so
  (`narration_source`). This split is deliberate and measured: in our
  earlier DriftCheck experiments a 0.5B model classified correctly
  only ~2/6 times and over-predicted cascades — fine as a narrator,
  unfit as a judge.
- **Read-only by construction:** `eth_call` / `eth_getLogs` only. No
  keys, no signing, no sending path exists in the code. Keccak-256 is
  implemented in pure Python (stdlib `hashlib` is NIST SHA3, which
  produces different digests) and self-tested against the
  `Transfer` topic constant in `Sentinel.sol`.
- **Idempotent:** each detection count is assessed exactly once;
  re-runs append nothing.

Label distribution over the 20 live detections: CASCADE_RISK 12,
SINGLE_WHALE 4, NOISE 3, BURST 1. Sample output:
[`ai-layer/assessments-sample.jsonl`](ai-layer/assessments-sample.jsonl).

### Finding F-AI-1 — the counters lied; the events didn't

The counters said the loop was perfect: `largeSellCount = 20`,
`lastAlertCount = 20`. The AI layer's event-level audit found only
**19 `Alert` logs**. Detection **#2** (0.001327539033669843 ETH,
origin block 58542421) has no matching `Alert` anywhere in the scanned
range; the other 19 alerts match their detections 1:1 in order and
amount. This is consistent with one `requestCallback` being dropped
during the debt-era burst while the destination counter still ended
at 20 — because `alert()` *writes the count from the payload* instead
of incrementing. Takeaway, and the reason this layer exists: **audit
a reactive loop by its events, never by its counters.**

## Repository layout

```
src/Sentinel.sol           Reactive contract (Lasna): subscriptions, react(), coverDebt()
src/SentinelCallback.sol   Callback counterparty (Base Sepolia)
test/Sentinel.t.sol        6 Foundry tests
script/Deploy.s.sol        Deploy scripts (callback first, then Sentinel)
lib/                       forge-std + reactive-lib-omni (official Reactive library)
ai-layer/                  The AI assessment service (see ai-layer/README.md)
foundry.toml               solc 0.8.29
```

## Run it

Contracts:

```bash
forge build
forge test        # 6/6 passing
```

AI layer (Python 3, stdlib only):

```bash
cd ai-layer
python3 keccak.py                  # selector/topic self-test
python3 sentinel_ai.py --once      # one pass against live state
python3 sentinel_ai.py --watch 30  # poll and assess new detections
python3 sentinel_ai.py --once --no-model   # rules only, no Ollama
```

For model-narrated records, start Ollama first (`ollama serve`, model
`qwen2.5:0.5b`). Without it the service still completes, with
`rules-fallback` narration.

## Honest limitations

- **Demo economics are wasteful by design.** A 0.001 ETH threshold on
  Base Sepolia's WETH — a busy testnet token — means organic transfers
  above threshold arrive constantly. While the contract is in debt
  they queue; once revived, the burst drains reserves within blocks
  and the contract pauses again. This is correct network behaviour,
  not a bug — but it means the demo must be funded right before it
  runs (see the `depositTo` rule above). A hardened redeploy
  (threshold ~0.05 ETH, Cron1000 instead of Cron100, callback gas
  ~200k) is the planned fix if longer unattended operation is needed.
- **The AI layer assesses; it does not control.** Callbacks fire from
  the Reactive contract regardless of classification. An on-chain
  assessment registry (hash-anchoring each record) was designed but
  deliberately not deployed for this submission.
- **Narration quality at 0.5B is cosmetic-grade.** Facts in the
  narration are spelled out for the model to copy verbatim; it still
  occasionally rambles. Labels never depend on it.
- `lastCronBlock` remains 0 on the live contract for the economic
  reason explained above (funded windows shorter than the 100-block
  tick interval), not a subscription defect — proven by the isolated
  Cron probe.

## Credits

Built with the official
[Reactive Network](https://dev.reactive.network) `reactive-lib-omni`
library and Foundry. Solo project by tegar07 for the Reactive Omni
Buildathon, track *Reactive Meets AI*.
