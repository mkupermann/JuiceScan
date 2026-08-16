# JuiceScan — Verdict & Improvement Roadmap

Date: 2026-08-17. Written after the first full field day with real film.
Verdicts are judged against the bars set before the work, not after.

## Verdict per workstream

**Core stack (driver build, CLI, GUI, packaging): PASS.**
Self-compiled genesys backend detects and drives the 8600F, 48 unit
tests green, hardware-verified flatbed and transparency scans, DMG with
native pkg installer, Windows package from CI, GIMP plugin shipped.
Release v1.1 is live and self-contained.

**High resolution transparency: PASS, with a diagnosis lesson.**
300 to 4800 dpi verified with real image data. The evening-long detour
happened because an obstructed calibration slot produced symptoms that
looked exactly like a driver bug. Prediction "backend is broken above
300 dpi" was a miss; the mental model lacked "calibration is physical
and resolution-dependent". A 300-dpi-capped release shipped in between
and had to be reverted. Lesson recorded below.

**Automatic frame detection: PARTIAL.**
Base-gap detection works when frames have bright gaps. On strips where
dense image areas touch, no automatic method we tried separates frames
reliably. The bar moved from "automatic" to "assisted": editor with
draggable frames plus a frame-count field. That is a scope change and
is recorded as such, not sold as a pass.

**Infrared scratch removal: PARTIAL.**
Works as designed on dye film. Physically impossible on silver B/W
film; the app now detects that case and skips inpainting instead of
smearing dense areas (the license-plate incident). Limit is physics,
documented.

**Speed versus VueScan: NULL on the main experiment.**
Buffer-size tuning brought a modest, jittery gain (118 s vs 133–178 s).
The exposure-period experiment predicted ~2x speedup and delivered
none (202 s cold vs 133 s baseline) — the line rate is motor-bound,
not exposure-bound. Honest NULL, reverted, no post-hoc tuning.
VueScan's speed comes from per-device motor tuning we have not
attempted; that is their paid moat.

**Color quality on film: PARTIAL.**
The cold lamp shifts color during the first scans, producing
density-dependent casts that no global correction removes. Correct
answer for silver B/W film is grayscale scanning; that toggle was
silently broken by an i18n string mismatch (found by Michael in manual
testing, regression test added). Gray-world balance plus joint
luminance stretch now handles global casts for color film.

## Prediction misses worth remembering

1. "Stripes above 300 dpi = driver bug" — wrong, hardware. Check the
   physical light path before blaming register code.
2. "Halving exposure halves scan time" — wrong, motor-bound. Measure
   which component gates throughput before tuning another.
3. "libtool relink produces correct install names" — wrong twice.
   Shipped binaries silently depended on the dev tree; only hard
   normalization plus a build-failing verification closed it.

## Roadmap, ordered by value for the photographer

1. **Notarized signing.** The DMG is ad-hoc signed; on any other Mac,
   Gatekeeper will block it. Apple Developer ID plus notarization makes
   the GitHub release genuinely public. Effort: small, needs the
   certificate.
2. **Lamp warm-up guard.** Before color film scans, offer a warm-up
   pass or a delay until lamp color stabilizes; kills the pink/green
   casts at the root. Effort: small.
3. **Multi-exposure for dense negatives.** Two passes at different
   exposure, merged; the classic answer to thin shadows. Effort: one
   day, hardware-testable with the existing oracle loop.
4. **GIMP plugin smoke test.** Still untested inside a real GIMP.
   Install GIMP 3 once, click through, remove the caveat. Effort: an
   hour.
5. **16-bit through the processing pipeline.** Today 16-bit is raw-only;
   inversion and crops force 8-bit. numpy pipeline can stay 16-bit
   until export. Effort: half a day.
6. **Motor-profile speed experiments.** The remaining gap to VueScan.
   Risky on old mechanics (banding, stalls); run as opt-in experiment
   series with the scan oracle. Effort: open-ended.
7. **openscan.** Generalization to all old SANE-supported scanners;
   spec exists (`~/Documents/GitHub/openscan`). Park until JuiceScan
   is boring.

## Durable lessons (one line each)

- Physical light path first, register theory second.
- scanimage option order matters: source before resolution.
- Never trust libtool with install names; verify shipped binaries or
  fail the build.
- A UI string used in a comparison is an API, not a label.
