# usernamed

A fast, extensible username permutation generator for OSINT and authorized
penetration testing engagements — built as a more complete alternative to
[username-anarchy](https://github.com/urbanadventurer/username-anarchy).

Given a list of names, `usernamed` streams out common corporate username
conventions (`first.last`, `f.last`, `flast`, `first.l`, `FLast`, ...),
including several formats the original tool doesn't generate.

## Why

username-anarchy is a great starting point but its plugin set has gaps —
for example it has no `first.l` (`john.s`) format despite covering the
mirror case `f.last`. `usernamed` fills those gaps and adds a few
capabilities aimed at larger, messier real-world name lists:

- 33 built-in formats, including mixed-case forms (`FLast`, `FirstLast`)
- Common first-name nickname expansion (`Daniel` → `dan`, `danny`)
- Accepts `First Last` and `Last, First` input interchangeably
- Streaming/generator-based — low memory footprint on large lists
- No dependencies beyond the Python standard library

## Install

```bash
git clone https://github.com/<your-username>/usernamed.git
cd usernamed
chmod +x usernamed.py
```

Requires Python 3.8+. No external packages needed.

## Usage

```bash
# Generate every format for a name list
./usernamed.py -i names.txt -o users.txt

# Only specific formats
./usernamed.py -i names.txt -f first.last,f.last,first.l

# Append a domain, e.g. for password spraying prep
./usernamed.py -i names.txt --domain corp.local -f first.last

# Expand common nicknames too (Daniel -> dan, danny)
./usernamed.py -i names.txt --nicknames

# List every available format with an example
./usernamed.py --list-formats

# Read from stdin and pipe straight into another tool
cat names.txt | ./usernamed.py -i - -f first.last | kerbrute userenum --dc dc01.corp.local -d corp.local -
```

### Input format

One name per line, either order:

```
Mitch Ressek
Ressek, Mitch
Mitch Alan Ressek
```

Lines that can't be parsed into at least a first and last name are skipped
with a warning on stderr, not a hard failure.

### Options

| Flag | Description |
|---|---|
| `-i, --input` | Input file, one name per line (`-` for stdin) |
| `-o, --output` | Output file (default: stdout) |
| `-f, --formats` | Comma-separated list of formats (default: all) |
| `--domain` | Append `@domain` to every username |
| `--case {lower,upper,title,asis}` | Output casing (default: `lower`) |
| `--no-dedupe` | Skip dedupe for O(1) memory on huge inputs |
| `--numeric-suffix` | Also emit a trailing `1` variant (`jsmith` / `jsmith1`) |
| `--nicknames` | Also generate usernames from common first-name nicknames |
| `--list-formats` | Print all available formats with examples |
| `-v, --verbose` | Print progress info to stderr |

Run `./usernamed.py --list-formats` for the full, current list — it's the
source of truth over this README.

## Development

```bash
pip install pytest
pytest
```

## Disclaimer

This tool is intended for authorized security testing, OSINT research, and
CTF use only. Only run it against systems and accounts you have explicit
permission to test. The author is not responsible for misuse.

## License

MIT — see [LICENSE](LICENSE).
