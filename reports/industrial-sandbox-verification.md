# Windows Sandbox terminal proof

Verified on 2026-09-04 with `python tools/nova_sandbox_proof.py --output reports/industrial-sandbox-proof-retry.json --timeout 180` (exit 0).

The generated `.wsb` launched the actual Windows Sandbox executable. Only the generated fixture/bootstrap/identity input directory was mounted read-only, with one dedicated writable output directory. Networking, clipboard, printers, audio input, video input and vGPU were disabled; ProtectedClient was enabled. No repository, profile, credentials or runtime installation was shared.

Guest PowerShell copied the immutable fixture into guest-local temporary storage, edited `hello` to `hello, nova`, executed the edited script in a child PowerShell terminal, and atomically returned JSON. The host validated the exact schema, fresh run ID and nonce, exit code, terminal text, original before/after SHA-256, expected edited SHA-256 and unchanged host input bundle. This proves the deterministic isolated terminal fixture, not execution of Nova's full release suite inside the guest.

Successful run: `2fa67c763c4bcaba802a64558e9a31f6`. Evidence is in `industrial-sandbox-proof-retry.json` and `sandbox-artifacts/2fa67c763c4bcaba802a64558e9a31f6/`. Guest result SHA-256: `b5d799e9374b23564d9a263cf1b3ec1436f29441f4940d6ecf7e1fbc77f3b056`.

The first attempt used a 120-second deadline and failed closed without guest evidence; its report remains in `industrial-sandbox-proof.json` for audit. The second fresh run used the CLI's 180-second default and passed. The reason for the first startup delay was not established. The Windows feature-state diagnostic required administrator elevation; no features were enabled, no reboot was requested, and no security settings were relaxed. Post-run process inspection found no remaining WindowsSandbox processes. Generated input/config/result files remain intentionally available for audit.

Boundary tests: `python -m pytest tests/test_nova_windows_sandbox.py -q -p no:cacheprovider` covers disabled capabilities, minimal mounts, strict schema/types, duplicate keys, wrong nonce/run ID, digest mismatch, oversized/malformed evidence, unavailable provider, timeout, hardlinks, input mutation and unexpected output files.
