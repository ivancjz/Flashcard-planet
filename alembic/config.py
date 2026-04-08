from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


class Config:
    """Lightweight subset of Alembic's Config API used by this project."""

    def __init__(self, filename: str):
        self.config_file_name = str(filename)
        self.config_ini_section = "alembic"
        self._filename = Path(filename)
        self._parser = ConfigParser()
        self._parser.read(self._filename, encoding="utf-8")

    def get_main_option(self, name: str, default: str | None = None) -> str | None:
        return self._parser.get(self.config_ini_section, name, fallback=default)

    def get_section(
        self, name: str, default: dict[str, str] | None = None
    ) -> dict[str, str]:
        if self._parser.has_section(name):
            return dict(self._parser.items(name))
        return {} if default is None else dict(default)
