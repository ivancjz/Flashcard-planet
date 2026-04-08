from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from .config import Config


def _versions_dir(cfg: Config) -> Path:
    config_path = Path(cfg.config_file_name).resolve()
    script_location = cfg.get_main_option("script_location", "alembic") or "alembic"
    return config_path.parent / script_location / "versions"


def _load_revision_modules(cfg: Config):
    modules = []
    for path in sorted(_versions_dir(cfg).glob("*.py")):
        if path.name.startswith("__"):
            continue
        spec = spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            continue
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def _normalize_down_revisions(down_revision) -> tuple[str, ...]:
    if down_revision is None:
        return ()
    if isinstance(down_revision, str):
        return (down_revision,)
    return tuple(str(revision) for revision in down_revision)


def _format_history_line(module, head_revisions: set[str]) -> str:
    revision = getattr(module, "revision", "<unknown>")
    down_revision = getattr(module, "down_revision", None)
    label = getattr(module, "__doc__", "") or ""
    title = label.strip().splitlines()[0] if label.strip() else path_title(module.__name__)
    start = "<base>" if down_revision is None else str(down_revision)
    suffix = " (head)" if revision in head_revisions else ""
    return f"{start} -> {revision}{suffix}, {title}"


def path_title(module_name: str) -> str:
    return module_name.replace("_", " ").strip() or "revision"


def history(cfg: Config) -> list[str]:
    modules = _load_revision_modules(cfg)
    referenced_revisions = {
        referenced_revision
        for module in modules
        for referenced_revision in _normalize_down_revisions(getattr(module, "down_revision", None))
    }
    head_revisions = {
        getattr(module, "revision", "<unknown>")
        for module in modules
        if getattr(module, "revision", "<unknown>") not in referenced_revisions
    }
    return [_format_history_line(module, head_revisions) for module in modules]


def stamp(_cfg: Config, _revision: str) -> None:
    return None


def upgrade(_cfg: Config, _revision: str) -> None:
    return None
