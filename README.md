# Linux fingerprint driver for the EgisTec EH576 (USB `1c7a:0576`)

A working **libfprint driver** for the EgisTec EH576 fingerprint sensor, which
upstream libfprint lists as unsupported. If your laptop's fingerprint reader
does nothing on Linux and `lsusb` shows `1c7a:0576`, this is for you.

Confirmed working on a **Lenovo Yoga 7 16IRL8 (82YN)** under Linux Mint 22.2:
enrolment, verification, `sudo`, and unlocking the lock screen with a finger.
Other laptops ship this sensor too — reports welcome, see
[Help wanted](#help-wanted).

```
lsusb | grep 1c7a:0576      # if this prints something, this driver is for you
```

## Status, honestly

**It works, and it is one person's reverse-engineering project rather than a
certified biometric product.** Both halves of that sentence matter.

What is verified: the protocol, capture, enrolment, matching, and the full
fprintd/PAM login path, on one sensor.

What the numbers rest on: two labelled test sessions on **one unit, one
person** — 10 genuine and 16 impostor presses. At the shipped threshold that
gives **0% false accepts and about 10% false rejects** (a rejected press is
just re-pressed). That is enough to show the driver works and nowhere near
enough to quote as a security specification. More testers is the single most
useful thing anyone can contribute.

Use it for convenience — unlocking your own laptop, `sudo` without typing a
long password. **Keep your password working**, which the PAM setup here does
by design. If your machine holds data whose exposure would genuinely hurt,
treat the password as the real boundary.

## Install

Needs a Debian/Ubuntu-family distro (tested on Linux Mint 22.2). Build
dependencies:

```sh
sudo apt install meson ninja-build gcc pkg-config libglib2.0-dev \
                 libgusb-dev libnss3-dev libgudev-1.0-dev git
```

Then:

```sh
git clone https://github.com/tsteppy/egistec-eh576-libfprint.git
cd egistec-eh576-libfprint
./install.sh
```

The script fetches libfprint, adds the driver, builds it, and installs to
`/usr/local` — which precedes `/usr/lib` in the linker search path, so it
takes precedence over your distribution's libfprint **without overwriting a
single packaged file**. It then checks that the linker really does prefer it.

To undo everything: `./install.sh --uninstall`

## Enrol a finger

```sh
fprintd-enroll
```

**Move your finger deliberately between the eight presses**: centred, toward
the tip, toward the knuckle, left, right, rolled left, rolled right, centred
again.

This is not a nicety. The sensor images about 5x4mm — a fraction of your
fingertip — so a press only matches if it lands on skin you enrolled.
Enrolling eight presses at one comfortable position measured a **60%**
false-reject rate; the same eight spread across the fingertip measured
**10%**. `fprintd-enroll` gives no positional prompts, so this is on you.

Then test:

```sh
fprintd-verify
```

### A GUI that guides this properly

Doing those eight presses correctly matters more than it sounds, and
`fprintd-enroll` gives you no help with it. **Fingerprint Setup**
(https://github.com/tsteppy/fingerprint-setup) prompts each press by position,
then runs ten verifications and tells you how well your enrolment actually
performs before you rely on it. It works with any fprintd-supported reader,
not just this one.

## Fingerprint login

Once verification works:

```sh
sudo pam-auth-update --enable fprintd
```

This puts fingerprint authentication ahead of the password prompt for login,
the lock screen and `sudo`, **leaving the password as a fallback** — which
matters, because a press that lands off the enrolled area gets rejected and
you will want to type a password rather than fight the sensor.

Test it before you trust it. Keep a root shell open in a spare terminal
(`sudo -i`), then in a *new* terminal:

```sh
sudo -k && sudo true
```

You should get a fingerprint prompt; ignoring it for ten seconds should fall
through to the password prompt. Once both paths behave, the lock screen works
with no further configuration.

To disable: `sudo pam-auth-update --disable fprintd`

## How it works

Full technical write-up in [`driver/README.md`](driver/README.md). The short
version:

- **Not an `FpImageDevice`.** libfprint's usual path hands images to NBIS
  minutiae matching, which **cannot work here**: bozorth3 refuses to compute
  below 10 minutiae, and a 70x57 frame from this sensor physically contains
  only about 7. The vendor's own Windows driver doesn't use minutiae either.
- **Matching happens on the host, in the driver**, by correlating enhanced
  ridge structure against the enrolled frames. Enrolment stores 8 raw frames;
  verification scores the probe against each and takes the best.
- **Ghost-frame protection.** This sensor intermittently re-serves a stale
  frame from an earlier press, carrying fresh noise so checksums miss it. Left
  unguarded that is an authentication bypass — press any finger, occasionally
  get in. Every capture is checked against a second frame of the same press.

The matcher sits behind a two-function interface (`em_frame_compute` /
`em_match` in `driver/egis_match.h`) so it can be replaced without touching
any USB or state-machine code. One replacement ships in-tree, opt-in:

```
EGIS0576_FRONTEND=gabor ./install.sh
```

links `driver/egis_match_gabor.c` instead of `egis_match.c` — same interface,
an orientation-selective Gabor enhancement in place of the high-pass, a
per-pixel coherence mask and a ±10° rotation search on top of the
translation search, and its own operating point (the threshold and coverage
gate belong to the front-end, `em_match_threshold` / `em_min_coverage`).
On the one unit it was measured on (60 genuine / 480 same-person impostor
press comparisons, raw frames as this driver feeds them) the two populations
stop overlapping: lowest genuine 0.81, highest impostor 0.77, 0 % / 0 % with
the threshold chosen on one half of the data and applied to the other. Every
parameter was chosen on that same unit, which is exactly why it is opt-in
until someone else's score table says the same; the file's header has the
numbers, the cost (4 ms per comparison) and the caveats.

## Known limitations

- **~10% of genuine presses are rejected** and need a second try, usually
  because the press landed away from enrolled skin. Re-enrolling with wider
  coverage helps.
- **Numbers come from one sensor and one person.** See
  [Help wanted](#help-wanted).
- **Debian/Ubuntu-family only** so far — nothing is distro-specific except the
  library path and package names, so ports should be easy.
- **No suspend/resume handling** beyond libfprint's defaults.

### Hardware warnings

- **Never USB-reset this sensor** (`usbreset`, pyusb `dev.reset()`). The
  firmware hangs and the device vanishes from the bus until a full
  **power-off** — a reboot is not enough.
- A second image request without re-arming returns a blank frame. Treat an
  all-zero frame as an invalid capture, never as "no finger".

## Help wanted

The most valuable contribution is **data from other hardware**. If you have an
EH576:

1. Install, enrol, and run `python3 tools/test_matching.py`. It prompts for
   each press by name, labels every frame, and prints a score table.
2. Open an issue with your **laptop model, distro, and the score table**.

**Never upload raw fingerprint captures.** They are your biometrics, they
cannot be reissued, and this project does not want them. Scores, models and
logs only — the harness is built so the numbers alone are useful.

Also useful: ports to other distros, a replacement matcher (the interface is
deliberately small), and anyone who wants to push this upstream into libfprint
properly.

## Credits

Built on the reverse-engineering work in
[Pengu601/EgisTec-EH576](https://github.com/Pengu601/EgisTec-EH576) — the
init/repeat command sequences and variance-based finger detection come from
that project, as does the earlier
[Animeshz/EgisTec-EH575](https://github.com/Animeshz/EgisTec-EH575) work it
builds on. Additional protocol details (the gain register, the vendor's image
preprocessing and quality metrics) were recovered from EgisTec's Windows
driver.

Driver structure follows libfprint's `egis0570` and `egismoc` drivers.

## License

LGPL-2.1-or-later, matching libfprint. See [LICENSE](LICENSE).
