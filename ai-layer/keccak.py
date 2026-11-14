#!/usr/bin/env python3
"""Pure-Python Keccak-256 (Ethereum flavour, NOT NIST SHA3-256).

Stdlib-only: hashlib.sha3_256 uses NIST padding (0x06) and gives different
digests than Ethereum's Keccak (padding 0x01), so selectors/topics computed
with it would be wrong. This is the standard Keccak-f[1600] sponge with
rate 1088 / capacity 512, suffix 0x01, 24 rounds.

Self-test vectors (run this file directly):
  keccak256("")                                  = c5d24601...d85a470
  keccak256("Transfer(address,address,uint256)") = ddf252ad...f523b3ef
  (the second one is the TRANSFER_TOPIC_0 constant in Sentinel.sol)
"""

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_R = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_MASK = (1 << 64) - 1


def _rot(x, n):
    return ((x << n) | (x >> (64 - n))) & _MASK if n else x


def _keccak_f(state):
    for rc in _RC:
        # theta
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15]
             ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rot(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        # rho + pi
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rot(state[x + 5 * y],
                                                        _R[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = (b[x + 5 * y]
                                    ^ ((~b[(x + 1) % 5 + 5 * y])
                                       & b[(x + 2) % 5 + 5 * y])) & _MASK
        # iota
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136  # bytes (1088 bits)
    state = [0] * 25
    # pad10*1 with Keccak suffix 0x01
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != rate - 1:
        padded.append(0x00)
    padded.append(0x80)
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(state)
    out = bytearray()
    while len(out) < 32:
        for i in range(rate // 8):
            out += state[i].to_bytes(8, "little")
        if len(out) < 32:
            _keccak_f(state)
    return bytes(out[:32])


def selector(sig: str) -> str:
    """4-byte function selector as 0x-prefixed hex."""
    return "0x" + keccak256(sig.encode()).hex()[:8]


def topic0(sig: str) -> str:
    """32-byte event topic0 as 0x-prefixed hex."""
    return "0x" + keccak256(sig.encode()).hex()


if __name__ == "__main__":
    v1 = keccak256(b"").hex()
    assert v1 == ("c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7"
                  "bfad8045d85a470"), v1
    v2 = keccak256(b"Transfer(address,address,uint256)").hex()
    assert v2 == ("ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f5"
                  "5a4df523b3ef"), v2
    print("keccak self-test OK")
    for sig in ("largeSellCount()", "lastLargeSellAmount()",
                "lastLargeSellBlock()", "lastCronBlock()", "threshold()",
                "lastAlertCount()", "lastAlertAmount()", "lastAlertBlock()"):
        print(f"  {sig:24s} selector {selector(sig)}")
    for sig in ("LargeSell(uint256,uint256,uint256)",
                "Alert(uint256,uint256,uint256)"):
        print(f"  {sig:34s} topic0 {topic0(sig)}")
