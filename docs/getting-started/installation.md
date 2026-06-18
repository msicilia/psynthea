# Installation

psynthea is pure Python with **no required runtime dependencies** and supports
Python 3.11+.

```bash
pip install psynthea          # or: uv pip install psynthea
```

This installs the library and the `psynthea` command-line tool.

## Optional extras

```bash
pip install "psynthea[dev]"    # pytest, ruff, mypy — for contributing
pip install "psynthea[docs]"   # mkdocs-material — to build these docs locally
```

## Verify the install

```bash
psynthea generate -p 5 -m otitis_media -o out/ --seed 1
```

This generates a 5-patient cohort from a bundled example module and writes flat CSV
tables to `out/`. If you see `Generated 5 patient(s)…`, you're ready.

## Building the docs locally

```bash
pip install "psynthea[docs]"
mkdocs serve        # live-reload at http://127.0.0.1:8000
mkdocs build        # static site into site/
```
