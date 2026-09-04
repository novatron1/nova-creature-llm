# Nova Test / Check Live Test

Date: 2026-08-19

## Browser result

- Opened `http://127.0.0.1:3000/` in Chromium.
- Opened the **Test / Check** tab.
- Pressed **Full Training**.
- The panel returned `Score 100/100 - 30/30 checks passed`.
- Nine category result rows rendered in the panel.
- No browser page errors were reported.
- Screenshot: `reports/nova-test-check-live.png`.

## What the score means

The 30 checks verify Nova's current behavior across memory, truth, commands, deep conversation, web honesty, tools, website builder, and UI. A green score is a release/evaluation gate; it does not by itself change model weights.

## Guarded training result

The button also queued guarded transformer training with job ID `hypertrain_job_b8ce9b5c`. At the time of the live check, `/api/training/status` reported the job as still running. The most recent completed guarded run was `REJECTED` because the candidate did not improve the protected metrics, so no improvement should be claimed until this job finishes with `PROMOTED` and the candidate is activated.

## Safe learning path

1. Save a bad answer and a corrected answer in Review & Train.
2. Approve only corrections that are actually better.
3. Build/check the reviewed dataset.
4. Run guarded training on the local or rented GPU.
5. Promote only if the candidate beats the baseline and passes protected facts/negative controls.
6. Re-run Test / Check and a holdout conversation before calling Nova improved.
