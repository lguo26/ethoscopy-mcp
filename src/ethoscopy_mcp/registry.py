"""Content-addressed registration for immutable local source files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.errors import SourceChangedError
from ethoscopy_mcp.schemas import SourceFile


PICKLE_MEDIA_TYPE = "application/vnd.python.pickle"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class SourceRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings

    def register(self, requested_path: str | Path) -> SourceFile:
        path = self.settings.resolve_source(requested_path)
        stat = path.stat()
        digest = sha256_file(path)
        return SourceFile(
            source_id=f"sha256-{digest[:16]}",
            path=path,
            media_type=PICKLE_MEDIA_TYPE,
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            sha256=digest,
        )

    def register_auxiliary(self, requested_path: str | Path) -> SourceFile:
        path = self.settings.resolve_auxiliary(requested_path)
        stat = path.stat()
        digest = sha256_file(path)
        return SourceFile(
            source_id=f"sha256-{digest[:16]}",
            path=path,
            media_type="text/csv",
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            sha256=digest,
        )

    def assert_auxiliary_unchanged(self, source: SourceFile) -> None:
        path = self.settings.resolve_auxiliary(source.path)
        stat = path.stat()
        if stat.st_size != source.size_bytes or sha256_file(path) != source.sha256:
            raise SourceChangedError(
                f"Auxiliary file changed after registration: {source.source_id}"
            )

    def assert_unchanged(self, source: SourceFile) -> None:
        path = self.settings.resolve_source(source.path)
        stat = path.stat()
        if stat.st_size != source.size_bytes or sha256_file(path) != source.sha256:
            raise SourceChangedError(
                f"Source changed after registration: {source.source_id}"
            )
