/* Evaluate whichever egis_match*.c front-end is linked in, on manifests of
 * raw frames. Prints one line per probe decision.
 *
 * em_match(a, b) is template-first and the Gabor front-end is not symmetric,
 * so the call here is em_match(&template, &probe), matching the driver.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "egis_match.h"

/* em_match_threshold / em_min_coverage arrive with the front-end interface
 * change; declared weak so this tool also builds against a driver that does
 * not have them yet, and reports 0 for an absent one. */
extern const double em_match_threshold __attribute__ ((weak));
extern const double em_min_coverage __attribute__ ((weak));

#define MAXF 96

static int
load_raw (const char *p, uint8_t *b)
{
  FILE *f = fopen (p, "rb");
  if (!f) return -1;
  size_t n = fread (b, 1, EM_N, f);
  fclose (f);
  return n == EM_N ? 0 : -1;
}

/* Reads at most MAXF names and REFUSES a longer manifest. The first version
 * stopped silently at MAXF: handed 2304 frames it scored the first 96, all at
 * one end of the sweep, and reported a reassuring maximum that was purely an
 * artefact of the truncation. A caller cannot tell that from a real result,
 * so this now fails loudly instead of returning a short list. */
static int
read_manifest (const char *path, char names[MAXF][512])
{
  FILE *f = fopen (path, "r");
  if (!f) { fprintf (stderr, "no manifest %s\n", path); exit (1); }
  int n = 0;
  char line[512];
  while (fgets (line, sizeof line, f))
    {
      char *nl = strchr (line, '\n');
      if (nl) *nl = 0;
      if (!line[0]) continue;
      if (n == MAXF)
        {
          fprintf (stderr,
                   "%s: more than MAXF (%d) entries -- refusing to score a "
                   "truncated manifest; split it into chunks\n", path, MAXF);
          exit (1);
        }
      memcpy (names[n], line, sizeof line);
      n++;
    }
  fclose (f);
  if (n == 0) { fprintf (stderr, "%s: empty manifest\n", path); exit (1); }
  return n;
}

static char en[MAXF][512], ge[MAXF][512], im[MAXF][512];
static EmFrame fe[MAXF], fg[MAXF], fi[MAXF];

static void
load_frames (char names[MAXF][512], int n, EmFrame *out)
{
  uint8_t raw[EM_N];
  for (int i = 0; i < n; i++)
    {
      if (load_raw (names[i], raw)) { fprintf (stderr, "load %s\n", names[i]); exit (1); }
      em_frame_compute (raw, &out[i]);
    }
}

int
main (int argc, char **argv)
{
  if (argc < 4) { fprintf (stderr, "usage: %s enroll genuine impostor\n", argv[0]); return 1; }
  int ne = read_manifest (argv[1], en);
  int ng = read_manifest (argv[2], ge);
  int ni = read_manifest (argv[3], im);
  load_frames (en, ne, fe);
  load_frames (ge, ng, fg);
  load_frames (im, ni, fi);

  printf ("PARAMS %.6f %.6f\n",
          &em_match_threshold ? em_match_threshold : 0.0,
          &em_min_coverage ? em_min_coverage : 0.0);
  for (int e = 0; e < ne; e++) printf ("COV E %.6f %s\n", fe[e].coverage, en[e]);

  for (int pass = 0; pass < 2; pass++)
    {
      int np = pass ? ni : ng;
      EmFrame *fp = pass ? fi : fg;
      char (*nm)[512] = pass ? im : ge;
      for (int p = 0; p < np; p++)
        {
          double best = -1.0;
          for (int e = 0; e < ne; e++)
            {
              double s = em_match (&fe[e], &fp[p]);   /* template first */
              if (s > best) best = s;
            }
          printf ("%s %.10f %.6f %s\n", pass ? "I" : "G", best, fp[p].coverage, nm[p]);
        }
    }
  return 0;
}
