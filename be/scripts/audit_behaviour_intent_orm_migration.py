"""
Static comparison: BehaviourIntent ORM mapped columns vs add/drop ops on behaviour_intents
in Alembic revisions. Run from repo `be/`:

  python -m scripts.audit_behaviour_intent_orm_migration

Exits 0 always; prints a human-readable delta to stdout.

This satisfies the audit plan checklist without requiring a live database.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict, deque
from pathlib import Path


def _orm_column_names() -> set[str]:
    from app.db.models.behaviour_intent import BehaviourIntent

    return {c.key for c in BehaviourIntent.__table__.columns}


def _parse_revision_id(text: str) -> str | None:
    m = re.search(r"^revision\s*:\s*\S+\s*=\s*['\"](\w+)['\"]", text, re.MULTILINE)
    return m.group(1) if m else None


def _parse_down_revision(text: str) -> str | None:
    if re.search(r"down_revision\s*:\s*[^=\n]+\=\s*None\b", text):
        return None
    m = re.search(r"down_revision\s*:\s*[^=\n]+\=\s*['\"](\w+)['\"]", text)
    return m.group(1) if m else None


def _topology_ordered_paths(mig_dir: Path) -> list[Path]:
    paths = sorted(p for p in mig_dir.glob("*.py") if not p.name.startswith("_"))
    by_rev: dict[str, tuple[str | None, Path]] = {}
    for path in paths:
        txt = path.read_text(encoding="utf-8")
        rev = _parse_revision_id(txt)
        if not rev:
            continue
        down = _parse_down_revision(txt)
        by_rev[rev] = (down, path)

    all_revs = set(by_rev)
    adj: dict[str, list[str]] = defaultdict(list)
    indeg = {r: 0 for r in all_revs}
    for rev, (down, _) in by_rev.items():
        if down and down in all_revs:
            adj[down].append(rev)
            indeg[rev] += 1

    q = deque(sorted(r for r in all_revs if indeg[r] == 0))
    ordered: list[Path] = []
    while q:
        cur = q.popleft()
        ordered.append(by_rev[cur][1])
        for nei in sorted(adj[cur]):
            indeg[nei] -= 1
            if indeg[nei] == 0:
                q.append(nei)
    ordered_set = set(ordered)
    ordered.extend(sorted((p for p in paths if p not in ordered_set), key=lambda x: x.name))
    return ordered


def _upgrade_section(text: str) -> str:
    start = text.find("def upgrade()")
    if start < 0:
        return text
    end = text.find("def downgrade()", start)
    if end < 0:
        return text[start:]
    return text[start:end]


def _bootstrap_columns_behaviour_intents(upgrade_txt: str) -> list[str]:
    """Initial create_table columns from the first migration (if present)."""
    for marker in ("op.create_table('behaviour_intents'", 'op.create_table("behaviour_intents"'):
        pos = upgrade_txt.find(marker)
        if pos < 0:
            continue
        fk = upgrade_txt.find("sa.ForeignKeyConstraint", pos)
        chunk = upgrade_txt[pos:fk] if fk > pos else upgrade_txt[pos : pos + 4000]
        return re.findall(r"sa\.Column\(\s*['\"](\w+)['\"]", chunk)
    return []


def _collect_behaviour_intents_ops(upgrade_txt: str) -> tuple[list[str], list[str]]:
    """Returns (columns_added_by_name, columns_dropped_by_name) in upgrade()."""
    adds: list[str] = []
    drops: list[str] = []

    # op.add_column("behaviour_intents", sa.Column("foo", ...
    add_re = re.compile(
        r"add_column\s*\(\s*[\'\"]behaviour_intents[\'\"]\s*,\s*sa\.Column\s*\(\s*[\'\"](\w+)[\'\"]",
        re.MULTILINE,
    )
    adds.extend(add_re.findall(upgrade_txt))

    # op.drop_column("behaviour_intents", "foo" — allow optional schema kw
    drop_re = re.compile(
        r"drop_column\s*\(\s*[\'\"]behaviour_intents[\'\"]\s*,\s*[\'\"](\w+)[\'\"]",
        re.MULTILINE,
    )
    drops.extend(drop_re.findall(upgrade_txt))

    return adds, drops


def main() -> None:
    be_root = Path(__file__).resolve().parents[1]
    mig_dir = be_root / "app" / "db" / "migrations" / "versions"

    sys.path.insert(0, str(be_root))
    sys.path.insert(0, str(be_root.parent))  # project root fallback

    try:
        orm_cols = sorted(_orm_column_names())
    except Exception as exc:  # pragma: no cover - import failure
        print(f"ERROR: Could not load ORM BehaviourIntent ({exc})", file=sys.stderr)
        sys.exit(1)

    cumulative: set[str] = set()
    ordered_events: list[tuple[str, str, str]] = []

    if not mig_dir.is_dir():
        print(f"Migrations dir not found: {mig_dir}")
        return

    ordered_paths = _topology_ordered_paths(mig_dir)
    for path in ordered_paths:
        full_text = path.read_text(encoding="utf-8")
        rev_label = _parse_revision_id(full_text) or path.stem.split("_")[0]
        upgrade_txt = _upgrade_section(full_text)

        adds, drops = _collect_behaviour_intents_ops(upgrade_txt)

        bootstrap = _bootstrap_columns_behaviour_intents(upgrade_txt)
        if bootstrap:
            for c in bootstrap:
                cumulative.add(c)
                ordered_events.append((rev_label, "init", c))
        for c in adds:
            cumulative.add(c)
            ordered_events.append((rev_label, "add", c))
        for c in drops:
            if c in cumulative:
                cumulative.discard(c)
            ordered_events.append((rev_label, "drop", c))

    mig_cols_sorted = sorted(cumulative)
    orm_set = set(orm_cols)
    mig_set = set(mig_cols_sorted)

    only_in_orm = sorted(orm_set - mig_set)
    only_in_migrations = sorted(mig_set - orm_set)

    print("=== behaviour_intents: ORM ↔ migration (static chain) audit ===")
    print(f"ORM BehaviourIntent columns ({len(orm_cols)}): {', '.join(orm_cols)}")
    print(f"Net migrations columns ({len(mig_cols_sorted)}): {', '.join(mig_cols_sorted)}")
    if only_in_orm:
        print("\n[COLUMNS ONLY ON ORM — may need migration]: " + ", ".join(only_in_orm))
    if only_in_migrations:
        print("\n[COLUMNS ONLY IN NET MIGRATIONS — ghost / unmapped in ORM]: " + ", ".join(only_in_migrations))
    if not only_in_orm and not only_in_migrations:
        print("\n(Net migration column names match ORM column names.)")

    if ordered_events:
        print("\n--- Migration events (topological revision order): ---")
        for rev, kind, col in ordered_events:
            print(f"  {rev}  {kind:4}  {col}")


if __name__ == "__main__":
    main()
