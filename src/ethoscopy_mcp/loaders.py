"""Trusted local loaders. Pickle support is intentionally fail-closed."""

from __future__ import annotations

import pandas as pd

from ethoscopy_mcp.errors import UnsupportedSourceError
from ethoscopy_mcp.schemas import SourceFile


def load_behaviour_pickle(source: SourceFile) -> pd.DataFrame:
    """Load a registered pickle and validate the minimum Ethoscopy shape.

    Registration and trusted-root validation must happen before this function is
    called. Reading an arbitrary pickle is unsafe because unpickling can execute
    code.
    """

    loaded = pd.read_pickle(source.path)
    if not isinstance(loaded, pd.DataFrame):
        raise UnsupportedSourceError(
            f"Pickle {source.source_id} did not contain a pandas DataFrame"
        )

    metadata = getattr(loaded, "meta", None)
    if not isinstance(metadata, pd.DataFrame):
        raise UnsupportedSourceError(
            f"Pickle {source.source_id} has no pandas DataFrame in .meta"
        )

    return loaded


def working_copy(data: pd.DataFrame) -> pd.DataFrame:
    """Create a deliberate data and metadata copy for future mutations."""

    copied = data.copy(deep=True)
    copied.meta = data.meta.copy(deep=True)
    return copied
