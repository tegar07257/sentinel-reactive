# SUBMISSION CHECKLIST — Sentinel @ DoraHacks Reactive Omni Buildathon

Track: **Reactive Meets AI**. Hard deadline per plan: **6 Dec 2026,
07:00 WIB**; internal target: submit end of Nov 2026, fully polished
(tegar's decision 14 Nov 2026: "sempurnakan dulu sampai bener-bener
mateng" — do not submit half-done).

Submission requirements (from `../../files/rencana-build-reactive-omni.md`):
public repo + deployed contract addresses + several tx hashes showing
the complete loop (event → Reactive → callback) + demo video < 3 min.
Judging: Execution (an on-chain reactive tx + callback is the gate —
without it the entry is not scored), Integration (the reactive
contract does real work, not decoration), Usefulness, Craft (clean
code, demo, docs).

## Still to do before submitting

- [x] **Publish this repo to GitHub (public)** and note the URL here:
      `REPO_URL = https://github.com/tegar07257/sentinel-reactive`
      (Published earlier. The 15 Nov 2026 redeploy source updates in
      this local copy — threshold/Cron1000/gas-limit changes — still
      need a push; run the standard secret scan of the diff first:
      no `.env`, no key files (see `.gitignore`); the testnet deploy
      key must NOT be in the repo.)
- [ ] **Top up immediately before the demo/submission session:**
      `SYSTEM.depositTo(0xE86A5E5D1bCC4c1bF68aecAA8D3763BF475e8AE0)`
      on Lasna with **~0.5 lREACT** (from the testnet deployer
      wallet). Current pair is #3 (see REDEPLOY-2026-11-15.md in the
      parent folder). Last known state (15 Nov 2026, after the
      revival top-up): debt 0, reserves 0.4886699 lREACT, contract
      balance 0.005853 lREACT, largeSellCount 6, lastAlertCount 6;
      deployer held 0.3329797 lREACT. Measured burn is
      ~0.06–0.077 lREACT per detection cycle, so 0.5 lREACT buys
      roughly 6–8 cycles.
      Also confirm the Base Sepolia callback proxy
      (`0x476F44b11F5C942c58f4c8E3d0300E5710743585`) still has
      debt 0 / reserves > 0 for the callback
      `0x61D4b1F2bC65d578B00CC9CF64a83EA191Cd6245`
      (last: reserves 0.004996 ETH).
      Do the demo right after topping up — the organic transfer queue
      drains reserves within blocks.
- [ ] **Re-read the final live state at submission time** and use
      THOSE numbers in the submission text (do not reuse the numbers
      below — they are the 14 Nov snapshot):
      - Sentinel (Lasna): `largeSellCount`, `lastLargeSellAmount`,
        `lastLargeSellBlock`, `lastCronBlock`, `threshold`
      - SentinelCallback (Base Sepolia): `lastAlertCount`,
        `lastAlertAmount`, `lastAlertBlock`
      - System contract: `debt(Sentinel)`, reserves/balance
      - Snapshot 14 Nov 2026 ~14:09 WIB (for comparison only):
        largeSellCount 20, lastAlertCount 20, last amount
        0.049264358917821638 ETH @ origin block 58549848,
        lastAlertBlock 58549858, lastCronBlock 0, events 20 vs
        Alert logs 19 (finding F-AI-1).
- [ ] **Fire one fresh deliberate trigger during the demo** (e.g. wrap
      + transfer **0.06 WETH** on Base Sepolia — must be ≥ the new
      0.05 ETH threshold; the old 0.0015 WETH example no longer
      triggers anything) and capture its full hash chain for the
      submission: origin Transfer tx → Lasna reaction tx → Base
      Sepolia callback tx.
- [ ] **Run the AI layer live once** (`python3 sentinel_ai.py --once`
      with Ollama serving `qwen2.5:0.5b`) so the newest detection —
      including the demo trigger — has an assessment record; keep the
      `assessments.jsonl` output for the video/submission.
