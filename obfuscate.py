#!/usr/bin/env python3
"""
HKD Obfuscate Public
Static CPython source obfuscation with zero per-call protection runtime.

Security model:
- Plain source is not shipped.
- The compiled payload is compressed, block-scrambled, masked, and SHA-256 verified.
- HKD block-richness + exact meet-in-the-middle partitioning balances the two
  storage lanes before keyed permutation.
- All reconstruction happens once at import. Protected functions then execute
  as ordinary CPython functions with their original bytecode.

This is obfuscation + integrity, not cryptographic secrecy: a determined
attacker controlling the Python process can still inspect runtime code objects.
"""

import argparse
import binascii
import hashlib
import math
import marshal
import os
import random
import sys
import zlib


def _sha256(data):
    # Named hashlib constructors are Python's fast path.
    return hashlib.sha256(data).digest()


def _entropy(block):
    if not block:
        return 0.0
    counts = [0] * 256
    for b in block:
        counts[b] += 1
    n = float(len(block))
    e = 0.0
    for c in counts:
        if c:
            p = c / n
            e -= p * math.log(p, 2)
    return e


def _richness(block):
    # Integer score: information density + byte diversity + payload mass.
    return int(_entropy(block) * 3072) + len(set(block)) * 48 + len(block) * 3


def _mitm_balance(scores):
    """Exact subset-sum balance closest to half total; practical for <= 28 blocks."""
    n = len(scores)
    if n == 0:
        return set()
    if n > 24:
        # Windowed exact MITM keeps build cost bounded while retaining exact
        # balance inside each window.
        chosen = set()
        base = 0
        for start in range(0, n, 24):
            sub = scores[start:start + 24]
            for i in _mitm_balance(sub):
                chosen.add(base + i)
            base += len(sub)
        return chosen

    m = n // 2
    a, b = scores[:m], scores[m:]

    left = []
    for mask in range(1 << len(a)):
        s = 0
        for i, v in enumerate(a):
            if mask >> i & 1:
                s += v
        left.append((s, mask))
    left.sort()

    right = []
    for mask in range(1 << len(b)):
        s = 0
        for i, v in enumerate(b):
            if mask >> i & 1:
                s += v
        right.append((s, mask))

    target = sum(scores) / 2.0
    best = None
    j = len(left) - 1
    for sr, mr in right:
        want = target - sr
        lo, hi = 0, len(left)
        while lo < hi:
            mid = (lo + hi) // 2
            if left[mid][0] < want:
                lo = mid + 1
            else:
                hi = mid
        for k in (lo - 1, lo):
            if 0 <= k < len(left):
                sl, ml = left[k]
                err = abs((sl + sr) - target)
                if best is None or err < best[0]:
                    best = (err, ml, mr)

    _, ml, mr = best
    out = set()
    for i in range(len(a)):
        if ml >> i & 1:
            out.add(i)
    for i in range(len(b)):
        if mr >> i & 1:
            out.add(m + i)
    return out


def _keystream(key, index, n):
    out = bytearray()
    counter = 0
    seed = key + index.to_bytes(4, "big")
    while len(out) < n:
        out.extend(_sha256(seed + counter.to_bytes(4, "big")))
        counter += 1
    return bytes(out[:n])


def _xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _merkle_root(leaves):
    if not leaves:
        return _sha256(b"")
    level = list(leaves)
    while len(level) > 1:
        if len(level) & 1:
            level.append(level[-1])
        level = [_sha256(level[i] + level[i + 1])
                 for i in range(0, len(level), 2)]
    return level[0]


def _protect(data, key, block_size):
    blocks = [data[i:i + block_size] for i in range(0, len(data), block_size)]
    scores = [_richness(b) for b in blocks]
    lane_a = _mitm_balance(scores)

    # Keyed order within the two richness-balanced lanes.
    def rank(i):
        return _sha256(key + i.to_bytes(4, "big") + _sha256(blocks[i]))

    a = sorted((i for i in range(len(blocks)) if i in lane_a), key=rank)
    b = sorted((i for i in range(len(blocks)) if i not in lane_a), key=rank)

    order = []
    while a or b:
        if a:
            order.append(a.pop())
        if b:
            order.append(b.pop())

    protected = []
    leaves = [None] * len(blocks)
    original_to_stored = [0] * len(blocks)
    for stored_pos, original_index in enumerate(order):
        raw = blocks[original_index]
        masked = _xor(raw, _keystream(key, original_index, len(raw)))
        protected.append(masked)
        leaves[original_index] = _sha256(original_index.to_bytes(4, "big") + raw)
        original_to_stored[original_index] = stored_pos

    # Split the embedded key into two XOR shares. This is concealment, not
    # cryptographic key storage; both shares necessarily ship with the loader.
    rng = random.Random(int.from_bytes(_sha256(key + b"HKD-PUBLIC-SHARE-v1")[:16], "big"))
    share1 = bytes(rng.randrange(256) for _ in key)
    share2 = _xor(key, share1)

    return protected, original_to_stored, leaves, _merkle_root(leaves), share1, share2, scores


