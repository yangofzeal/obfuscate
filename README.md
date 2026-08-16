# HKD Obfuscate

**Static Python source protection with SHA-256 integrity and zero added hot-path bytecode.**

HKD Obfuscate is a small, single-file Python obfuscator designed for performance-sensitive code.

Unlike protection systems that keep a runtime VM, decryptor, dispatcher, or wrapper in the execution path, HKD Obfuscate performs its protection work at build/import time. After reconstruction, protected functions execute as ordinary CPython functions with their original bytecode.

No platform-specific distribution is required.

```bash
python obfuscate.py input.py protected.py
