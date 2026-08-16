## 2026-08-17 — Verdict: JuiceScan v1.1 field day

- **Verdict:** PASS overall (core stack, high-res transparency), PARTIAL
  (frame auto-detection → assisted editor; IR descratch limited by
  silver-film physics; color casts from cold lamp), NULL (exposure-based
  speed experiment: predicted ~2x, measured none, motor-bound, reverted).
- **Evidence:** 48 tests green; TA ladder 300–4800 dpi verified on
  hardware (row/col metrics 7–35); scan 40x30mm@2400 ≈ 2 min regardless
  of buffer; exposure 24000: 202s vs baseline 133s.
- **Prediction check:** three misses recorded (calibration-slot symptom
  misread as driver bug; exposure≠throughput; libtool install names
  untrustworthy). Mental-model fixes in IMprovement-roadmap.md.
- **Honesty checks:** experiment reverted after NULL, no threshold moved
  post-hoc; 300-dpi-cap release was published on a wrong diagnosis and
  explicitly corrected; scope change on frame detection recorded as
  PARTIAL, not PASS.
- **Learned:** physical light path first; option order is API; verify
  shipped binaries, never trust relink; UI strings in comparisons are API.
- **Next:** notarized signing, lamp warm-up guard, multi-exposure
  (see docs/IMprovement-roadmap.md).
