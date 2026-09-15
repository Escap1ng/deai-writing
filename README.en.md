# deai-writing

[中文](README.md) | English

Three runnable gates for any Chinese or English draft: remove the AI-slop habits, and remove the invisible watermark characters. The rules run, re-check and regress on their own, so you do not have to rely on how a draft feels.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What it does

- **Word list.** `code/check_phrasing.py` reads `code/phrasing-blacklist.json` and scans for template openers, filler, empty claims and fake-insight phrasing, in Chinese and English alike. It exits 1 on any hit and prints the fix for each one. There are 21 rules, and the `en-slop-*` ones cover English drafts.
- **Structure.** `code/check_style.py` measures six things: over-long passive sentences, repeated sentence openings, transition-word density, the long-to-short sentence ratio, paragraph length rhythm, and decimal places in results. It reports a risk level of `low` / `medium` / `high` / `very high`.
- **Characters.** `code/strip_invisible.py` strips zero-width characters, bidi controls, tag characters and variation selectors, covering `.tex`, `.docx`, `.pdf` and plain text.

**Scope.** It only touches wording and characters. Facts, data and conclusions stay as they are. De-slopping is not the same as making writing casual; the test is whether only this author could have written the sentence, drawn from that author's own judgements, numbers and limits.

## Quick start

### Install

Drop this repository into your agent's skills directory:

```
<project>/.trae/skills/deai-writing/
```

The scripts use the Python standard library only. PDF mode additionally needs PyMuPDF (`pip install pymupdf`). No host framework required.

### Run the three gates

```bash
python3 code/check_phrasing.py draft.md                # word list: exit 1 on any hit
python3 code/check_style.py draft.md                   # structure: exit 1 on any hit
python3 code/strip_invisible.py --clean draft.tex      # characters: clean in place, keep a .bak
python3 code/check_phrasing.py --list-rules            # show the rules and their fixes
python3 code/check_style.py --list-metrics             # show the metrics and thresholds
```

Rewrite each hit along the fix printed after `→`: add the number, name the source, split the long sentence, widen the gap between neighbouring paragraphs. Re-check until both checkers exit 0. Do not ship while the structural risk level reads `high` or `very high`. A rule carrying `max_per_document` is a frequency cap, and only uses above the cap count as hits. The final PDF and Word file must both be cleaned and re-checked; a `CLEANED-RESIDUAL` report means do not ship.

### Regression self-check

```bash
python3 code/selfcheck.py                              # 12 assertions: fixtures, doc self-check, character round-trip
```

Run it whenever you change the word list, a threshold or a fixture.

## Repository layout

```
deai-writing/
├── SKILL.md                       # Entry point: scope, three gates, quick flow, hard requirements
├── README.md                      # Chinese README: quick start, layout, rationale, conventions
├── README.en.md                   # This file: the same structure in English
├── code/                          # Runnable scripts and data
│   ├── check_phrasing.py          #   Word-list checker: template openers, filler, empty claims, fake insight
│   ├── phrasing-blacklist.json    #   Chinese and English rules (single source of truth; add words here only)
│   ├── check_style.py             #   Structural checker: six metrics plus a risk level
│   ├── strip_invisible.py         #   Character cleaner: tex, docx, pdf and plain text
│   └── selfcheck.py               #   Regression self-check: asserts the expected exit code of every fixture
├── docs/                          # Specifications
│   ├── deai-rules.md              #   Chinese rules, the authoritative source: hint list, rewrite rules, negative list, voice preservation, abstract de-templating, structural details, character cleaning
│   └── no-ai-slop-reference.md    #   English reference: slop pattern catalogue and rule mapping (MIT, source SHA and notice kept)
└── examples/                      # Reproducible fixtures
    ├── clean-sample.md            #   Chinese positive: both checkers must report zero
    ├── clean-sample.tex           #   Chinese positive in LaTeX, covering the .tex code path
    ├── slop-sample.md             #   Chinese negative: dense word-list hits
    ├── style-slop-sample.md       #   Chinese negative: dense structural hits
    ├── clean-sample-en.md         #   English positive
    └── slop-sample-en.md          #   English negative: dense en-slop hits
```

## Relationship to upstream

The English slop pattern catalogue and its sentence-level taxonomy come from [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop). This repository adds three things on top:

- The catalogue turned into 21 runnable rules that cover Chinese and English; adding a word means editing `code/phrasing-blacklist.json` only.
- Chinese rules, plus the structural and character gates, so a vague sense of AI-ness becomes a reproducible exit code.
- Fixtures wired to `code/selfcheck.py`, so an expected-result table that used to be checked by eye now fails when it drifts.

## Layout rationale

- **Top level split by content type**: `code/`, `docs/`, `examples/`. The vocabulary is stable across searches: `code/` is always runnable scripts and data, `docs/` is always specification, `examples/` is always reproducible fixtures.
- **The word list is data, not code**: `code/phrasing-blacklist.json` is read by the checker and can also be consumed by third-party programs. Adding a word means editing that one file, and `check_phrasing.py` plus `docs/deai-rules.md` follow.
- **Two levels deep at most**: files sit directly under `code/`, `docs/` and `examples/`.

## Extending it

Checklist for adding a rule or a cleaning rule set:

```
code/phrasing-blacklist.json    # add one entry under rules (id/label/severity/why/fix/patterns/max_per_document)
docs/deai-rules.md              # document it in one line (counter-examples stay in backticks so the doc self-checks)
examples/                       # add a positive or negative fixture when needed
python3 code/selfcheck.py       # run the regression and confirm every assertion still passes
```

Conventions:

- Every word-list rule carries `why` (why it reads as a hint) and `fix` (how to rewrite it). The checker prints both, so every hit arrives with a repair.
- Structural thresholds live in the constants at the top of `code/check_style.py`. Changing one means updating `docs/deai-rules.md` and the expected results in `examples/`.
- Patterns use Python `re` syntax. A broken pattern must raise rather than be skipped, so rules are pre-compiled at load time.
- Counter-examples inside the specification docs stay wrapped in backticks, which keeps those files passing the word-list check.
- Every script exposes an `argparse` entry point and uses the same exit codes: `0` pass, `1` check failed, `2` usage or environment error.
- Run `python3 code/selfcheck.py` after adding or changing a fixture.

## Credits and license

The rule system here builds on two upstream projects. What was taken from each:

**petergyang/no-ai-slop** (MIT, by Peter Yang)

Taken: the English slop pattern taxonomy and the editing principles, covering binary contrasts, colon reveals, fake-insight setups, fake-profound kickers and decorative formatting. The adapted catalogue is [`docs/no-ai-slop-reference.md`](docs/no-ai-slop-reference.md), which keeps the upstream URL, commit `000650b156983f5159695b441477f4e63b25dc85` and the full MIT notice.

**guillaumemeyer/watermarks-remover** (MIT)

Taken: the invisible-character set and the IVD protection logic in `code/strip_invisible.py`, ported from Layer A (`service/scripts/text_unicode.py`).

What this repository adds on top: the Chinese word-list rules, the structural and character gates, and `code/selfcheck.py`, which pins the fixtures down as assertions.

**License**: this repository is released under [MIT](LICENSE). Keep the upstream notices when you redistribute it. The full upstream MIT text sits in `docs/no-ai-slop-reference.md`, and the character-set source is credited in the header of `code/strip_invisible.py`.