def obfuscate_source(source_path, output_path, key, block_size=192):
    source_path = os.path.abspath(source_path)
    output_path = os.path.abspath(output_path)
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # optimize=0 preserves ordinary source execution semantics, including asserts.
    code = compile(source, str(source_path), "exec",
                   dont_inherit=True, optimize=0)
    raw = marshal.dumps(code)
    packed = zlib.compress(raw, 9)

    key_bytes = _sha256(key.encode("utf-8"))
    blocks, inverse, leaves, root, s1, s2, scores = _protect(
        packed, key_bytes, block_size
    )

    literals = ",\n".join("bytes.fromhex(%r)" % binascii.hexlify(x).decode('ascii') for x in blocks)
    leaf_literals = ",\n".join("bytes.fromhex(%r)" % binascii.hexlify(x).decode('ascii') for x in leaves)

    loader = """# HKD OBFUSCATE PUBLIC — STATIC PROTECTED MODULE
# CPython %d.%d; all protection work occurs at import, never per function call.
import hashlib as _hh
import marshal as _hm
import zlib as _hz

_B=(%s,)
_I=%r
_L=(%s,)
_R=bytes.fromhex(%r)
_S1=bytes.fromhex(%r)
_S2=bytes.fromhex(%r)

def _x(a,b):
    return bytes(i^j for i,j in zip(a,b))

def _ks(k,idx,n):
    o=bytearray(); c=0; s=k+idx.to_bytes(4,'big')
    while len(o)<n:
        o.extend(_hh.sha256(s+c.to_bytes(4,'big')).digest()); c+=1
    return bytes(o[:n])

def _mr(v):
    if not v:
        return _hh.sha256(b'').digest()
    v=list(v)
    while len(v)>1:
        if len(v)&1: v.append(v[-1])
        v=[_hh.sha256(v[i]+v[i+1]).digest() for i in range(0,len(v),2)]
    return v[0]

_K=_x(_S1,_S2)
_P=[]
_V=[]
for _i in range(len(_I)):
    _m=_B[_I[_i]]
    _r=_x(_m,_ks(_K,_i,len(_m)))
    _P.append(_r)
    _V.append(_hh.sha256(_i.to_bytes(4,'big')+_r).digest())
if tuple(_V)!=_L or _mr(_V)!=_R:
    raise ImportError('HKD public SHA-256 integrity verification failed')

_C=_hm.loads(_hz.decompress(b''.join(_P)))

# Execute protected code in a fresh module-shaped namespace. This is critical
# for hot paths: loader temporaries never contaminate the function globals
# dictionary with deleted slots/tombstones.
_G=globals()
_N={
    '__name__':_G.get('__name__'),
    '__doc__':_G.get('__doc__'),
    '__package__':_G.get('__package__'),
    '__loader__':_G.get('__loader__'),
    '__spec__':_G.get('__spec__'),
    '__file__':_G.get('__file__'),
    '__cached__':_G.get('__cached__'),
    '__builtins__':_G.get('__builtins__'),
}
exec(_C,_N,_N)

# Publish source-defined names to the actual module object. Functions keep _N
# as __globals__, matching a clean normal module execution environment.
for _q,_v in _N.items():
    if _q != '__builtins__':
        _G[_q]=_v

del _B,_I,_L,_R,_S1,_S2,_K,_P,_V,_C,_i,_m,_r,_x,_ks,_mr,_q,_v,_N,_G,_hh,_hm,_hz
""" % (
        sys.version_info[0], sys.version_info[1],
        literals, tuple(inverse), leaf_literals, binascii.hexlify(root).decode('ascii'),
        binascii.hexlify(s1).decode('ascii'), binascii.hexlify(s2).decode('ascii')
    )

    parent = os.path.dirname(output_path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError:
            if not os.path.isdir(parent):
                raise
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(loader)

    return {
        "source_bytes": len(source.encode("utf-8")),
        "marshal_bytes": len(raw),
        "packed_bytes": len(packed),
        "blocks": len(blocks),
        "block_size": block_size,
        "richness_total": sum(scores),
        "sha256_merkle": binascii.hexlify(root).decode('ascii'),
        "python": "%d.%d" % sys.version_info[:2],
        "output": str(output_path),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("output")
    p.add_argument("--key", default=os.environ.get("HKD_OBFUSCATE_KEY", "HKD-PUBLIC-v1"))
    p.add_argument("--block-size", type=int, default=192)
    a = p.parse_args()
    info = obfuscate_source(a.source, a.output, a.key, a.block_size)
    for k in ("source_bytes", "marshal_bytes", "packed_bytes", "blocks",
              "block_size", "richness_total", "sha256_merkle", "python", "output"):
        print("%s=%s" % (k, info[k]))


if __name__ == "__main__":
    main()
