#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKD Obfuscate v4 - portable source-payload obfuscation for CPython 3.4.3+.

Design goals:
- Never serialize Python code objects.  No marshal dependency.
- Emit only syntax/APIs available in Python 3.4.3 and still supported by modern CPython.
- Compile the protected source on the destination interpreter.
- Execute protected source directly in the module's real globals dictionary.
- Add no wrapper, hook, decorator, proxy, tracing, or per-call work to protected functions.
  After import, protected functions are ordinary CPython functions.

Important:
- There is necessarily one-time import work: reconstruct, verify, decompress, decode,
  compile, and exec.  "Zero overhead" here means zero added steady-state/per-call
  overhead after import, not zero import-time cost.
- The protected source itself must be valid on every Python version on which it is
  expected to run.  Building it with Python 3.4.3 is a strong syntax/API gate for
  the oldest target, but this tool cannot make version-specific application code
  portable automatically.
- This is obfuscation and integrity protection, not cryptographic secrecy.  Code
  executing in a Python process can ultimately be inspected by a determined user.
"""

from __future__ import print_function

import argparse
import binascii
import hashlib
import io
import math
import os
import random
import struct
import sys
import zlib


def _sha256(data):
    return hashlib.sha256(data).digest()


def _u32(n):
    if n < 0 or n > 0xffffffff:
        raise ValueError("integer does not fit in 32 bits")
    return struct.pack(">I", n)


def _xor_bytes(a, b):
    if len(a) != len(b):
        raise ValueError("xor operands differ in length")
    out = bytearray(len(a))
    i = 0
    while i < len(a):
        out[i] = a[i] ^ b[i]
        i += 1
    return bytes(out)


def _entropy(block):
    if not block:
        return 0.0
    counts = [0] * 256
    for value in block:
        counts[value] += 1
    total = float(len(block))
    result = 0.0
    for count in counts:
        if count:
            p = count / total
            result -= p * math.log(p, 2)
    return result


def _richness(block):
    return int(_entropy(block) * 4096) + len(set(block)) * 64 + len(block)


def _mitm_balance(scores):
    """Choose a subset whose score is closest to half the total.

    Work is bounded by splitting long inputs into exact 28-block windows.
    This is build-time only and therefore cannot affect protected-call speed.
    """
    n = len(scores)
    if n == 0:
        return set()

    if n > 28:
        chosen = set()
        base = 0
        start = 0
        while start < n:
            sub = scores[start:start + 28]
            for index in _mitm_balance(sub):
                chosen.add(base + index)
            base += len(sub)
            start += 28
        return chosen

    middle = n // 2
    left_scores = scores[:middle]
    right_scores = scores[middle:]

    left = []
    mask = 0
    while mask < (1 << len(left_scores)):
        score = 0
        i = 0
        while i < len(left_scores):
            if (mask >> i) & 1:
                score += left_scores[i]
            i += 1
        left.append((score, mask))
        mask += 1
    left.sort()

    right = []
    mask = 0
    while mask < (1 << len(right_scores)):
        score = 0
        i = 0
        while i < len(right_scores):
            if (mask >> i) & 1:
                score += right_scores[i]
            i += 1
        right.append((score, mask))
        mask += 1

    target = sum(scores) / 2.0
    best = None
    for right_score, right_mask in right:
        want = target - right_score
        lo = 0
        hi = len(left)
        while lo < hi:
            mid = (lo + hi) // 2
            if left[mid][0] < want:
                lo = mid + 1
            else:
                hi = mid
        for k in (lo - 1, lo):
            if 0 <= k < len(left):
                left_score, left_mask = left[k]
                error = abs((left_score + right_score) - target)
                if best is None or error < best[0]:
                    best = (error, left_mask, right_mask)

    chosen = set()
    left_mask = best[1]
    right_mask = best[2]

    i = 0
    while i < len(left_scores):
        if (left_mask >> i) & 1:
            chosen.add(i)
        i += 1

    i = 0
    while i < len(right_scores):
        if (right_mask >> i) & 1:
            chosen.add(middle + i)
        i += 1

    return chosen


def _keystream(key, index, length):
    out = bytearray()
    counter = 0
    seed = key + _u32(index)
    while len(out) < length:
        out.extend(_sha256(seed + _u32(counter)))
        counter += 1
    return bytes(out[:length])


def _merkle_root(leaves):
    if not leaves:
        return _sha256(b"")
    level = list(leaves)
    while len(level) > 1:
        if len(level) & 1:
            level.append(level[-1])
        next_level = []
        i = 0
        while i < len(level):
            next_level.append(_sha256(level[i] + level[i + 1]))
            i += 2
        level = next_level
    return level[0]


def _seed_integer(data):
    # Avoid int.from_bytes so the emitted/build-side compatibility surface is tiny.
    return int(binascii.hexlify(data), 16)


def _protect(data, key, block_size):
    blocks = []
    start = 0
    while start < len(data):
        blocks.append(data[start:start + block_size])
        start += block_size

    if not blocks:
        blocks = [b""]

    scores = [_richness(block) for block in blocks]
    lane_a = _mitm_balance(scores)

    def rank(index):
        return _sha256(key + _u32(index) + _sha256(blocks[index]))

    a = sorted([i for i in range(len(blocks)) if i in lane_a], key=rank)
    b = sorted([i for i in range(len(blocks)) if i not in lane_a], key=rank)

    order = []
    while a or b:
        if a:
            order.append(a.pop())
        if b:
            order.append(b.pop())

    protected = []
    leaves = [None] * len(blocks)
    original_to_stored = [0] * len(blocks)

    stored_position = 0
    for original_index in order:
        raw = blocks[original_index]
        masked = _xor_bytes(raw, _keystream(key, original_index, len(raw)))
        protected.append(masked)
        leaves[original_index] = _sha256(_u32(original_index) + raw)
        original_to_stored[original_index] = stored_position
        stored_position += 1

    rng = random.Random(_seed_integer(_sha256(key + b"HKD-V4-SHARE")[:16]))
    share1 = bytes(bytearray([rng.randrange(256) for _ in range(len(key))]))
    share2 = _xor_bytes(key, share1)

    return (protected, original_to_stored, leaves,
            _merkle_root(leaves), share1, share2, scores)


def _hex(data):
    return binascii.hexlify(data).decode("ascii")


def _hex_expr(data):
    # binascii.unhexlify has existed for far longer than the minimum target.
    return "_hb.unhexlify(%r)" % _hex(data)


def _generated_loader(blocks, inverse, leaves, root, share1, share2):
    block_literals = ",\n        ".join(_hex_expr(item) for item in blocks)
    leaf_literals = ",\n        ".join(_hex_expr(item) for item in leaves)

    # Everything used only by the loader lives inside _hkd_v4_bootstrap(), except
    # the function name itself.  The protected program is exec'd directly into the
    # real module globals dictionary, preserving ordinary Python global semantics.
    return '''# -*- coding: utf-8 -*-
# HKD OBFUSCATE v4 - portable source payload, no marshal/code-object dependency.
# Protection is import-time only; protected functions have no per-call wrapper.
def _hkd_v4_bootstrap(_g):
    import binascii as _hb
    import hashlib as _hh
    import struct as _hs
    import zlib as _hz

    _b = (
        %s,
    )
    _inv = %r
    _leaves = (
        %s,
    )
    _root = _hb.unhexlify(%r)
    _share1 = _hb.unhexlify(%r)
    _share2 = _hb.unhexlify(%r)

    def _u32(_n):
        return _hs.pack('>I', _n)

    def _xor(_a, _c):
        _o = bytearray(len(_a))
        _i = 0
        while _i < len(_a):
            _o[_i] = _a[_i] ^ _c[_i]
            _i += 1
        return bytes(_o)

    def _ks(_key, _index, _length):
        _o = bytearray()
        _counter = 0
        _seed = _key + _u32(_index)
        while len(_o) < _length:
            _o.extend(_hh.sha256(_seed + _u32(_counter)).digest())
            _counter += 1
        return bytes(_o[:_length])

    def _merkle(_values):
        if not _values:
            return _hh.sha256(b'').digest()
        _level = list(_values)
        while len(_level) > 1:
            if len(_level) & 1:
                _level.append(_level[-1])
            _next = []
            _i = 0
            while _i < len(_level):
                _next.append(_hh.sha256(_level[_i] + _level[_i + 1]).digest())
                _i += 2
            _level = _next
        return _level[0]

    _key = _xor(_share1, _share2)
    _parts = []
    _verify = []
    _i = 0
    while _i < len(_inv):
        _masked = _b[_inv[_i]]
        _raw = _xor(_masked, _ks(_key, _i, len(_masked)))
        _parts.append(_raw)
        _verify.append(_hh.sha256(_u32(_i) + _raw).digest())
        _i += 1

    if tuple(_verify) != _leaves or _merkle(_verify) != _root:
        raise ImportError('HKD protected payload integrity verification failed')

    try:
        _source = _hz.decompress(b''.join(_parts)).decode('utf-8')
    except Exception as _exc:
        raise ImportError('HKD protected payload reconstruction failed: %%s' %% (_exc,))

    _filename = _g.get('__file__') or '<HKD-obfuscated>'
    _code = compile(_source, _filename, 'exec', 0, True, 0)

    # Discard the plaintext string before running user code.  CPython may reclaim
    # it immediately; no plaintext source is retained as a module global.
    del _source

    # Exact module semantics: definitions execute in the actual module globals.
    exec(_code, _g, _g)

_hkd_v4_bootstrap(globals())
del _hkd_v4_bootstrap
''' % (
        block_literals,
        tuple(inverse),
        leaf_literals,
        _hex(root),
        _hex(share1),
        _hex(share2)
    )


def obfuscate_source(source_path, output_path, key, block_size=128):
    if block_size <= 0:
        raise ValueError("block size must be greater than zero")
    if block_size > 0xffffffff:
        raise ValueError("block size is too large")

    source_path = os.path.abspath(source_path)
    output_path = os.path.abspath(output_path)

    with open(source_path, "rb") as handle:
        source_bytes = handle.read()

    try:
        source = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("source must be UTF-8 encoded")

    # Crucial portability rule: validate source, but never serialize this code object.
    compile(source, source_path, "exec", 0, True, 0)

    raw = source.encode("utf-8")
    packed = zlib.compress(raw, 9)
    key_bytes = _sha256(key.encode("utf-8"))

    protected, inverse, leaves, root, share1, share2, scores = _protect(
        packed, key_bytes, block_size
    )

    loader = _generated_loader(
        protected, inverse, leaves, root, share1, share2
    )

    parent = os.path.dirname(output_path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError:
            if not os.path.isdir(parent):
                raise

    with io.open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(loader)

    # Validate the generated loader with the builder interpreter too.
    compile(loader, output_path, "exec", 0, True, 0)

    return {
        "source_bytes": len(raw),
        "packed_bytes": len(packed),
        "blocks": len(protected),
        "block_size": block_size,
        "richness_total": sum(scores),
        "sha256_merkle": _hex(root),
        "builder_python": "%d.%d.%d" % sys.version_info[:3],
        "payload": "utf8-source",
        "marshal_code_objects": "NO",
        "per_call_wrapper": "NO",
        "target_min_python": "3.4.3",
        "output": output_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Portable HKD source obfuscator for CPython 3.4.3+"
    )
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument(
        "--key",
        default=os.environ.get("HKD_OBFUSCATE_KEY", "HKD-INF")
    )
    parser.add_argument("--block-size", type=int, default=128)
    args = parser.parse_args()

    info = obfuscate_source(
        args.source, args.output, args.key, args.block_size
    )

    fields = (
        "source_bytes",
        "packed_bytes",
        "blocks",
        "block_size",
        "richness_total",
        "sha256_merkle",
        "builder_python",
        "payload",
        "marshal_code_objects",
        "per_call_wrapper",
        "target_min_python",
        "output",
    )
    for field in fields:
        print("%s=%s" % (field, info[field]))


if __name__ == "__main__":
    main()
