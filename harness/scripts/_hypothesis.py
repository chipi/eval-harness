"""A hypothesis written into an arm's config before its run (ADR-0025).

    hypothesis:
      against: baseline_v1          # the config_id it is compared with
      measure: false_alarm          # one of the arm's metrics
      direction: better             # better | worse | no-worse
      statement: "the shorter prompt lowers false alarms"
      items: data/expected_flips.txt   # optional: item ids expected to flip

A paired test is valid uncorrected only when the pair was named before the results were read. The
config is where the change is, so the prediction sits beside it; a run records it, and whether the
commit that last changed it came before the run. It is never part of the fingerprint: a hypothesis
does not change what was measured.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

DIRECTIONS = ("better", "worse", "no-worse")
KEYS = ("against", "measure", "direction", "statement", "items")
REQUIRED = ("against", "measure", "direction", "statement")

#: What a run records about the naming: named is True, False or None (not determinable).
YES, NO, UNDETERMINED = "yes", "no", "not determinable"


def of(cfg: dict) -> dict | None:
    """The config's hypothesis block as written, or None when it has none."""
    return cfg.get("hypothesis") if isinstance(cfg, dict) else None


def config_ids() -> dict[str, Path]:
    """{config_id: file} for every arm config of the project (data/configs and validate.json's globs)."""
    import yaml  # noqa: PLC0415
    from evaluation_harness._common import arm_config_files as config_files  # noqa: PLC0415

    out: dict[str, Path] = {}
    for f in config_files():
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(doc, dict) and doc.get("config_id"):
            out.setdefault(str(doc["config_id"]), f)
    return out


def known_metrics(cfg: dict, config_path: Path | None) -> set[str]:
    """The metrics this arm has: what its adapter declares, what its goal decides on, and what runs of
    the config recorded. Empty when nothing says (the adapter declares none and the arm never ran)."""
    from evaluation_harness import _adapter, _common, _runs  # noqa: PLC0415

    spec = cfg.get("adapter")
    path = None
    if spec:
        p = Path(spec)
        for cand in (
            [p]
            if p.is_absolute()
            else [*([config_path.resolve().parent / p] if config_path else []), _common.ROOT / p]
        ):
            if cand.is_file():
                path = cand
                break
    elif (_common.ROOT / "adapter.py").is_file():
        path = _common.ROOT / "adapter.py"
    params = dict(cfg.get("params") or {})
    names: set[str] = set(_adapter.metric_kinds(path)) | set(_adapter.metric_directions(path))
    names |= set(_adapter.metric_descriptions(path))
    primary = _adapter.primary_metric(path, params)
    if primary:
        names.add(primary)
    goal = (_common.load_goals().get(cfg.get("goal") or "") or {}).get("success_criteria") or {}
    if (goal.get("primary") or {}).get("measure"):
        names.add(goal["primary"]["measure"])
    names |= {
        str(a["measure"])
        for a in (goal.get("axes") or {}).values()
        if isinstance(a, dict) and a.get("measure")
    }
    for _d, m in _runs.runs_on(config_id=cfg.get("config_id")):
        names |= set(m.get("scores") or {})
    names.discard(None)
    return names


