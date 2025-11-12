"""Workflow configuration dataclasses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class WorkflowSettings:
    """工作流运行参数。"""

    dataset_path: Optional[str] = None
    max_tasks: int = 1
    output_dir: str = "./outputs"
    result_filename: str = "answer.md"
    max_web_results: int = 3
    llm_model_name: str = "default_llm"
    llm_token_limits: dict[str, int] = field(default_factory=dict)

    def to_shared_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.dataset_path:
            data["dataset_path"] = str(Path(self.dataset_path).expanduser())
        data["output_dir"] = str(Path(self.output_dir).expanduser())
        return data

    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser() / self.result_filename

