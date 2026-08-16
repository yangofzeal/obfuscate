# HKD Obfuscate

**Static Python source protection with SHA-256 integrity and zero added hot-path bytecode.**

HKD Obfuscate is a small, single-file Python obfuscator designed for performance-sensitive code.

Unlike protection systems that keep a runtime VM, decryptor, dispatcher, or wrapper in the execution path, HKD Obfuscate performs its protection work at build/import time. After reconstruction, protected functions execute as ordinary CPython functions with their original bytecode.

No platform-specific distribution is required.

```bash
python obfuscate.py input.py protected.py
```

## Runtime Overhead: 0.00% Added Hot-Path Bytecode

HKD Obfuscate was designed around a simple requirement:

**Obfuscation should not make the protected function slower every time it runs.**

HKD Obfuscate performs reconstruction and SHA-256 integrity verification outside the repeated application hot path. Once the protected module has loaded, the reconstructed function executes with the same CPython bytecode as the original function.

Our structural verification reports:

```text
exact_behavior=True
hot_function_bytecode_exact=True
structural_added_hotpath_bytecodes=0
structural_per_call_obfuscation_overhead_pct=0.0000
PASS=True
```

HKD (Hilbert–Krylov Decomposition) is a broader research program investigating structured contraction, active-state reduction, and effective-complexity reduction in computational problems.

The following papers provide background on the development and applications of HKD.

### Subset Sum

**Hilbert–Krylov Tower Decomposition and a Pseudo-Polynomial Complexity Bound for Subset Sum**

International Journal of Computer Techniques (IJCT), Vol. 12, Issue 6, 2025.

https://ijctjournal.org/hilbert-krylov-pseudo-polynomial-complexity/

Introduces HKD/HKT contraction for Subset Sum and analyzes a controlled effective-width formulation.

### Traveling Salesman Problem

**Hilbert–Krylov Tower Decomposition for the Traveling Salesman Problem: Exact-Verified Solutions with Reduced Effective Complexity**

International Journal of Computer Techniques (IJCT), Vol. 12, Issue 6, 2025.

https://ijctjournal.org/hilbert-krylov-tower-decomposition/

Applies HKD as structured pruning over the Held–Karp dynamic-programming state space and reports exact-verified results on structured instances.

### General NP-Hard Problems

**Generalizing the Hilbert–Krylov Decomposition to Exact Solution of NP-Hard Problems**

International Journal of Computer Techniques (IJCT), Vol. 12, Issue 6, 2025.

https://ijctjournal.org/generalizing-hilbert-krylov-decomposition/

Develops the broader HKD width-collapse framework and its application across NP-hard dynamic-programming state spaces under stated structural conditions.

### Missile Defense

**Invariance of Interceptor Assignment Latency in Distributed Missile Defense via Hilbert–Krylov Decomposition**

International Journal of Computer Techniques (IJCT), Vol. 13, Issue 2, 2026.

https://ijctjournal.org/invariance-interceptor-assignment-latency/

Applies HKD ideas to distributed interceptor/threat assignment and studies scaling under a fixed lane-width coverage condition.

### Monotone Contraction of Symbolic Degrees of Freedom

**Monotone Loss of Symbolic Freedom in the Collatz Dynamics via HKD Piano Lanes**

International Journal of Computer Techniques (IJCT), Vol. 13, Issue 1, 2026.

https://ijctjournal.org/monotone-loss-symbolic-freedom/

Studies an HKD-inspired symbolic invariant under arithmetic refinement and formalizes monotone contraction of symbolic degrees of freedom.

### HKD∞ and Large TSP Instances

**A 93-Second Reproducible Certificate for the TSPLIB d2103 Optimum via HKD-Infinity Style Alternating Components and Weighted Hamiltonian Completion**

International Journal of Computer Techniques (IJCT), Vol. 13, Issue 4, 2026.

https://ijctjournal.org/93-second-reproducible-certificate-tsplib-d2103-optimum/

Reports a reproducible HKD∞-style certificate pipeline for the 2,103-city TSPLIB `d2103` instance.
