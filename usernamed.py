#!/usr/bin/env python3
"""
usernamed.py — extensive username permutation generator for engagements.

A drop-in replacement for username-anarchy: reads a list of names (one per
line, "First [Middle] Last" or "Last, First [Middle]") and streams out
usernames across a wide set of corporate naming conventions, including
several username-anarchy's stock plugins don't cover (first.l, l.f, FLast,
mixed-case forms, nickname expansion, etc.)

Usage:
    ./usernamed.py -i Team.txt -o users.txt
    ./usernamed.py -i Team.txt -f first.last,f.last,first.l
    ./usernamed.py -i Team.txt --domain example.com --nicknames
    ./usernamed.py --list-formats
    ./usernamed.py -i Team.txt --case upper --numeric-suffix
    cat Team.txt | ./usernamed.py -i -            # read from stdin

Design notes (why this scales better than username-anarchy for large lists):
    - Everything is generator-based end-to-end: names are read, permuted,
      and written line-by-line. Nothing is materialized as a full list
      unless you ask for dedupe (which needs a seen-set by definition).
    - --no-dedupe gives true O(1) memory regardless of input size.
    - Output is written incrementally, so you can pipe directly into
      another tool (kerbrute, o365spray, etc.) without waiting on the
      whole file.
"""

import argparse
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Format definitions
#
# Each formatter takes (first, middle, last) — lowercase, ascii-folded,
# alnum-only, middle possibly "" — and returns a username or None if it
# can't be produced (e.g. no middle name available). Formatters that need
# mixed/title case do their own capitalization so --case can still override
# them explicitly if the user passes --case.
# ---------------------------------------------------------------------------

def fi(s):
    return s[0] if s else ""


def cap(s):
    return s[:1].upper() + s[1:] if s else s


# name -> (function, human description)
FORMATS = {
    # Simple
    "first":            (lambda f, m, l: f,                              "john"),
    "last":             (lambda f, m, l: l,                              "smith"),

    # Full name combos
    "firstlast":        (lambda f, m, l: f + l,                          "johnsmith"),
    "lastfirst":        (lambda f, m, l: l + f,                          "smithjohn"),
    "first.last":       (lambda f, m, l: f"{f}.{l}",                     "john.smith"),
    "last.first":       (lambda f, m, l: f"{l}.{f}",                     "smith.john"),
    "first_last":       (lambda f, m, l: f"{f}_{l}",                     "john_smith"),
    "last_first":       (lambda f, m, l: f"{l}_{f}",                     "smith_john"),
    "first-last":       (lambda f, m, l: f"{f}-{l}",                     "john-smith"),
    "last-first":       (lambda f, m, l: f"{l}-{f}",                     "smith-john"),

    # Initial + full name
    "f.last":           (lambda f, m, l: f"{fi(f)}.{l}",                 "j.smith"),
    "last.f":           (lambda f, m, l: f"{l}.{fi(f)}",                 "smith.j"),
    "flast":            (lambda f, m, l: f"{fi(f)}{l}",                  "jsmith"),
    "lastf":            (lambda f, m, l: f"{l}{fi(f)}",                  "smithj"),

    # Full name + initial (the pair username-anarchy is missing)
    "first.l":          (lambda f, m, l: f"{f}.{fi(l)}",                 "john.s"),
    "l.first":          (lambda f, m, l: f"{fi(l)}.{f}",                 "s.john"),
    "firstl":           (lambda f, m, l: f"{f}{fi(l)}",                  "johns"),
    "lfirst":           (lambda f, m, l: f"{fi(l)}{f}",                  "sjohn"),

    # Both initials
    "fl":               (lambda f, m, l: f"{fi(f)}{fi(l)}",              "js"),
    "lf":               (lambda f, m, l: f"{fi(l)}{fi(f)}",              "sj"),
    "f.l":              (lambda f, m, l: f"{fi(f)}.{fi(l)}",             "j.s"),
    "l.f":              (lambda f, m, l: f"{fi(l)}.{fi(f)}",             "s.j"),

    # Truncated / mixed length (common AD-migration conventions)
    "first[4]last[4]":  (lambda f, m, l: f[:4] + l[:4],                  "johnsmit"),
    "first[3]last[3]":  (lambda f, m, l: f[:3] + l[:3],                  "johsmi"),
    "firstlast[8]":      (lambda f, m, l: (f + l)[:8],                   "johnsmit"),

    # Middle-name-aware (only emitted when a middle name exists)
    "first.m.last":     (lambda f, m, l: f"{f}.{m}.{l}" if m else None,       "john.michael.smith"),
    "first.mi.last":    (lambda f, m, l: f"{f}.{fi(m)}.{l}" if m else None,   "john.m.smith"),
    "fmlast":           (lambda f, m, l: f"{fi(f)}{fi(m)}{l}" if m else None, "jmsmith"),
    "fml":              (lambda f, m, l: f"{fi(f)}{fi(m)}{fi(l)}" if m else None, "jms"),
    "firstmiddlelast":  (lambda f, m, l: f + m + l if m else None,            "johnmichaelsmith"),

    # Mixed / title-case forms (kept distinct from --case, matching
    # username-anarchy's FLast/FL/FirstLast/First.Last/Last plugins)
    "FLast":            (lambda f, m, l: fi(f).upper() + l,              "Jsmith"),
    "FL":               (lambda f, m, l: fi(f).upper() + fi(l).upper(),  "JS"),
    "FirstLast":        (lambda f, m, l: cap(f) + cap(l),                "JohnSmith"),
    "First.Last":       (lambda f, m, l: f"{cap(f)}.{cap(l)}",           "John.Smith"),
    "Last":             (lambda f, m, l: cap(l),                        "Smith"),
}

