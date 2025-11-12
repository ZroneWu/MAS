"""Factory helpers to assemble the workflow oxy space and runtime."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from oxygent import Config, MAS, oxy, preset_tools
from oxygent.oxy import FunctionTool
from dotenv import load_dotenv

from .agents import (
    MasterAgent,
    PlannerAgent,
    ReasonerAgent,
    RetrieverAgent,
)
from .blackboard import read_blackboard, reset_blackboard, write_blackboard
from .constants import (
    BLACKBOARD_READ_TOOL,
    BLACKBOARD_RESET_TOOL,
    BLACKBOARD_WRITE_TOOL,
    RESULT_WRITER_TOOL,
    TASK_LOADER_TOOL,
    WEB_RETRIEVER_TOOL,
)
from .settings import WorkflowSettings
from .tooling import (
    load_tasks,
    retrieve_open_web,
    write_result,
)

logger = logging.getLogger(__name__)
load_dotenv()
print(os.getenv("DEFAULT_LLM_API_KEY"))
print(os.getenv("DEFAULT_LLM_BASE_URL"))
print(os.getenv("DEFAULT_LLM_MODEL_NAME"))

def build_custom_tools() -> list[FunctionTool]:
    """创建工作流所需的自定义工具。"""

    return [
        FunctionTool(
            name=TASK_LOADER_TOOL,
            desc="读取 JSONL 数据集并给出任务摘要。",
            func_process=load_tasks,
        ),
        FunctionTool(
            name=BLACKBOARD_WRITE_TOOL,
            desc="将内容写入共享黑板，支持命名空间合并。",
            func_process=write_blackboard,
        ),
        FunctionTool(
            name=BLACKBOARD_READ_TOOL,
            desc="从共享黑板读取指定命名空间的数据。",
            func_process=read_blackboard,
        ),
        FunctionTool(
            name=BLACKBOARD_RESET_TOOL,
            desc="重置共享黑板中的命名空间。",
            func_process=reset_blackboard,
        ),
        FunctionTool(
            name=WEB_RETRIEVER_TOOL,
            desc="调用 DuckDuckGo API 进行轻量检索。",
            func_process=retrieve_open_web,
        ),
        FunctionTool(
            name=RESULT_WRITER_TOOL,
            desc="将字符串内容写入目标路径并返回文件信息。",
            func_process=write_result,
        ),
    ]


def build_oxy_space(settings: WorkflowSettings) -> list[Any]:
    """组装 MAS 运行所需的 oxy_space。"""

    llm_name = settings.llm_model_name
    Config.set_agent_llm_model(llm_name)

    llm_params = {}
    if settings.llm_token_limits.get(llm_name):
        limit = settings.llm_token_limits[llm_name]
        llm_params["max_tokens"] = limit
        llm_params.setdefault("max_output_tokens", limit)

    default_llm = oxy.HttpLLM(
        name=llm_name,
        desc="默认 HTTP LLM，用于 ReasonerAgent 推理。",
        api_key=os.getenv("DEFAULT_LLM_API_KEY"),
        base_url=os.getenv("DEFAULT_LLM_BASE_URL"),
        model_name=os.getenv("DEFAULT_LLM_MODEL_NAME"),
    )

    tools = build_custom_tools()

    agents = [
        PlannerAgent(settings),
        RetrieverAgent(settings),
        ReasonerAgent(settings),
        MasterAgent(settings),
    ]

    return [
        default_llm,
        preset_tools.math_tools,
        preset_tools.file_tools,
        *tools,
        *agents,
    ]


async def run_cli(
    settings: WorkflowSettings,
    query: str,
    attachments: Optional[list[str]] = None,
) -> dict[str, Any]:
    """CLI 模式运行一次工作流。"""

    attachments = attachments or []
    Config.set_app_name("oxygent_workflow")
    Config.set_server_auto_open_webpage(False)
    Config.set_message_is_stored(False)

    oxy_space = build_oxy_space(settings)

    async with MAS(oxy_space=oxy_space) as mas:
        oxy_response = await mas.chat_with_agent(
            payload={
                "query": query,
                "attachments": attachments,
                "shared_data": {"settings": settings.to_shared_dict()},
            }
        )
        return {
            "result": oxy_response.output,
            "trace_id": oxy_response.oxy_request.current_trace_id,
        }

