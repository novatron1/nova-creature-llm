# v144 — Vision Input Expansion

## Purpose
Let Nova learn from screenshots and visual reports without fake image understanding.

## Current Vision Stack (v096-v100)
- screenshot report reading (text-first)
- UI error extraction
- folder screenshot understanding
- visual memory conversion
- visual benchmark report parsing

## Future Vision Targets
- accept human-provided screenshot descriptions when OCR/vision unavailable
- parse visual test results into memory events
- extract version/status from report screenshots
- convert visual errors into mistake memory
- flag uncertain visual claims as pending approval

## Safety Rules
- no fake image understanding
- if OCR/vision tools unavailable, accept text description
- uncertain visual claims go to pending approval
- no training of raw unprocessed screenshots
