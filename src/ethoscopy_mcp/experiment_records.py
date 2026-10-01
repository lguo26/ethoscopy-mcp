"""Private experiment records and verified run links, separate from source files."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Literal

from pydantic import Field, model_validator

from ethoscopy_mcp.schemas import StrictModel, AnalysisRunResult, ReviewedExclusionDecision
from ethoscopy_mcp.errors import InvalidExperimentError


class ConditionRecord(StrictModel):
    condition_id: str = Field(min_length=1)
    treatment: str = Field(min_length=1)
    method: str = "Ethoscope"
    food: str | None = None
    temperature_c: float | None = Field(default=None, allow_inf_nan=False)
    sex: str | None = None
    od600: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    is_control: bool = False
    oa_route: str | None = None
    planned_n: int | None = Field(default=None, ge=0)


class ExperimentRecord(StrictModel):
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1)
    experiment_date: date | None = None
    folder: Path
    source_paths: tuple[Path, ...] = ()
    question: str = ""
    next_action: str = ""
    notes: str = ""
    recording_status: Literal["unknown", "planned", "recording", "finished"] = "unknown"
    review_status: Literal["needs_review", "confirmed", "reviewed"] = "needs_review"
    conditions: tuple[ConditionRecord, ...] = ()

    @model_validator(mode="after")
    def unique_conditions(self):
        ids = [c.condition_id for c in self.conditions]
        if len(ids) != len(set(ids)):
            raise ValueError("Condition IDs must be unique within an experiment")
        return self


class RegisteredExperiment(StrictModel):
    record: ExperimentRecord
    revision: int
    updated_at: datetime
    analyses: tuple[AnalysisRunResult, ...] = ()
    exclusion_decisions: tuple[ReviewedExclusionDecision, ...] = ()


class ExperimentRecords(StrictModel):
    schema_version: Literal["1"] = "1"
    experiments: tuple[RegisteredExperiment, ...]


class DashboardResult(StrictModel):
    path: Path
    experiments: int
    conditions: int
    built_at: datetime


class ExperimentStore:
    def __init__(self, settings):
        self.settings = settings

    def directory(self):
        if self.settings.artifact_root is None:
            raise InvalidExperimentError("An artifact root is required for experiment records")
        root = self.settings.artifact_root / "experiment_registry"
        if root.is_symlink():
            raise InvalidExperimentError("Registry directory must not be a symlink")
        root.mkdir(exist_ok=True)
        return root

    @contextmanager
    def locked(self):
        root = self.directory()
        # Reject final-component symlinks for both locking and persisted records.
        fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = root / "records.json"
            if path.is_symlink():
                raise InvalidExperimentError("Registry file must not be a symlink")
            data = ExperimentRecords.model_validate_json(path.read_text()) if path.exists() else ExperimentRecords(experiments=())
            yield path, list(data.experiments)

    @staticmethod
    def write(path, entries):
        content = ExperimentRecords(experiments=tuple(entries)).model_dump_json(indent=2)
        atomic_write(path, content)

    def list(self):
        if self.settings.artifact_root is None:
            return ExperimentRecords(experiments=())
        root = self.settings.artifact_root / "experiment_registry"
        path = root / "records.json"
        if root.is_symlink() or path.is_symlink():
            raise InvalidExperimentError("Registry must not be a symlink")
        return ExperimentRecords.model_validate_json(path.read_text()) if path.exists() else ExperimentRecords(experiments=())

    def register(self, record, expected_revision):
        folder = record.folder.resolve(strict=True)
        if not folder.is_dir() or not any(folder.is_relative_to(r) for r in self.settings.trusted_roots):
            raise InvalidExperimentError("Experiment folder must be inside a trusted root")
        sources = tuple(self.settings.resolve_source(p) for p in record.source_paths)
        if any(not p.is_relative_to(folder) for p in sources) or len(sources) != len(set(sources)):
            raise InvalidExperimentError("Unique experiment sources must be inside its folder")
        record = record.model_copy(update={"folder": folder, "source_paths": sources})
        with self.locked() as (path, entries):
            previous = next((e for e in entries if e.record.experiment_id == record.experiment_id), None)
            revision = previous.revision if previous else 0
            if expected_revision != revision:
                raise InvalidExperimentError(f"Revision conflict: current revision is {revision}")
            if previous and (previous.analyses or previous.exclusion_decisions) and set(previous.record.source_paths) != set(sources):
                raise InvalidExperimentError("Cannot change registered sources with linked analyses or decisions; use a new experiment ID")
            entry = RegisteredExperiment(record=record, revision=revision+1,
                updated_at=datetime.now(timezone.utc), analyses=previous.analyses if previous else (),
                exclusion_decisions=previous.exclusion_decisions if previous else ())
            entries = [e for e in entries if e.record.experiment_id != record.experiment_id] + [entry]
            self.write(path, entries)
            return entry

    def record_exclusion(self, experiment_id, request, expected_revision, sources):
        """Append a decision version without rewriting earlier decisions or runs."""
        with self.locked() as (path, entries):
            for i, entry in enumerate(entries):
                if entry.record.experiment_id != experiment_id:
                    continue
                if entry.revision != expected_revision:
                    raise InvalidExperimentError(f"Revision conflict: current revision is {entry.revision}")
                if set(entry.record.source_paths) != {s.path for s in sources}:
                    raise InvalidExperimentError("Decision sources no longer match registration")
                previous = [d for d in entry.exclusion_decisions if d.decision_id == request.decision_id]
                if request.status == "retired" and not previous:
                    raise InvalidExperimentError("Cannot retire a decision that does not exist")
                decision = ReviewedExclusionDecision(**request.model_dump(), experiment_id=experiment_id,
                    revision=max((d.revision for d in previous), default=0)+1,
                    recorded_at=datetime.now(timezone.utc), sources=sources)
                updated = entry.model_copy(update={"exclusion_decisions": (*entry.exclusion_decisions, decision),
                    "revision": entry.revision+1, "updated_at": datetime.now(timezone.utc)})
                entries[i] = updated
                self.write(path, entries)
                return updated
            raise InvalidExperimentError("Register the experiment before recording decisions")

    def attach(self, result, source_paths):
        with self.locked() as (path, entries):
            for i, entry in enumerate(entries):
                if entry.record.experiment_id != result.experiment_id:
                    continue
                if set(entry.record.source_paths) != {Path(p).resolve(strict=True) for p in source_paths}:
                    raise InvalidExperimentError("Run sources do not match the registered experiment")
                # One current run per recipe, never sum overlapping analyses as animals.
                others = [r for r in entry.analyses if r.recipe_id != result.recipe_id]
                canonical = result.model_copy(update={"reused_existing": False, "dashboard_path": None, "dashboard_warning": None})
                old = next((r for r in entry.analyses if r.recipe_id == result.recipe_id), None)
                if old is None or old.analysis_id != canonical.analysis_id:
                    entry = entry.model_copy(update={"analyses": tuple(others + [canonical]),
                        "revision": entry.revision+1, "updated_at": datetime.now(timezone.utc)})
                    entries[i] = entry
                    self.write(path, entries)
                return entry
            return None


def atomic_write(path, text):
    if path.is_symlink():
        raise InvalidExperimentError("Output must not be a symlink")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".registry-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
