#!/usr/bin/env python3
"""Remove the sensor's fixed-pattern noise from raw frames.

Every sensel on this sensor has its own dark level, and at high gain that
per-pixel pattern is large: on the unit this was written for, the gain-6
reference has a per-pixel standard deviation of 26.6 against 2.0 at gain 0.
The pattern is highly repeatable (a held-out no-finger frame correlates 0.987
with a reference built from other no-finger frames), so it subtracts out.

Removing it matters because the pattern is UNIT-SPECIFIC: it is what makes a
match threshold measured on one laptop wrong on another. On the unit this was
written for, flat-fielding took the cross-fold threshold spread of the Gabor
front-end from 0.038 to 0.001. See docs/gabor-frontend-second-unit.md.

  sub  (default) corrected = px - ref + 128        <- validated, use this
  mul            corrected = px * mean(ref) / ref  <- clips badly, see below
  v250           corrected = px * 250 / ref        <- an earlier recipe

The multiplicative forms divide by a reference that spans roughly 31..248 at
gain 6, so they scale parts of the frame by up to 3.6x, clip at 255 and destroy
ridge structure: frames corrected that way lose so much coherent area that
em_match returns its -1 "not enough overlap" sentinel. Subtraction is the
physically right model for a per-sensel offset and does not clip meaningfully
(2.5 % of pixels on this unit's captures).

The reference is built only from no-finger captures, never from the frames being
corrected, so nothing about a press leaks into its own correction.

Usage, from the repository root, with a data root holding the capture blocks:

  python3 tools/flatfield.py --data-root <dir> --out <dir> \
      --ref-gain0 'frames/baseline_*.bin' --ref-gain6 'frames/g6base_*.bin' \
      --gain6 'session_*'

Raw frames are biometrics and are not in this repository.
"""
import argparse, glob, os
import numpy as np


def load(p):
    return np.fromfile(p, dtype=np.uint8).astype(np.float64)


def reference(pattern):
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise SystemExit('no reference frames match ' + pattern)
    return np.mean([load(p) for p in paths], axis=0), len(paths)


def correct(px, ref, variant):
    if variant == 'sub':
        out = px - ref + 128.0
    elif variant == 'mul':
        out = px * ref.mean() / np.maximum(ref, 1.0)
    else:
        out = px * 250.0 / np.maximum(ref, 1.0)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--ref-gain0', required=True, help='glob of no-finger frames at low gain')
    ap.add_argument('--ref-gain6', default='', help='glob of no-finger frames at high gain')
    ap.add_argument('--gain6', default='', help='comma-separated globs of blocks captured at high gain')
    ap.add_argument('--variant', default='sub', choices=('sub', 'mul', 'v250'))
    a = ap.parse_args()

    r0, n0 = reference(a.ref_gain0)
    print(f'  low-gain reference:  {n0} frames, per-pixel std {r0.std():.2f}')
    r6 = None
    if a.ref_gain6:
        r6, n6 = reference(a.ref_gain6)
        print(f'  high-gain reference: {n6} frames, per-pixel std {r6.std():.2f}')

    hi = set()
    for pat in (p for p in a.gain6.split(',') if p):
        hi |= {os.path.basename(d.rstrip('/'))
               for d in glob.glob(os.path.join(a.data_root, pat)) if os.path.isdir(d)}

    n, clipped, total = 0, 0, 0
    for d in sorted(glob.glob(os.path.join(a.data_root, '*'))):
        if not os.path.isdir(d):
            continue
        block = os.path.basename(d)
        ref = r6 if block in hi else r0
        if ref is None:
            raise SystemExit(f'{block} needs a high-gain reference; pass --ref-gain6')
        os.makedirs(os.path.join(a.out, block), exist_ok=True)
        for p in sorted(glob.glob(d + '/*.bin')):
            v = load(p)
            raw = v - ref + 128.0 if a.variant == 'sub' else None
            if raw is not None:
                clipped += int(((raw < 0) | (raw > 255)).sum())
                total += raw.size
            correct(v, ref, a.variant).tofile(
                os.path.join(a.out, block, os.path.basename(p)))
            n += 1
        print(f'  {block}: {len(glob.glob(d + "/*.bin"))} frames, '
              f'{"high" if block in hi else "low"}-gain reference')
    if total:
        print(f'  clipped {clipped} of {total} px ({100.0 * clipped / total:.2f} %)')
    print(f'  wrote {n} frames to {a.out} (variant={a.variant})')


if __name__ == '__main__':
    main()