DEFAULT_FORMATS = list(FORMATS.keys())

# A compact common-nickname table. Only expands the FIRST name; enabled
# with --nicknames. Not exhaustive by design — it's meant to catch the
# high-frequency cases you'll actually see in a corporate directory.
NICKNAMES = {
    "robert": ["rob", "bob", "bobby"],
    "william": ["will", "bill", "liam", "billy"],
    "richard": ["rick", "rich", "dick"],
    "michael": ["mike", "mick", "mickey"],
    "james": ["jim", "jimmy", "jamie"],
    "john": ["jack", "johnny"],
    "joseph": ["joe", "joey"],
    "daniel": ["dan", "danny"],
    "david": ["dave", "davey"],
    "charles": ["charlie", "chuck"],
    "christopher": ["chris", "topher"],
    "matthew": ["matt"],
    "anthony": ["tony"],
    "andrew": ["andy", "drew"],
    "alexander": ["alex", "xander"],
    "benjamin": ["ben", "benny"],
    "samuel": ["sam", "sammy"],
    "nicholas": ["nick", "nico"],
    "edward": ["ed", "eddie", "ted"],
    "thomas": ["tom", "tommy"],
    "patrick": ["pat", "paddy"],
    "elizabeth": ["liz", "beth", "eliza", "betty"],
    "katherine": ["kate", "katie", "kat"],
    "margaret": ["maggie", "meg", "peggy"],
    "jennifer": ["jen", "jenny"],
    "jessica": ["jess"],
    "rebecca": ["becky", "becca"],
    "victoria": ["vicky", "tori"],
    "susan": ["sue", "susie"],
    "deborah": ["deb", "debbie"],
    "cynthia": ["cindy"],
    "kimberly": ["kim"],
}


def strip_accents(s: str) -> str:
    """Fold names like 'Radzík' or accented chars to plain ascii."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clean_token(s: str) -> str:
    return "".join(c for c in s if c.isalnum())


def parse_name(line: str):
    """
    Parse a raw name line into (first, middle, last) lowercase ascii parts.
    Accepts both "First [Middle] Last" and "Last, First [Middle]".
    Returns None if the line can't be parsed into at least two components.
    """
    raw = strip_accents(line.strip())
    if not raw:
        return None

    if "," in raw:
        # "Last, First Middle"
        last_part, _, rest = raw.partition(",")
        rest_parts = rest.split()
        if not rest_parts:
            return None
        first = rest_parts[0]
        middle = rest_parts[1] if len(rest_parts) > 2 else ""
        last = last_part.strip()
    else:
        parts = raw.split()
        if len(parts) < 2:
            return None
        first = parts[0]
        last = parts[-1]
        middle = parts[1] if len(parts) > 2 else ""

    first, middle, last = clean_token(first).lower(), clean_token(middle).lower(), clean_token(last).lower()
    if not first or not last:
        return None
    return first, middle, last


def apply_case(s: str, mode: str) -> str:
    if mode == "lower":
        return s.lower()
    if mode == "upper":
        return s.upper()
    if mode == "title":
        return "-".join(w.capitalize() for w in s.split("-"))
    return s  # "asis" — respect whatever the format itself produced


def iter_names(path: Path, verbose: bool):
    """Yield (first, middle, last) tuples, streaming the file line by line."""
    fh = sys.stdin if str(path) == "-" else path.open(encoding="utf-8")
    try:
        count = 0
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parsed = parse_name(line)
            if not parsed:
                print(f"[!] Skipping unparsable line: {line!r}", file=sys.stderr)
                continue
            count += 1
            yield parsed
        if verbose:
            print(f"[+] Parsed {count} names", file=sys.stderr)
    finally:
        if fh is not sys.stdin:
            fh.close()


def expand_nicknames(first, middle, last, use_nicknames):
    """Yield (first, middle, last) variants — the canonical name plus any
    known nicknames for the first name, when --nicknames is set."""
    yield first, middle, last
    if use_nicknames:
        for nick in NICKNAMES.get(first, []):
            yield nick, middle, last


def generate(names_iter, formats, domain, case_mode, dedupe, numeric_suffix, use_nicknames):
    """Generator yielding final username strings, one at a time."""
    seen = set() if dedupe else None

    for first, middle, last in names_iter:
        for f, m, l in expand_nicknames(first, middle, last, use_nicknames):
            for fmt_name in formats:
                fn, _desc = FORMATS[fmt_name]
                uname = fn(f, m, l)
                if not uname:
                    continue
                uname = apply_case(uname, case_mode)

                candidates = [uname]
                if numeric_suffix:
                    candidates.append(f"{uname}1")

                for cand in candidates:
                    final = f"{cand}@{domain}" if domain else cand
                    if seen is not None:
                        if final in seen:
                            continue
                        seen.add(final)
                    yield final


def list_formats():
    width = max(len(name) for name in FORMATS)
    for name, (_fn, desc) in FORMATS.items():
        print(f"{name:<{width}}  e.g. {desc}")


def main():
    ap = argparse.ArgumentParser(description="Generate username permutations from a name list.")
    ap.add_argument("-i", "--input", type=Path, help="Input file, one name per line ('-' for stdin)")
    ap.add_argument("-o", "--output", type=Path, help="Output file (default: stdout)")
    ap.add_argument("-f", "--formats", help="Comma-delimited list of formats to use (default: all)")
    ap.add_argument("--domain", help="Append @domain to every generated username")
    ap.add_argument("--case", choices=["lower", "upper", "title", "asis"], default="lower",
                     help="Output case (default: lower; 'asis' preserves each format's own casing)")
    ap.add_argument("--no-dedupe", action="store_true", help="Skip dedupe for O(1) memory on huge inputs")
    ap.add_argument("--numeric-suffix", action="store_true", help="Also emit a trailing '1' variant (jsmith / jsmith1)")
    ap.add_argument("--nicknames", action="store_true", help="Also generate usernames from common first-name nicknames")
    ap.add_argument("--list-formats", action="store_true", help="List available format names with examples and exit")
    ap.add_argument("-v", "--verbose", action="store_true", help="Print progress info to stderr")
    args = ap.parse_args()

    if args.list_formats:
        list_formats()
        return

    if not args.input:
        ap.error("-i/--input is required (use '-' to read from stdin)")

    formats = args.formats.split(",") if args.formats else DEFAULT_FORMATS
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        print(f"[!] Unknown format(s): {', '.join(unknown)}", file=sys.stderr)
        print("    Run --list-formats to see valid names.", file=sys.stderr)
        sys.exit(1)

    if str(args.input) != "-" and not args.input.exists():
        print(f"[!] Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    names_iter = iter_names(args.input, args.verbose)
    results = generate(
        names_iter,
        formats,
        args.domain,
        args.case,
        dedupe=not args.no_dedupe,
        numeric_suffix=args.numeric_suffix,
        use_nicknames=args.nicknames,
    )

    out_fh = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    count = 0
    try:
        for uname in results:
            out_fh.write(uname + "\n")
            count += 1
    finally:
        if args.output:
            out_fh.close()

    if args.output or args.verbose:
        print(f"[+] Wrote {count} usernames" + (f" to {args.output}" if args.output else ""), file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Graceful exit when piped into head/grep/etc. and the reader closes early.
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
