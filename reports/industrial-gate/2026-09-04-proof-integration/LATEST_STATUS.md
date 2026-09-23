# Verification status — September 4, 2026

The app was refreshed on port 3000 (process 31064) and returned HTTP 200. Startup loaded all seven transformer roles.

- Live isolated behavioral baseline: 8/8, strict threshold 1.0, in `reports/behavior-evidence-controller-v2.json`. This is eight fixture scenarios, not a broad production-quality certification.
- Full Windows test run: 2,269 passed, 2 timeout failures, 12 skipped in `reports/industrial-windows-final-suite.xml`. Both timeout cases passed unchanged in isolation (2 passed in 4.66 seconds) in `reports/industrial-timeout-recheck.xml`. The original failed aggregate remains intact.
- Eleven exact Linux/POSIX skips are classified not applicable for the Windows release, without changing raw JUnit counts. The Windows host symlink-permission skip has a separate successful real Windows Sandbox proof in `reports/industrial-real-symlink.json`.
- Clean release preparation now binds the required checkpoint inputs to `NOVA_RUNTIME_ASSETS.json`, copies them only during verification, and verifies/removes those copies before source comparisons and commits. Review found that first-pass Git history/index changes also needed rejection; that check was added. Six focused tests passed, including attempts to stage or commit copied weights. Such failed private runs are not accepted releases.
- No completed clean candidate or production promotion exists yet. The full gate still needs to pass on the final immutable candidate commit. Old interrupted/failed runs must not be treated as release evidence.

Storage: the completed ZIP was copied to `F:\NovaVerification\preserved-exports\NOVA_COMPANION_768D_LATEST_20260821.zip`, SHA-256 verified, then its original removed. Size 1,470,244,128 bytes; SHA-256 `7e8e5cafaF343ca9b90f6c0960c79e73cbaff1f7515014f7000b56a1d972376a` (case insensitive). The unpacked export remains on C:. C: subsequently fell to approximately 7 MB free. A separate question to move the unpacked export to F: is pending; no dependent move is authorized yet. Disposable verification work uses `E:\NovaVerification\20260904-industrial`.