def problems(cfg: dict, config_path: Path | None = None, ids: dict | None = None) -> list[str]:
    """What is wrong with the config's hypothesis block, each as one sentence; [] when it has none or it is
    sound. `ids`: config_ids(), when the caller checks many configs and read it once."""
    h = of(cfg)
    if h is None:
        return []
    if not isinstance(h, dict):
        return ["hypothesis: must be a mapping with against, measure, direction and statement"]
    out: list[str] = []
    for k in h:
        if k not in KEYS:
            out.append(f"hypothesis: unknown key {k!r} (one of {', '.join(KEYS)})")
    for k in REQUIRED:
        v = h.get(k)
        if not isinstance(v, str) or not v.strip():
            out.append(f"hypothesis.{k}: required, a non-empty string")
    if out:
        return out
    if h["direction"] not in DIRECTIONS:
        out.append(f"hypothesis.direction: {h['direction']!r} is not one of {', '.join(DIRECTIONS)}")
    ids = ids if ids is not None else config_ids()
    if h["against"] == cfg.get("config_id"):
        out.append("hypothesis.against: the arm cannot be compared with itself")
    elif h["against"] not in ids:
        out.append(f"hypothesis.against: no config with config_id {h['against']!r} (data/configs/*.yaml)")
    metrics = known_metrics(cfg, config_path)
    if metrics and h["measure"] not in metrics:
        out.append(
            f"hypothesis.measure: {h['measure']!r} is not one of this arm's metrics ({', '.join(sorted(metrics))})"
        )
    if h.get("items") is not None:
        if not isinstance(h["items"], str) or not h["items"].strip():
            out.append("hypothesis.items: a path to a file of item ids")
        else:
            from evaluation_harness import _common  # noqa: PLC0415

            p = Path(h["items"])
            cands = (
                [p]
                if p.is_absolute()
                else [*([config_path.resolve().parent / p] if config_path else []), _common.ROOT / p]
            )
            if not any(c.is_file() for c in cands):
                out.append(
                    f"hypothesis.items: no file {h['items']!r} (relative to the config, then the project)"
                )
    return out


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def named_before(config_path: Path, hyp: dict, build: dict, before: str) -> dict:
    """Whether the config's hypothesis was committed before the run: the commit that last changed it is an
    ancestor of the run's build commit and was made before `before` (the run's start). Returns {"named":
    True | False | None, "commit", "committed_at", "why"}; None outside git, for a build that is not a git
    commit, and for a dirty tree, where the config on disk may not be the committed one."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _common  # noqa: PLC0415
    from evaluation_harness._fingerprint import _git, tree_dirt  # noqa: PLC0415

    def out(named, why, commit=None, at=None):
        return {"named": named, "commit": commit, "committed_at": at, "why": why}

    path = Path(config_path).resolve()
    top = _git(path.parent, "rev-parse", "--show-toplevel")
    if not top:
        return out(None, "the config is not in a git repository")
    if build.get("source") != "git" or not build.get("ref"):
        return out(None, "the build is not a git commit")
    dirt = tree_dirt(Path(top), _common.DATA)
    if dirt is None:
        return out(None, "git cannot say whether the tree is clean")
    if dirt:
        return out(None, "the working tree is dirty")
    ref = build["ref"]
    if _git(Path(top), "rev-parse", "--verify", f"{ref}^{{commit}}") is None:
        return out(None, "the build commit is not in the config's repository")
    rel = path.relative_to(Path(top).resolve()).as_posix()
    # Walked from the build commit, so every commit seen is one of its ancestors.
    log = _git(Path(top), "log", ref, "--format=%H\t%cI", "--", rel)
    last = None
    for line in (log or "").splitlines():
        sha, when = line.split("\t")
        doc = yaml.safe_load(_git(Path(top), "show", f"{sha}:{rel}") or "") or {}
        if isinstance(doc, dict) and doc.get("hypothesis") == hyp:
            last = (sha, when)
        else:
            break
    if last is None:
        return out(False, "the hypothesis is in no commit before the run")
    sha, when = last
    # Strictly after: git dates and `before` both have one-second resolution, and the commit being an
    # ancestor of the build commit (the tree's HEAD at the start) already puts it first.
    if _when(when) > _when(before):
        return out(False, f"committed at {when}, not before the run ({before})", sha, when)
    return out(True, f"committed {sha[:8]} at {when}", sha, when)


def record_for(cfg: dict, config_path: Path, build: dict, before: str) -> dict:
    """The fields a run records about its config's hypothesis: {} when it has none, else
    {"hypothesis": the block, "hypothesis_in_advance": named_before(...)}."""
    h = of(cfg)
    if not h:
        return {}
    return {"hypothesis": h, "hypothesis_in_advance": named_before(config_path, h, build, before)}


def said(adv: dict | None) -> str:
    """'yes (committed 1a2b3c4d before the run)', 'no (…)' or 'not determinable (…)'."""
    adv = adv or {}
    named = adv.get("named")
    if named is True:
        return f"{YES} (committed {str(adv.get('commit') or '')[:8]} before the run)"
    if named is False:
        return f"{NO} ({adv.get('why') or 'not committed before the run'})"
    return f"{UNDETERMINED} ({adv.get('why') or 'no record'})"


def agreement(direction: str, delta: float, lower: bool, significant: bool) -> str:
    """Whether a paired test's result (delta = A - B, `significant` at the threshold shown) agrees with the stated
    direction: 'yes', 'no' or 'not shown'. better and worse need a significant move that way, and a significant
    move the other way contradicts them; no-worse holds unless A is significantly worse (no proof of equivalence)."""
    better = delta < 0 if lower else delta > 0
    worse = delta > 0 if lower else delta < 0
    if direction == "no-worse":
        return "no" if worse and significant else "yes"
    want, other = (better, worse) if direction == "better" else (worse, better)
    return "yes" if want and significant else "no" if other and significant else "not shown"