- [ ] **Record the demo video (< 3 minutes).** Suggested flow:
      1. Show the contracts on the explorers (addresses + counters).
      2. Fire the deliberate WETH transfer; show `LargeSell` on Lasna
         and the `Alert` callback on Base Sepolia arriving.
      3. Run the AI layer; show the new assessment (label + narration)
         and the 20-detection label distribution.
      4. Show finding F-AI-1: counters 20 = 20, events 20 vs 19.
      5. One line on the debt lesson + `depositTo`/`coverDebt()` fix.
- [ ] **Fill the DoraHacks submission form:**
      - Project name: Sentinel
      - Track: Reactive Meets AI
      - Public repo URL (from above)
      - Contract addresses (pair #3, hardened — the two addresses
        are DIFFERENT now; pair #1 shared one address on both chains):
        - Sentinel (Lasna): `0xE86A5E5D1bCC4c1bF68aecAA8D3763BF475e8AE0`
        - SentinelCallback (Base Sepolia): `0x61D4b1F2bC65d578B00CC9CF64a83EA191Cd6245`
      - Tx hashes proving the full loop — at minimum the first
        organic detection chain of pair #3:
        - Detection (Lasna): `0xebd1f7b5820a6d96d995399d7deba66c8b7570ae62de98ec27d4edada596c4bc`
        - Callback (Base Sepolia): `0x545d6c0906340e608bd01602b24dd87daa63b95a2cf860857e290a04d506deeb`
        - Deploy callback: `0x1dc55d939db77ffa3102b98481f34739d7abbcfaf18caf8ea4ac9bee3d25b490`
        - Deploy Sentinel: `0xba6ad5c8f859aeb2ba4f9a2fdaf1e3e715031c589a49f4e75650b377599cdf51`
        - Plus the fresh demo-trigger chain recorded above.
      - Pair #1 (superseded) proof chain, for project history only:
        - Detection (Lasna): `0xe9310189575b458113f3c7acd4118d590b09215640b4fd61d8f5dfa434158a8d`
        - Callback (Base Sepolia): `0xc68073a51b6d3a04db35699a85addc3d1177f465c04c9e48926fbb54d8270daa`
        - Deploy callback: `0xfd50ead776cb334992491d8be7398542a938ff10cd21f35a8f2c3c9fc793e4db`
        - Deploy Sentinel: `0x6dfbcbe1e8735a421d45b027c53efab7888c980130e0627263f87cd39c17dedd`
      - Demo video link (< 3 min): **https://www.youtube.com/watch?v=l8x22ZWlwxo**
        (public demo video already published — recorded here 15 Nov 2026)
      - Description: adapt the repo README (what it is, the loop, the
        debt lesson, the AI layer, F-AI-1, honest limitations). Use
        ONLY the corrected organic figure **0.070873991024375358 ETH**
        — never the superseded ~1.129 ETH number from the week-1
        notes.
- [x] **Decision — hardened redeploy: DONE 15 Nov 2026** (tegar
      chose redeploy). Threshold 0.05 ETH, Cron1000, `coverDebt()`
      live. Callback gas is **500,000, not the ~200k originally
      sketched here**: the first hardened attempt (pair #2) proved
      200k cannot work — the Base Sepolia callback proxy withholds
      130,000 gas (_extraGas 80,000 + _maxChargeGas 50,000) and
      `alert()` needs ~91,786, so 200k forwarded only 70,000 and all
      6 deliveries failed with `CallbackFailure`. Full analysis in
      `../REDEPLOY-2026-11-15.md`. Current pair is #3 (addresses in
      the form section above); README, this checklist, and the Open
      Agentic Web watchdog files were updated in the same pass
      (watchdog site itself still needs a git push to go live).
- [ ] **Do NOT claim in the submission:** an on-chain assessment
      registry (designed only, not deployed), Cron ticks landing on
      Sentinel itself (proven via probe contract only), or "20/20
      callbacks" without the F-AI-1 caveat (events show 19 Alert
      logs).
