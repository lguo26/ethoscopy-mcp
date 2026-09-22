"""Verified, non-overwriting exports beside the first source pickle."""

from pathlib import Path
import shutil
import tempfile

from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.registry import sha256_file
from ethoscopy_mcp.schemas import AnalysisRunResult


def export_analysis(source: Path, result: AnalysisRunResult) -> Path:
    """Copy completed artifacts atomically; never replace existing user files."""
    # The service supplies a freshly validated, resolved source path.
    destination = source.parent / f"{result.analysis_id}_exports"
    if destination.is_symlink():
        raise InvalidExperimentError(f"Export directory cannot be a symlink: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise InvalidExperimentError(f"Export destination is not a directory: {destination}")
        for artifact in result.artifacts:
            target = destination / artifact.path.name
            if (target.is_symlink() or not target.is_file()
                    or sha256_file(target) != artifact.sha256):
                raise InvalidExperimentError(
                    f"Existing export is missing or changed; no files overwritten: {target}"
                )
        return destination

    temporary = Path(tempfile.mkdtemp(prefix=".ethoscopy-export-", dir=source.parent))
    try:
        for artifact in result.artifacts:
            target = temporary / artifact.path.name
            shutil.copy2(artifact.path, target)
            if sha256_file(target) != artifact.sha256:
                raise InvalidExperimentError(f"Export hash verification failed: {target.name}")
        # Recheck before publication to avoid replacing an existing folder.
        if destination.exists() or destination.is_symlink():
            raise InvalidExperimentError(f"Export destination already exists: {destination}")
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination
