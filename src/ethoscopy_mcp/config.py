"""Local, fail-closed configuration for trusted experiment paths."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable

from ethoscopy_mcp.errors import ConfigurationError, UnsafePathError, UnsupportedSourceError


DATA_ROOTS_ENV = "ETHOSCOPY_DATA_ROOTS"
ARTIFACT_ROOT_ENV = "ETHOSCOPY_ARTIFACT_ROOT"


@dataclass(frozen=True, slots=True)
class Settings:
    """Filesystem boundaries used by the local service.

    Roots are resolved when settings are created. Source requests are resolved
    again with ``strict=True`` so symlinks cannot escape an allowed root.
    """

    trusted_roots: tuple[Path, ...]
    artifact_root: Path | None = None
    allowed_suffixes: tuple[str, ...] = (".pkl", ".pickle")

    @classmethod
    def create(
        cls,
        trusted_roots: Iterable[str | Path],
        artifact_root: str | Path | None = None,
        allowed_suffixes: Iterable[str] = (".pkl", ".pickle"),
    ) -> "Settings":
        roots: list[Path] = []
        for raw_root in trusted_roots:
            root = Path(raw_root).expanduser().resolve(strict=True)
            if not root.is_dir():
                raise ConfigurationError(f"Trusted root is not a directory: {root}")
            roots.append(root)

        if not roots:
            raise ConfigurationError("At least one trusted data root is required")

        resolved_artifact_root = None
        if artifact_root is not None:
            resolved_artifact_root = Path(artifact_root).expanduser().resolve(strict=True)
            if not resolved_artifact_root.is_dir():
                raise ConfigurationError(
                    f"Artifact root is not a directory: {resolved_artifact_root}"
                )

        suffixes = tuple(
            suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
            for suffix in allowed_suffixes
        )
        return cls(tuple(dict.fromkeys(roots)), resolved_artifact_root, suffixes)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_roots = os.environ.get(DATA_ROOTS_ENV, "")
        roots = [value for value in raw_roots.split(os.pathsep) if value]
        if not roots:
            raise ConfigurationError(
                f"{DATA_ROOTS_ENV} must contain at least one trusted directory"
            )
        return cls.create(roots, os.environ.get(ARTIFACT_ROOT_ENV) or None)

    def resolve_source(self, requested_path: str | Path) -> Path:
        """Resolve and validate one existing source file."""

        try:
            resolved = Path(requested_path).expanduser().resolve(strict=True)
        except FileNotFoundError as exc:
            raise UnsafePathError(f"Source does not exist: {requested_path}") from exc

        if not resolved.is_file():
            raise UnsafePathError(f"Source is not a file: {resolved}")

        if not any(_is_relative_to(resolved, root) for root in self.trusted_roots):
            raise UnsafePathError("Source is outside the configured trusted roots")

        if resolved.suffix.lower() not in self.allowed_suffixes:
            raise UnsupportedSourceError(
                f"Unsupported source suffix {resolved.suffix!r}; "
                f"allowed suffixes: {', '.join(self.allowed_suffixes)}"
            )

        return resolved

    def resolve_auxiliary(
        self,
        requested_path: str | Path,
        allowed_suffixes: Iterable[str] = (".csv",),
    ) -> Path:
        """Resolve a non-executable overlay or configuration file."""

        try:
            resolved = Path(requested_path).expanduser().resolve(strict=True)
        except FileNotFoundError as exc:
            raise UnsafePathError(f"Auxiliary file does not exist: {requested_path}") from exc

        if not resolved.is_file():
            raise UnsafePathError(f"Auxiliary path is not a file: {resolved}")
        if not any(_is_relative_to(resolved, root) for root in self.trusted_roots):
            raise UnsafePathError("Auxiliary file is outside the configured trusted roots")

        normalized = {
            suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
            for suffix in allowed_suffixes
        }
        if resolved.suffix.lower() not in normalized:
            raise UnsupportedSourceError(
                f"Unsupported auxiliary suffix {resolved.suffix!r}; "
                f"allowed suffixes: {', '.join(sorted(normalized))}"
            )
        return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
