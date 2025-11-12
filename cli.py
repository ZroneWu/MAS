"""Command line entry point for the workflow package."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Sequence

from .builder import run_cli
from .settings import WorkflowSettings
from .utils import parse_llm_token_limits


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行基于 OxyGent 的多智能体工作流")
    parser.add_argument("--query", required=True, help="用户问题或任务描述")
    parser.add_argument("--dataset", type=str, help="任务数据集 JSONL 路径", default=None)
    parser.add_argument(
        "--attachments",
        nargs="*",
        default=[],
        help="需要注入的附件路径列表",
    )
    parser.add_argument("--output-dir", default="./outputs", help="结果输出目录")
    parser.add_argument("--result-filename", default="answer.md", help="结果文件名")
    parser.add_argument("--max-tasks", type=int, default=1, help="读取数据集条目上限")
    parser.add_argument(
        "--max-web-results",
        type=int,
        default=3,
        help="Web 检索返回条目数",
    )
    parser.add_argument(
        "--llm-model",
        default=os.getenv("DEFAULT_LLM_NAME", "default_llm"),
        help="推理 Agent 使用的 LLM 标识",
    )
    parser.add_argument(
        "--llm-token-limit",
        action="append",
        default=[],
        help="限制模型生成 token 数量，格式为 model=limit，可重复使用。",
    )
    return parser.parse_args(args=argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    settings = WorkflowSettings(
        dataset_path=args.dataset,
        max_tasks=args.max_tasks,
        output_dir=args.output_dir,
        result_filename=args.result_filename,
        max_web_results=args.max_web_results,
        llm_model_name=args.llm_model,
        llm_token_limits=parse_llm_token_limits(args.llm_token_limit),
    )

    result = asyncio.run(
        run_cli(settings, query=args.query, attachments=args.attachments)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

