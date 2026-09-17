# Gabor front-end on a second unit, and why the flat-field matters more than the search

Measured 2026-09-17, evaluating @PHILIPPDEV5396's PR #3 (`egis_match_gabor.c`) on
a second unit and a second person's hands. His own numbers, on his unit, are
0.0 % FRR at 0.0 % FAR; the parameters were chosen on that same dataset, which is
why he sent it opt-in and asked for someone else's hardware.

## Headline

Cross-fold, held-out (see Protocol):

| configuration | FRR | FAR |
|---|---|---|
| `egis_match.c` as shipped (+/-6 px, 800 px floor) | 51.7 % | 4.5 % |
| `egis_match_gabor.c`, raw frames | 17.2 % | 1.1 % |
| **`egis_match_gabor.c` + subtractive flat-field** | **6.9 %** | **1.1 %** |

The Gabor front-end replicates as the largest single improvement this matcher has
had. It does **not** reproduce his clean separation here: flat-fielded, the weakest
genuine press scores 0.600 and the strongest impostor 0.815, so the populations
still overlap and 6.9 % is a threshold choice rather than a gap.

## The flat-field makes the threshold portable

This is the part worth carrying forward. Fixed-pattern noise is per-sensel and
therefore unit-specific, so it is what makes a threshold measured on one laptop
wrong on another.

| | fold thresholds | spread |
|---|---|---|
| gabor, raw frames | 0.832 / 0.870 | 0.038 |
| **gabor + flat-field** | **0.815 / 0.813** | **0.001** |
| his unit, raw frames (his figures) | 0.793 / 0.803 | 0.010 |

On raw frames this unit's zero-false-accept point sits near 0.85 while his sits
near 0.80, and that gap is real: at his shipped `em_match_threshold` of 0.80 the
Gabor front-end false-accepts 3.4 % of this unit's impostors, 3 of 88, the worst
at 0.870. Flat-fielded, the two folds here agree to 0.001 and land at 0.814.

On this unit the high-gain fixed pattern is 13x the low-gain one (per-pixel
standard deviation 26.6 against 2.0), which is presumably why it matters most on
the high-gain frames the driver actually verifies against.

### It must be subtraction, and it is front-end specific

Two findings that cost time:

- **Multiplicative correction destroys frames.** `px * mean(ref) / ref` divides by
  a reference spanning about 31..248 at gain 6, so it scales parts of the frame by
  up to 3.6x and clips at 255. Corrected frames lose so much coherent area that
  `em_match` returns its `-1` sentinel. Subtraction centred at 128 is the right
  model for a per-sensel offset and clips about 2 % of pixels.
- **The flat-field helps the Gabor front-end and hurts the original.** The same
  correction takes `egis_match.c` from 51.7 % to 65.5 % and pushes one genuine
  frame below the 800 px overlap floor entirely. Anyone testing the two changes
  independently will wrongly conclude the flat-field is harmful.

The correction was validated before being trusted: a reference built from three
no-finger frames, applied to a held-out fourth, removes 84 % of its per-pixel
variation at gain 6 (standard deviation 26.89 to 4.28) and correlates 0.987 with
it, so the pattern is genuinely fixed rather than noise.

## The ablation needs a retuned baseline

PR #3's ablation compares the Gabor front-end against `egis_match.c` at +/-6 and
+/-19, both with `EM_MIN_OVERLAP` left at 800. That is the wrong corner to
benchmark against, because the floor and the search width are coupled
(see [em-srch-sweep-results.md](em-srch-sweep-results.md)). Retuning both
constants together, same data and protocol:

| pool | base as shipped | base retuned | gabor, raw |
|---|---|---|---|
| gain-0 set | 73.3 % | **6.7 %** (+/-30, 1200) | 13.3 % |
| gain-6 sessions | 28.6 % | 14.3 % (+/-28, 1000) | **7.1 %** |
| pooled | 51.7 % | **17.2 %** (+/-26, 1400) | **17.2 %** |

Pooled, a retuned original and the Gabor front-end on raw frames tie exactly, and
each wins one of the two pools. So "the Gabor step is the only thing that lifted
the genuine floor clear of the impostor ceiling" is not established yet: the
search, mask and rotation ablations were all measured over a fixed 800 px floor.

None of this touches the flat-field result. Gabor plus flat-field at 6.9 % beats
every tuning of the original front-end found so far.

## Protocol

- Unit: Lenovo Yoga 7 16IRL8, Intel. His: Yoga 7 14ARB7, AMD.
- 29 genuine and 88 impostor decisions across 8 capture blocks. Impostors are the
  same person's other fingers, not another person's.
- `em_match(&template, &probe)`, the order PR #3 documents. The Gabor front-end is
  not symmetric and the first harness here had the probe first, which understated
  it; the header comment in PR #3 is the only reason that was caught.
- **Cross-fold:** the threshold is the strictest zero-false-accept point on one
  fold, applied to the held-out fold, both directions, weighted by fold size.
  Folds split by capture block so no press appears on both sides. A threshold
  chosen on the data it is scored against proves nothing.
- Every dataset was scanned for ghost frames (stale frames the sensor
  intermittently re-serves, cross-label raw correlation > 0.95) before use. Three
  were found and excluded, all copies of a session's first enrolment frame.

```sh
cc -O2 -Idriver -Wno-address tools/frontend_eval.c driver/egis_match_gabor.c -o /tmp/fe -lm

python3 tools/flatfield.py --data-root <captures> --out /tmp/ff \
    --ref-gain0 'frames/baseline_*.bin' --ref-gain6 'frames/g6base_*.bin' \
    --gain6 'session_*'

python3 tools/eval_frontend.py --bin /tmp/fe --data-root /tmp/ff --enroll 5 \
    --fold-a 'dataset:f1,dataset:f2,dataset:f3,session_20260802_110741' \
    --exclude 'session_20260802_110741/genuine_03.bin,session_20260802_112811/impostor-thumb_00.bin,session_20260802_112811/impostor-leftindex_02.bin'
```

## Caveats

- 6.9 % of 29 genuine decisions is two presses. Treat the third digit with the
  suspicion it deserves.
- The two capture sets differ in **sensor gain** (one gain 0, one gain 6) and in
  **enrolment protocol** (5 arbitrary presses against 8 guided ones covering
  distinct fingertip regions). Pooling them mixes both, and the guided gain-6
  sessions are much the easier set for the original front-end (28.6 % against
  73.3 %).
- Impostor scores rise sharply with template count under both front-ends
  (impostor median 0.288 at 5 templates, 0.744 at 8). A decision is a maximum
  over templates times alignments, so deeper enrolment buys an impostor more
  chances. This is the same effect behind the "deeper enrolment shrinks the
  margin" result in PR #3.
- Raw frames are biometrics and are not in this repository. Everything here is
  scores and rates.
