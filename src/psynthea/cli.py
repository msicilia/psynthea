"""Command-line interface: ``psynthea generate ...``."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from psynthea.compat import load_module_file, save_module_file
from psynthea.demographics import DemographicProfile
from psynthea.engine import Generator, GeneratorConfig
from psynthea.export import export_csv, export_ground_truth, export_omop
from psynthea.ir.module import Module


def _load_profile(path: str) -> DemographicProfile:
    """Load a demographic profile from JSON: ``{"bands": [[min,max,w_male,w_female],...]}``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return DemographicProfile.from_bands([tuple(b) for b in data["bands"]])

# bundled example modules, shipped inside the package (works once installed)
_DEFAULT_MODULES_DIR = Path(__file__).resolve().parent / "data" / "modules"


def _resolve_modules(names: list[str], files: list[str], modules_dir: Path) -> list[Module]:
    modules: list[Module] = []
    for name in names:
        modules.append(load_module_file(modules_dir / f"{name}.json"))
    for f in files:
        modules.append(load_module_file(f))
    return modules


def _cmd_generate(args: argparse.Namespace) -> int:
    modules = _resolve_modules(args.module, args.module_file, Path(args.modules_dir))
    if not modules:
        print("error: specify at least one module with -m/--module or --module-file", file=sys.stderr)
        return 2

    end_date = (
        datetime.fromisoformat(args.end_date)
        if args.end_date
        else datetime.combine(datetime.now().date(), datetime.min.time())
    )
    config = GeneratorConfig(
        population=args.population,
        seed=args.seed,
        step_days=args.step_days,
        end_date=end_date,
        min_age=args.min_age,
        max_age=args.max_age,
        profile=_load_profile(args.profile_file) if args.profile_file else None,
    )
    people = Generator(modules, config).run()
    exporter = export_omop if args.format == "omop" else export_csv
    counts = exporter(people, args.output)
    if args.ground_truth:
        counts.update(export_ground_truth(people, args.output))

    print(f"Generated {len(people)} patient(s) using modules: {', '.join(m.name for m in modules)}")
    print(f"Format: {args.format}{' + ground-truth' if args.ground_truth else ''}")
    print(f"Output written to {Path(args.output).resolve()}")
    for filename, n in counts.items():
        print(f"  {filename}: {n} row(s)")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    modules = _resolve_modules(args.module, args.module_file, Path(args.modules_dir))
    if len(modules) != 1:
        print("error: export takes exactly one module (-m/--module or --module-file)",
              file=sys.stderr)
        return 2
    out = save_module_file(modules[0], args.output)
    print(f"Exported module {modules[0].name!r} to {out.resolve()} (Synthea GMF JSON)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psynthea", description="Synthetic patient generator")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate a synthetic cohort")
    gen.add_argument("-p", "--population", type=int, default=1, help="number of patients")
    gen.add_argument("-s", "--seed", type=int, default=0, help="random seed (reproducible)")
    gen.add_argument("-m", "--module", action="append", default=[],
                     help="module name within --modules-dir (repeatable)")
    gen.add_argument("--module-file", action="append", default=[],
                     help="path to a GMF JSON module file (repeatable)")
    gen.add_argument("-d", "--modules-dir", default=str(_DEFAULT_MODULES_DIR),
                     help="directory holding <name>.json modules")
    gen.add_argument("-o", "--output", default="out", help="output directory")
    gen.add_argument("--format", choices=["csv", "omop"], default="csv",
                     help="output format: flat CSV or OMOP CDM v5.4 (source-loaded)")
    gen.add_argument("--ground-truth", action="store_true",
                     help="also emit ground-truth labels (provenance, trajectories, phenotypes)")
    gen.add_argument("--step-days", type=float, default=7.0, help="simulation time step in days")
    gen.add_argument("--min-age", type=float, default=0.0)
    gen.add_argument("--max-age", type=float, default=100.0)
    gen.add_argument("--profile-file", default=None,
                     help="JSON demographic profile {\"bands\":[[min,max,w_male,w_female],...]} "
                          "to match a target age/sex structure (overrides --min/max-age)")
    gen.add_argument("--end-date", default=None, help="simulation end date (YYYY-MM-DD)")
    gen.set_defaults(func=_cmd_generate)

    exp = sub.add_parser("export", help="export a module to Synthea GMF JSON")
    exp.add_argument("-m", "--module", action="append", default=[],
                     help="module name within --modules-dir")
    exp.add_argument("--module-file", action="append", default=[],
                     help="path to a GMF JSON module file (re-export through the IR)")
    exp.add_argument("-d", "--modules-dir", default=str(_DEFAULT_MODULES_DIR),
                     help="directory holding <name>.json modules")
    exp.add_argument("-o", "--output", required=True, help="output .json file path")
    exp.set_defaults(func=_cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
