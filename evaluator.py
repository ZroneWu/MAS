"""Dataset evaluation utility for running the OxyGent workflow on task sets."""

from __future__ import annotations

import argparse
import asyncio
import ast
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

try:
    from .builder import run_cli
    from .settings import WorkflowSettings
    from .utils import parse_llm_token_limits
except ImportError:  # pragma: no cover - fallback when executed as script
    PACKAGE_ROOT = Path(__file__).resolve().parent
    PROJECT_ROOT = PACKAGE_ROOT.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from workflow.builder import run_cli  # type: ignore  # noqa: E402
    from workflow.settings import WorkflowSettings  # type: ignore  # noqa: E402
    from workflow.utils import parse_llm_token_limits  # type: ignore  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Single evaluation task loaded from JSONL."""

    task_id: str
    query: str
    level: int
    file_names: list[str]
    raw: dict


def _parse_filenames(raw: str | list[str] | None) -> list[str]:
    if raw in ("", None):
        return []
    if isinstance(raw, list):
        return [str(name).strip() for name in raw if str(name).strip()]
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return [str(name).strip() for name in parsed if str(name).strip()]
            if isinstance(parsed, str):
                raw = parsed
        except (ValueError, SyntaxError):
            pass
        candidates = [segment.strip() for segment in raw.split(",") if segment.strip()]
        return candidates
    return []


def load_tasks(path: Path) -> list[Task]:
    tasks: list[Task] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            file_names = _parse_filenames(payload.get("file_name"))
            tasks.append(
                Task(
                    task_id=payload.get("task_id", ""),
                    query=payload.get("query", ""),
                    level=int(payload.get("level", 0) or 0),
                    file_names=file_names,
                    raw=payload,
                )
            )
    return tasks


def _candidate_attachment_paths(name: str, attachments_root: Path) -> Iterable[Path]:
    yield attachments_root / name
    if "," in name:
        yield attachments_root / name.replace(",", ".")
    if not name.lower().endswith((".mp4", ".mp3", ".pdf", ".png", ".jpg", ".jpeg")):
        for suffix in (".mp4", ".mp3", ".pdf", ".png", ".jpg", ".jpeg"):
            yield attachments_root / f"{name}{suffix}"


def resolve_attachments(
    filenames: list[str], attachments_root: Optional[Path]
) -> list[str]:
    if not filenames or attachments_root is None:
        return []
    resolved: list[str] = []
    for name in filenames:
        for candidate in _candidate_attachment_paths(name, attachments_root):
            if candidate.exists():
                resolved.append(str(candidate))
                break
        else:
            logger.warning("Attachment not found: %s", name)
    return resolved


async def evaluate_tasks(
    tasks: Iterable[Task],
    output_path: Path,
    attachments_root: Optional[Path],
    base_settings: WorkflowSettings,
    limit: Optional[int] = None,
    start_index: int = 0,
    skip_ids: Optional[set[str]] = None,
    dry_run: bool = False,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    record = json.loads(line)
                    task_id = record.get("task_id")
                    if task_id:
                        existing_ids.add(task_id)
                except json.JSONDecodeError:
                    continue

    if skip_ids is None:
        skip_ids = set()

    with output_path.open("a", encoding="utf-8") as sink:
        for idx, task in enumerate(tasks):
            if idx < start_index:
                continue
            if limit is not None and idx - start_index >= limit:
                break
            if task.task_id in existing_ids or task.task_id in skip_ids:
                logger.info("Skipping existing task %s", task.task_id)
                continue

            attachments = resolve_attachments(task.file_names, attachments_root)
            task_settings = WorkflowSettings(
                dataset_path=base_settings.dataset_path,
                max_tasks=base_settings.max_tasks,
                output_dir=base_settings.output_dir,
                result_filename=f"{task.task_id}.md",
                max_web_results=base_settings.max_web_results,
                llm_model_name=base_settings.llm_model_name,
            )

            logger.info(
                "Running task %s (level=%s, attachments=%d)",
                task.task_id,
                task.level,
                len(attachments),
            )
            record: dict[str, any] = {
                "task_id": task.task_id,
                "query": task.query,
                "level": task.level,
                "attachments": attachments,
            }
            if dry_run:
                record["status"] = "skipped"
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                continue

            try:
                response = await run_cli(
                    task_settings, query=task.query, attachments=attachments
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Task %s failed: %s", task.task_id, exc)
                record["status"] = "error"
                record["error"] = str(exc)
            else:
                record["status"] = "ok"
                record["result"] = response.get("result")
                record["trace_id"] = response.get("trace_id")
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            sink.flush()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-click evaluation driver for workflow tasks"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="JSONL dataset to evaluate",
    )
    parser.add_argument(
        "--attachments-dir",
        type=Path,
        default=None,
        help="Directory containing attachment files referenced by dataset",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write evaluation results JSONL",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("./outputs/artifacts"),
        help="Directory for agent generated artifacts",
    )
    parser.add_argument(
        "--llm-model",
        default="default_llm",
        help="LLM identifier registered in OxyGent Config",
    )
    parser.add_argument(
        "--llm-token-limit",
        action="append",
        default=[],
        help="Limit tokens per model, format model=limit. Repeatable.",
    )
    parser.add_argument(
        "--dataset-path-setting",
        type=Path,
        default=None,
        help="Optional dataset path injected into WorkflowSettings",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Start index within dataset",
    )
    parser.add_argument(
        "--max-web-results",
        type=int,
        default=3,
        help="Maximum results for web retrieval tool",
    )
    parser.add_argument(
        "--skip-task",
        action="append",
        default=[],
        help="Task id to skip (can be used multiple times)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list tasks without invoking MAS",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    tasks = load_tasks(args.dataset)
    base_settings = WorkflowSettings(
        dataset_path=str(args.dataset_path_setting) if args.dataset_path_setting else "",
        output_dir=str(args.artifact_dir),
        result_filename="answer.md",
        max_web_results=args.max_web_results,
        llm_model_name=args.llm_model,
        llm_token_limits=parse_llm_token_limits(args.llm_token_limit),
    )

    asyncio.run(
        evaluate_tasks(
            tasks=tasks,
            output_path=args.output,
            attachments_root=args.attachments_dir,
            base_settings=base_settings,
            limit=args.max_tasks,
            start_index=args.start_index,
            skip_ids=set(args.skip_task or []),
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()

