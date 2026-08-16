# HKD Obfuscate

**Static Python source protection with SHA-256 integrity and zero added hot-path bytecode.**

HKD Obfuscate is a small, single-file Python obfuscator designed for performance-sensitive code.

Unlike protection systems that keep a runtime VM, decryptor, dispatcher, or wrapper in the execution path, HKD Obfuscate performs its protection work at build/import time. After reconstruction, protected functions execute as ordinary CPython functions with their original bytecode.

No platform-specific distribution is required.

```bash
python obfuscate.py input.py protected.py

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
