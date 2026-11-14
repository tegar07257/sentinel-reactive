#!/usr/bin/env python3
"""Minimal read-only JSON-RPC client (stdlib only).

External RPCs go through the sandbox egress proxy (env vars, which urllib
honours automatically). Read-only by construction: only eth_call,
eth_getLogs, eth_blockNumber are wrapped — there is no signing or sending
anywhere in this layer.

Each chain has a list of public endpoints; calls fail over in order.
getLogs uses adaptive chunking: start with a wide block window, halve it
whenever an endpoint complains, so one code path works against strict and
lenient RPCs alike.
"""
import json
import time
import urllib.request

from keccak import selector

TIMEOUT = 30


class RpcError(Exception):
    pass


class Chain:
    def __init__(self, name, endpoints, log_endpoints=None):
        self.name = name
        self.endpoints = endpoints
        # Endpoints that answer eth_getLogs sanely (some hosts that are
        # fine for eth_call reject or truncate log queries).
        self.log_endpoints = log_endpoints or endpoints
        self._id = 0

    def _post(self, url, method, params):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id,
                           "method": method, "params": params}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     # Several public RPCs 403 the default Python-urllib
                     # user agent; identify as a generic HTTP client.
                     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                   "sentinel-ai-layer/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            resp = json.load(r)
        if "error" in resp:
            raise RpcError(f"{method}: {resp['error']}")
        return resp["result"]

    def _call_on(self, endpoints, method, params):
        last = None
        for url in endpoints:
            try:
                return self._post(url, method, params)
            except Exception as e:  # noqa: BLE001 — fail over to next RPC
                last = e
        raise RpcError(f"{self.name} {method} failed on all endpoints: "
                       f"{last}")

    def call(self, method, params):
        return self._call_on(self.endpoints, method, params)

    def block_number(self):
        return int(self.call("eth_blockNumber", []), 16)

    def eth_call_uint(self, address, sig):
        data = selector(sig)
        out = self.call("eth_call", [{"to": address, "data": data},
                                     "latest"])
        return int(out, 16)

    def get_logs(self, address, topic0, from_block, to_block,
                 initial_chunk=50_000, min_chunk=500):
        """All logs for (address, topic0) in [from_block, to_block].

        Uses the chain's log endpoints only. Each span is retried up to
        3 times (free public RPCs rate-limit in bursts); persistent
        failure halves the window (down to min_chunk) before giving up.
        Spans that succeed are never re-asked.
        """
        logs = []
        start = from_block
        chunk = initial_chunk
        while start <= to_block:
            end = min(start + chunk - 1, to_block)
            part, last = None, None
            for _ in range(3):
                try:
                    part = self._call_on(self.log_endpoints, "eth_getLogs",
                                         [{
                                             "address": address,
                                             "topics": [topic0],
                                             "fromBlock": hex(start),
                                             "toBlock": hex(end),
                                         }])
                    break
                except Exception as e:  # noqa: BLE001 — retry, then halve
                    last = e
                    time.sleep(1.0)
            if part is None:
                if chunk <= min_chunk:
                    raise RpcError(
                        f"{self.name} eth_getLogs span {start}-{end} "
                        f"failed after retries and halving: {last}")
                chunk = max(min_chunk, chunk // 2)
                continue
            logs.extend(part)
            start = end + 1
        return logs


LASNA = Chain("lasna", ["https://lasna-rpc.rnk.dev"])
BASE_SEPOLIA = Chain(
    "base-sepolia",
    ["https://sepolia.base.org",
     "https://base-sepolia-rpc.publicnode.com",
     "https://base-sepolia.drpc.org"],
    # Measured 2026-11-14: sepolia.base.org answers eth_call fine but
    # returns HTTP 413 for eth_getLogs through this sandbox's egress;
    # drpc's free tier returns HTTP 400 for getLogs; publicnode works
    # with block ranges up to 50k. Logs therefore go to publicnode.
    log_endpoints=["https://base-sepolia-rpc.publicnode.com",
                   "https://sepolia.base.org"])

SENTINEL = "0xb78d73DEfCcCD42f3A6bbca4E05aF9149320c3C9"
# Same address on both chains (CREATE with the same nonce from the same
# deployer): Sentinel lives on Lasna, SentinelCallback on Base Sepolia.
