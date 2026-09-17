#!/usr/bin/env python3
"""Evaluate an egis_match*.c front-end on a directory of raw frames.

Builds nothing itself: point --bin at a binary built from tools/frontend_eval.c
linked against the front-end under test, e.g.

  cc -O2 -Idriver tools/frontend_eval.c driver/egis_match.c       -o /tmp/fe_base  -lm
  cc -O2 -Idriver tools/frontend_eval.c driver/egis_match_gabor.c -o /tmp/fe_gabor -lm
  python3 tools/eval_frontend.py --bin /tmp/fe_gabor --data-root <dir>

Reported numbers are CROSS-FOLD: the threshold is the strictest
zero-false-accept point on one fold and is applied to the held-out fold, both
ways. A threshold chosen on the data it is measured on proves nothing.

The data root holds capture blocks. Two layouts are understood:
  dataset/f<N>_<PP>.bin                 -- N fingers x P presses, synthetic split
  <session>/{enroll,genuine,impostor-*}_<PP>.bin  -- as captured by test_matching.py

Raw frames are biometrics and are not in this repository.
"""
import argparse, glob, os, subprocess, sys, collections

def excluded(path, exclude):
    """An exclude entry is either a bare basename, which drops that name in
    every block, or '<block>/<basename>', which drops it only in that block.
    Ghost frames are block-specific, so the qualified form is what you want."""
    base = os.path.basename(path)
    qual = os.path.basename(os.path.dirname(path)) + '/' + base
    return base in exclude or qual in exclude


def blocks(root, exclude, enroll):
    out = []
    ds = os.path.join(root, 'dataset')
    if os.path.isdir(ds):
        fingers = sorted({os.path.basename(p).split('_')[0]
                          for p in glob.glob(ds + '/f*_*.bin')})
        for f in fingers:
            pr = sorted(glob.glob(f'{ds}/{f}_*.bin'))
            if len(pr) < 4:
                continue
            cut = enroll if enroll else len(pr) // 2 + (len(pr) % 2)
            others = [p for g in fingers if g != f
                      for p in sorted(glob.glob(f'{ds}/{g}_*.bin'))[cut:]]
            out.append((f'dataset:{f}', pr[:cut], pr[cut:], others))
    for d in sorted(glob.glob(root + '/*')):
        if not os.path.isdir(d) or os.path.basename(d) == 'dataset':
            continue
        keep = lambda pat: [p for p in sorted(glob.glob(f'{d}/{pat}'))
                            if not excluded(p, exclude)]
        en, ge = keep('enroll_*.bin'), keep('genuine_*.bin')
        im = keep('impostor-*.bin')
        if en and ge and im:
            out.append((os.path.basename(d), en, ge, im))
    return out

def run(binp, en, ge, im, tmp):
    for nm, lst in (('en', en), ('gen', ge), ('imp', im)):
        open(f'{tmp}/{nm}.txt', 'w').write('\n'.join(lst) + '\n')
    txt = subprocess.run([binp, f'{tmp}/en.txt', f'{tmp}/gen.txt', f'{tmp}/imp.txt'],
                         capture_output=True, text=True, check=True).stdout
    rows, params = [], None
    for line in txt.strip().split('\n'):
        p = line.split()
        if p[0] == 'PARAMS':
            params = (float(p[1]), float(p[2]))
        elif p[0] in ('G', 'I'):
            rows.append((p[0], float(p[1])))
    return params, rows

def rates(rows, th):
    g = [v for k, v in rows if k == 'G']
    i = [v for k, v in rows if k == 'I']
    return (100.0 * sum(v < th for v in g) / len(g),
            100.0 * sum(v >= th for v in i) / len(i), len(g), len(i))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bin', required=True)
    ap.add_argument('--data-root', required=True)
    ap.add_argument('--exclude', default='',
                    help="comma-separated frames to drop, as 'name.bin' or "
                         "'block/name.bin' (ghost frames found by the "
                         "cross-label duplicate scan are block-specific)")
    ap.add_argument('--enroll', type=int, default=0,
                    help='presses per finger used as templates in the dataset/ '
                         'layout (default: half). Sessions use their enroll_* files.')
    ap.add_argument('--fold-a', default='',
                    help='comma-separated block tags forming fold A; the rest '
                         'form fold B. Default: alternate blocks.')
    ap.add_argument('--tmp', default='/tmp')
    a = ap.parse_args()
    exclude = {s for s in a.exclude.split(',') if s}
    blk = blocks(a.data_root, exclude, a.enroll)
    if not blk:
        sys.exit('no capture blocks found under ' + a.data_root)
    folds = collections.defaultdict(list)
    params = None
    for n, (tag, en, ge, im) in enumerate(blk):
        params, rows = run(a.bin, en, ge, im, a.tmp)
        fa = {t for t in a.fold_a.split(',') if t}
        side = ('A' if tag in fa else 'B') if fa else 'AB'[n % 2]
        folds[side].extend(rows)
        print(f'  [{side}] {tag}: {len(en)} enrol, {len(ge)} genuine, '
              f'{len(im)} impostor')
    print(f'\n  front-end operating point: threshold {params[0]}, '
          f'min_coverage {params[1]}')
    tot = []
    print('\nCROSS-FOLD (threshold from the train fold, applied to the held-out fold)')
    for tr, te in (('A', 'B'), ('B', 'A')):
        th = max(v for k, v in folds[tr] if k == 'I') + 1e-9
        frr, far, ng, ni = rates(folds[te], th)
        tot.append((frr, far, ng, ni))
        print(f'  train {tr} -> test {te}:  th {th:.3f}   '
              f'FRR {frr:5.1f}%  FAR {far:5.1f}%   (n {ng} gen / {ni} imp)')
    wf = sum(f * n for f, _, n, _ in tot) / sum(n for _, _, n, _ in tot)
    wa = sum(f * n for _, f, _, n in tot) / sum(n for _, _, _, n in tot)
    print(f'  POOLED HELD-OUT:          FRR {wf:5.1f}%  FAR {wa:5.1f}%')

if __name__ == '__main__':
    main()
