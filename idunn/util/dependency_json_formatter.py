"""JSON formatter for dependency-analysis results."""

import json
from typing import Any


class JsonFormatter:
  """Renders a dependency-analysis result as a JSON string."""

  def __init__(self, pretty: bool = False) -> None:
    """Configure the formatter; ``pretty`` enables 2-space indentation."""
    self.pretty: bool = pretty

  def format(self, analysis_result: dict[str, Any]) -> str:
    """Render the analysis result as JSON (sets become sorted lists)."""
    indent: int | None = 2 if self.pretty else None
    return json.dumps(self._jsonable(analysis_result), indent=indent, sort_keys=True)

  @classmethod
  def _jsonable(cls, value: Any) -> Any:
    """Recursively coerce sets/tuples into JSON-serializable lists."""
    result: Any
    if isinstance(value, dict):
      result = {key: cls._jsonable(item) for key, item in value.items()}
    elif isinstance(value, (set, frozenset)):
      result = sorted(cls._jsonable(item) for item in value)
    elif isinstance(value, (list, tuple)):
      result = [cls._jsonable(item) for item in value]
    else:
      result = value
    return result
