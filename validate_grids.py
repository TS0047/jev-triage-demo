#!/usr/bin/env python3
"""Validate the diagnostic grids mechanically. Correctness is checked, not eyeballed.

Checks, per grid:
  1. every cell's syndrome exists in SYNDROMES
  2. every cell's mechanism exists in SIEVE
  3. no cell exceeds the API's 255-choice cap (with the escape option)
  4. every cell is non-empty
  5. every condition has a non-empty label
  6. incubation tuples are well formed and ordered
  7. DDXPLUS covers ALL 49 official pathologies, exact string match
  8. DDXPLUS introduces no condition that is not an official pathology

Exits non-zero on any failure, so it can gate a commit.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from grids import GRIDS, SYNDROMES, SIEVE

MAX_CHOICES = 255
errors, warnings = [], []


def check_structure(name, grid):
    for (syn, mech), cell in grid.items():
        where = f"{name}[{syn}, {mech}]"
        if syn not in SYNDROMES:
            errors.append(f"{where}: syndrome '{syn}' not in SYNDROMES")
        if mech not in SIEVE:
            errors.append(f"{where}: mechanism '{mech}' not in SIEVE")
        if not cell:
            errors.append(f"{where}: cell is empty")
        if len(cell) + 1 > MAX_CHOICES:
            errors.append(f"{where}: {len(cell)+1} choices exceeds {MAX_CHOICES}")
        for key, meta in cell.items():
            if not isinstance(meta, dict):
                errors.append(f"{where}.{key}: entry is not a dict")
                continue
            label = meta.get("label", "")
            if not label or not label.strip():
                errors.append(f"{where}.{key}: empty label")
            inc = meta.get("incubation")
            if inc is not None:
                if (not isinstance(inc, (tuple, list)) or len(inc) != 2
                        or not all(isinstance(x, (int, float)) for x in inc)):
                    errors.append(f"{where}.{key}: malformed incubation {inc!r}")
                elif inc[0] > inc[1]:
                    errors.append(f"{where}.{key}: incubation min>max {inc!r}")


def check_ddxplus_coverage():
    cond_file = HERE / "datasets" / "release_conditions.json"
    if not cond_file.exists():
        warnings.append("datasets/release_conditions.json missing - "
                        "run eval_ddxplus.py once to fetch it; coverage NOT checked")
        return None
    official = set(json.loads(cond_file.read_text()).keys())
    covered = set()
    for (syn, mech), cell in GRIDS["ddxplus"].items():
        covered |= set(cell.keys())

    missing = official - covered
    extra = covered - official
    for m in sorted(missing):
        errors.append(f"ddxplus: pathology NOT reachable in any cell: {m!r}")
    for e in sorted(extra):
        errors.append(f"ddxplus: condition {e!r} is not an official DDXPlus pathology")
    return official, covered


def report():
    print("=" * 66)
    for name, grid in GRIDS.items():
        cells = len(grid)
        conds = {k for c in grid.values() for k in c}
        slots = sum(len(c) for c in grid.values())
        biggest = max(((len(c), f"{s}/{m}") for (s, m), c in grid.items()),
                      default=(0, "-"))
        print(f"{name:10s} {cells:3d} cells  {len(conds):3d} unique conditions  "
              f"{slots:3d} placements  largest cell {biggest[0]} ({biggest[1]})")
    print("=" * 66)

    cov = check_ddxplus_coverage()
    if cov:
        official, covered = cov
        print(f"\nDDXPlus coverage: {len(covered & official)}/{len(official)} "
              f"official pathologies reachable")

        # reachability detail: how many cells can each pathology be found in
        counts = {}
        for (s, m), cell in GRIDS["ddxplus"].items():
            for k in cell:
                counts[k] = counts.get(k, 0) + 1
        multi = {k: v for k, v in counts.items() if v > 1}
        print(f"  {len(multi)} pathologies appear in more than one cell "
              f"(intentional - differentials overlap)")
        singles = sorted(k for k, v in counts.items() if v == 1)
        print(f"  {len(singles)} appear in exactly one cell")

        # which syndromes are reachable
        syns = sorted({s for (s, m) in GRIDS["ddxplus"]})
        print(f"  syndromes used: {len(syns)} -> {', '.join(syns)}")

        # FRAGILITY: a pathology reachable from only one syndrome is lost
        # entirely if L2 routes elsewhere. This is the failure mode that
        # produced 'no_condition_in_cell_fits' escalations on real data.
        reach = {}
        for (s, m), cell in GRIDS["ddxplus"].items():
            for k in cell:
                reach.setdefault(k, set()).add(s)
        fragile = sorted(k for k, v in reach.items() if len(v) == 1)
        print(f"  {len(fragile)} reachable from only ONE syndrome "
              f"(fragile: a single L2 misroute loses them)")
        for k in fragile:
            warnings.append(f"ddxplus: {k!r} reachable only via "
                            f"{list(reach[k])[0]!r} - one L2 misroute escalates it")

    for w in warnings:
        print(f"\nWARN  {w}")
    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  FAIL  {e}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    for name, grid in GRIDS.items():
        check_structure(name, grid)
    sys.exit(report())
