#!/usr/bin/env python3
"""Check the blank-frame gate against real captures.

The gate in driver/egis_blank.h rejects an enrolment frame that correlates too
well with a no-finger reference, because a frame with no finger on the sensor
is the fixed pattern and nothing else. This tool measures the two populations
on a local capture set and reports whether EGIS0576_BLANK_THRESHOLD separates
them, with the margin either side.

  python3 tools/blank_gate_check.py --data-root <dir> \
      --ref 'frames/baseline_*.bin' --presses 'dataset/*.bin' 'session_*/*.bin'

The reference is built leave-one-out when scoring the reference frames
themselves, so no frame is ever compared against a reference built from it.

Raw frames are biometrics and are not in this repository.
"""
import argparse, glob, os, re, sys

def read_threshold(root):
    """single source of truth: the constant the driver actually ships"""
    hdr = os.path.join(root, 'driver', 'egis_blank.h')
    m = re.search(r'#define\s+EGIS0576_BLANK_THRESHOLD\s+([0-9.]+)', open(hdr).read())
    if not m:
        sys.exit("no EGIS0576_BLANK_THRESHOLD in %s" % hdr)
    return float(m.group(1))

def load(p):
    import numpy as np
    return np.fromfile(p, dtype='uint8').astype(float)

def main():
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', required=True)
    ap.add_argument('--repo-root', default=os.path.dirname(os.path.dirname(
                                            os.path.abspath(__file__))))
    ap.add_argument('--ref', action='append', required=True,
                    help='glob of no-finger frames, repeatable (one per gain)')
    ap.add_argument('--presses', nargs='+', required=True,
                    help='globs of real presses')
    a = ap.parse_args()
    th = read_threshold(a.repo_root)
    r = lambda x, y: float(np.corrcoef(x, y)[0, 1])

    refsets = [sorted(glob.glob(os.path.join(a.data_root, g))) for g in a.ref]
    if not refsets[0]:
        sys.exit("no reference frames matched %s" % a.ref[0])
    primary = np.mean([load(p) for p in refsets[0]], axis=0)

    blanks = []
    for i, group in enumerate(refsets):
        for j, p in enumerate(group):
            if i == 0:                      # leave-one-out against its own set
                others = [load(q) for k, q in enumerate(group) if k != j]
                if len(others) < 2:
                    continue
                blanks.append((p, r(load(p), np.mean(others, axis=0))))
            else:                           # other gains: score vs the primary
                blanks.append((p, r(load(p), primary)))

    presses = []
    for g in a.presses:
        for p in sorted(glob.glob(os.path.join(a.data_root, g))):
            presses.append((p, r(load(p), primary)))
    if not presses:
        sys.exit("no press frames matched %s" % a.presses)

    # a press glob may contain blanks; the point of the gate is that they
    # separate, so report them rather than silently averaging them in
    suspect = [(p, v) for p, v in presses if v > th]
    clean = [(p, v) for p, v in presses if v <= th]

    print("EGIS0576_BLANK_THRESHOLD = %.2f\n" % th)
    print("  %-28s n=%3d   %.4f to %.4f" % ("no-finger reference frames",
          len(blanks), min(v for _, v in blanks), max(v for _, v in blanks)))
    print("  %-28s n=%3d   %.4f to %.4f" % ("frames with a finger on",
          len(clean), min(v for _, v in clean), max(v for _, v in clean)))
    if suspect:
        print("\n  %d frame(s) in the press globs are blank and would be rejected:"
              % len(suspect))
        for p, v in sorted(suspect, key=lambda kv: -kv[1]):
            print("     %-52s %.4f" % (os.path.relpath(p, a.data_root), v))

    worst_press = max(v for _, v in clean)
    best_blank = min(v for _, v in blanks)
    ok = worst_press < th < best_blank
    print("\n  margin below the nearest blank : %+.4f" % (best_blank - th))
    print("  margin above the worst press   : %+.4f" % (th - worst_press))
    print("\n%s" % ("separated" if ok else
          "NOT SEPARATED: the threshold does not lie between the two populations"))
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
