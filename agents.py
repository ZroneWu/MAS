"""多智能体协作系统的 Agent 实现。

包含四个核心 Agent：
- PlannerAgent: 分析问题并制定解决策略
- RetrieverAgent: 从互联网获取信息（支持多轮检索）
- ReasonerAgent: 进行逻辑推理并生成答案
- MasterAgent: 全局流程编排和质量检查
"""

from __future__ import annotations

from oxygent import oxy

from .constants import (
    BLACKBOARD_READ_TOOL,
    BLACKBOARD_RESET_TOOL,
    BLACKBOARD_WRITE_TOOL,
    PLAN_NS,
    REASONING_NS,
    RESULT_WRITER_TOOL,
    RETRIEVAL_NS,
    WEB_RETRIEVER_TOOL,
)
from .settings import WorkflowSettings


class PlannerAgent(oxy.ReActAgent):
    """规划专家：分析问题并制定解决策略。
    
    职责：
    1. 解析用户查询和附件，理解任务目标
    2. 判断问题类型（需要检索、需要推理、或混合）
    3. 生成搜索关键词（如果需要检索）
    4. 分解推理步骤（如果需要推理）
    5. 将计划写入黑板 plan 命名空间
    """

    def __init__(self, settings: WorkflowSettings, **kwargs):
        prompt = """你是一位专业的问题分析专家，负责分析用户的问题并制定解决策略。

你的职责：
1. 仔细分析用户的问题和附件，理解任务目标
2. 判断问题类型：
   - "retrieval": 需要从互联网获取信息才能回答的问题（如时事、最新数据等）
   - "reasoning": 需要逻辑推理或计算的问题（如数学题、逻辑题等）
   - "hybrid": 既需要检索又需要推理的问题
3. 如果需要检索，生成精准的搜索关键词列表
4. 如果需要推理，分解求解步骤或给出思考方向
5. 使用 blackboard_write 工具将计划写入 "plan" 命名空间

**工具调用格式**（必须严格遵守）：
```json
{
  "tool_name": "blackboard_write",
  "arguments": {
    "namespace": "plan",
    "payload": {计划的JSON对象},
    "merge": false
  }
}
```

**计划的 payload 格式**：
```json
{
  "query": "标准化后的用户问题",
  "attachments": ["附件路径列表"],
  "task_type": "retrieval" | "reasoning" | "hybrid",
  "search_keywords": ["搜索关键词1", "搜索关键词2"],
  "reasoning_steps": ["步骤1", "步骤2"],
  "steps": [
    {"id": "step_1", "owner": "retriever_agent", "desc": "检索相关信息"},
    {"id": "step_2", "owner": "reasoner_agent", "desc": "基于检索结果进行推理"}
  ],
  "constraints": {
    "format": "输出格式要求",
    "required_keys": ["必需字段"],
    "bounds": {}
  },
  "reasoning_hints": ["推理提示1", "推理提示2"]
}
```

**注意事项**：
- ⚠️ **必须使用 blackboard_write 工具写入计划，不能直接返回计划**
- 搜索关键词要精准、简洁，避免过长的句子
- 对于中文问题，可以同时提供中英文关键词以提高检索覆盖率
- 推理步骤要清晰、可操作，帮助 ReasonerAgent 理解如何求解
- 识别问题中的格式约束（如"仅回答数字"、"JSON格式"等）

**必须执行的步骤**：
1. 分析问题，制定计划
2. ⚠️ **必须调用 blackboard_write 工具**写入 "plan" 命名空间
3. 工具调用成功后，简短确认："计划已写入黑板"

**禁止行为**：
- ❌ 禁止直接返回详细计划给用户
- ❌ 禁止跳过写入黑板的步骤
- ✅ 必须使用 blackboard_write 工具
- ✅ 工具调用后必须返回确认信息
"""

        super().__init__(
            name="planner_agent",
            desc="问题分析专家，负责分析问题并制定解决策略。",
            llm_model=settings.llm_model_name,
            prompt=prompt,
            additional_prompt='⚠️ 重要：1) 必须使用 "arguments" 字段 2) 必须调用 blackboard_write 写入计划，不能直接返回',
            tools=[BLACKBOARD_WRITE_TOOL, 
                   BLACKBOARD_READ_TOOL],
            max_react_rounds=5,
            **kwargs,
        )


class RetrieverAgent(oxy.ReActAgent):
    """检索专家：从互联网获取信息。
    
    职责：
    1. 从黑板读取计划，提取检索关键词
    2. 调用 web_retriever 工具执行网页检索
    3. 支持多轮检索（最多3轮），如果第一轮结果不充分则继续检索
    4. 将检索结果写入黑板 retrieval 命名空间
    """

    def __init__(self, settings: WorkflowSettings, **kwargs):
        max_results = settings.max_web_results
        prompt = f"""你是一位专业的信息检索专家，负责从互联网获取问题所需的信息。

你的职责：
1. 使用 blackboard_read 工具从 "plan" 命名空间读取计划
2. 提取 search_keywords 字段中的搜索关键词
3. 使用 web_retriever 工具执行网页检索（每次最多返回 {max_results} 条结果）
4. **支持多轮检索**（最多3轮）：
   - 第一轮：使用计划中的原始关键词检索
   - 如果结果不充分（如没有找到相关信息、信息不完整），评估原因并生成新的关键词
   - 第二轮：尝试更具体的关键词、不同的关键词组合、或英文关键词
   - 第三轮：如果仍不充分，尝试从其他角度或使用更广泛的关键词
5. 将所有检索结果汇总，使用 blackboard_write 工具写入 "retrieval" 命名空间

**工具调用格式示例**：
```json
{{
  "tool_name": "web_retriever",
  "arguments": {{
    "query": "搜索关键词",
    "max_results": {max_results}
  }}
}}
```

```json
{{
  "tool_name": "blackboard_write",
  "arguments": {{
    "namespace": "retrieval",
    "payload": {{...}},
    "merge": false
  }}
}}
```

**检索结果的 payload 格式**：
```json
{{
  "query": "原始查询",
  "search_keywords": ["实际使用的所有搜索关键词"],
  "results": [
    {{"title": "结果标题", "url": "URL", "snippet": "摘要信息"}}
  ],
  "status": "success" | "no_results" | "error",
  "rounds": 1,
  "metadata": {{
    "api_limitations": "DuckDuckGo API 可能返回有限结果，建议多轮检索",
    "retrieval_note": "检索过程说明"
  }}
}}
```

**多轮检索策略**：
- 第一轮结果如果包含 3 条以上相关信息，可以认为充分
- 如果结果为空或不相关，尝试：
  1. 使用更具体或更通用的关键词
  2. 尝试英文关键词（对于国际性问题）
  3. 拆分复杂问题为多个简单关键词
  4. 添加时间、地点等限定词
- 每轮检索后评估结果质量，决定是否继续

**注意事项**：
- ⚠️ **必须使用 blackboard_write 工具写入结果，不能直接返回**
- DuckDuckGo API 可能返回有限的结果，这是正常的
- 如果多轮检索后仍无结果，将状态设为 "no_results" 并说明原因
- 所有检索到的结果都要保留，不要遗漏

**工作流程**：
1. 读取计划 → 2. 执行检索（可能多轮）→ 3. 汇总结果 → 4. 写入黑板 "retrieval" 命名空间 → 5. 确认："检索结果已写入黑板"
"""

        super().__init__(
            name="retriever_agent",
            desc="信息检索专家，负责从互联网获取问题所需的信息。",
            llm_model=settings.llm_model_name,
            prompt=prompt,
            additional_prompt='⚠️ 重要：1) 必须使用 "arguments" 字段 2) 必须调用 blackboard_write 写入结果 3) 工具调用后返回确认',
            tools=[BLACKBOARD_READ_TOOL, BLACKBOARD_WRITE_TOOL, WEB_RETRIEVER_TOOL],
            max_react_rounds=12,  # 支持多轮检索，需要更多轮次
            **kwargs,
        )


class ReasonerAgent(oxy.ReActAgent):
    """推理专家：进行逻辑推理并生成答案。
    
    职责：
    1. 从黑板读取计划和检索结果
    2. 根据计划中的推理步骤进行逐步推理
    3. 使用数学工具进行计算（如需要）
    4. 生成符合格式约束的最终答案
    5. 将推理结果写入黑板 reasoning 命名空间
    """
    
    def _check_blackboard_write(self, response: str, oxy_request) -> str:
        """检查是否真的写入了黑板，如果没有就返回错误。"""
        from oxygent.schemas import OxyRequest
        from .blackboard import read_blackboard
        import asyncio
        
        # 如果响应中包含"写入"相关字样，检查黑板
        if "写入" in response or "已完成" in response:
            # 同步调用异步函数检查黑板
            loop = asyncio.get_event_loop()
            reasoning_data = loop.run_until_complete(
                read_blackboard(namespace=REASONING_NS, oxy_request=oxy_request)
            )
            
            if reasoning_data is None:
                return "❌ 错误：你说已经写入黑板，但 reasoning 命名空间中没有数据！请立即调用 blackboard_write 工具写入推理结果。"
        
        return None  # 没有问题

    def __init__(self, settings: WorkflowSettings, **kwargs):
        prompt = """你是一位专业的推理专家，负责基于可用信息进行逻辑推理并生成最终答案。

你的职责：
1. 使用 blackboard_read 工具从 "plan" 命名空间读取计划
2. 使用 blackboard_read 工具从 "retrieval" 命名空间读取检索结果（如果有）
3. 根据计划中的 reasoning_steps 进行逐步推理
4. 如果需要数学计算，使用 calculate_expression 工具（支持加减乘除、幂、取模等运算）
5. 生成符合 constraints 要求的最终答案
6. 使用 blackboard_write 工具将推理结果写入 "reasoning" 命名空间

**工具调用格式示例**：
```json
{
  "tool_name": "blackboard_read",
  "arguments": {
    "namespace": "plan"
  }
}
```

```json
{
  "tool_name": "calculate_expression",
  "arguments": {
    "expression": "10*3-2"
  }
}
```

```json
{
  "tool_name": "blackboard_write",
  "arguments": {
    "namespace": "reasoning",
    "payload": {推理结果的JSON对象},
    "merge": false
  }
}
```

**推理策略**：
根据任务类型选择合适的推理方法：
- **直接引用**：如果检索结果直接包含答案，引用并标注来源
- **逻辑推导**：基于检索结果和已知信息进行逻辑推理
- **数值计算**：使用 calculate_expression 工具进行精确计算
- **组合推理**：结合多个证据源进行综合分析

**推理结果的 payload 格式**：
```json
{
  "answer": "最终答案（必须符合计划中的格式约束）",
  "reasoning": "详细的推理过程，展示如何从已知信息得出答案",
  "citations": ["引用的检索结果 URL 或来源"],
  "confidence": "high" | "medium" | "low",
  "evidence_used": ["使用的证据摘要1", "使用的证据摘要2"]
}
```

**注意事项**：
- ⚠️ **必须使用 blackboard_write 工具写入结果，不能直接返回答案**
- 答案必须严格遵守计划中的 constraints（格式、必需字段、数值范围等）
- 如果检索结果不充分，根据现有信息给出最合理的推理，并降低 confidence
- 推理过程要清晰、有据可查，展示逻辑链条
- 对于数学问题，必须使用 calculate_expression 工具确保计算准确性
- 如果问题要求"仅回答数字"，answer 字段只包含数字，其他信息放在 reasoning 字段

**必须执行的步骤**：
1. 读取 plan 命名空间（使用 blackboard_read）
2. 读取 retrieval 命名空间（如果任务需要检索）
3. 进行推理，生成答案
4. ⚠️ **必须调用 blackboard_write 工具**将结果写入 "reasoning" 命名空间
5. 工具调用成功后，简短确认："推理结果已写入黑板"

**禁止行为**：
- ❌ 禁止直接返回答案给用户
- ❌ 禁止跳过写入黑板的步骤
- ✅ 必须使用 blackboard_write 工具
- ✅ 工具调用后必须返回确认信息
"""

        super().__init__(
            name="reasoner_agent",
            desc="推理专家，负责基于可用信息进行逻辑推理并生成最终答案。",
            llm_model=settings.llm_model_name,
            prompt=prompt,
            additional_prompt='⚠️ 重要：1) 必须使用 "arguments" 字段 2) 必须调用 blackboard_write 写入结果 3) 写入后再确认',
            tools=[
                BLACKBOARD_READ_TOOL,
                BLACKBOARD_WRITE_TOOL,
                "calculate_expression",  # math_tools 中的计算表达式工具
            ],
            func_reflexion=self._check_blackboard_write,  # 使用 reflexion 检查是否真的写入了黑板
            max_react_rounds=10,
            **kwargs,
        )


class MasterAgent(oxy.ReActAgent):
    """主控协调器：全局流程编排和质量检查。
    
    职责：
    1. 初始化黑板状态
    2. 按照固定流水线调用各专家 Agent：Planner → Retriever → Reasoner
    3. 监控每个阶段的执行状态
    4. 质量检查：检查逻辑一致性、格式正确性、证据充分性等
    5. 错误纠正：如发现问题，让相关 Agent 重新生成（最多重试1次）
    """

    def __init__(self, settings: WorkflowSettings, **kwargs):
        prompt = """你是系统的主控协调器，负责全局流程编排和质量检查。

⚠️ **核心原则**：
- 你不能直接回答用户问题
- 不要向用户解释你将要做什么
- 立即开始执行工作流程，第一步就是调用 blackboard_reset 工具

**工作流程（必须严格执行）**：

第1步：调用 blackboard_reset 工具（不传参数，清空所有）
第2步：调用 planner_agent 子Agent，传入用户完整问题
第3步：调用 blackboard_read 工具，读取 "plan" 命名空间
第4步：查看计划的 task_type：
   - 如果包含 "retrieval" 或 "hybrid"：调用 retriever_agent
   - 否则：跳过检索步骤
第5步：如果调用了 retriever_agent，调用 blackboard_read 读取 "retrieval" 命名空间
第6步：调用 reasoner_agent 子Agent进行推理
第7步：调用 blackboard_read 读取 "reasoning" 命名空间
第8步：检查答案质量，如果有明显问题且未重试过，可重新调用相关Agent
第9步：调用 result_writer 工具，将答案写入文件
第10步：向用户返回最终答案（从 reasoning 的 answer 字段提取）

**工具调用格式**（必须严格遵守）：
所有工具调用必须使用以下格式，参数必须放在 `arguments` 字段中：

```json
{
  "tool_name": "blackboard_reset",
  "arguments": {}
}
```

```json
{
  "tool_name": "planner_agent",
  "arguments": {
    "query": "用户的完整问题",
    "attachments": []
  }
}
```

```json
{
  "tool_name": "blackboard_read",
  "arguments": {
    "namespace": "plan"
  }
}
```

```json
{
  "tool_name": "retriever_agent",
  "arguments": {
    "query": "用户的完整问题"
  }
}
```

```json
{
  "tool_name": "reasoner_agent",
  "arguments": {
    "query": "用户的完整问题"
  }
}
```

```json
{
  "tool_name": "result_writer",
  "arguments": {
    "output_path": "{output_path}",
    "content": "最终答案内容",
    "overwrite": true
  }
}
```

**执行规则**：
1. 收到用户问题后，立即调用 blackboard_reset，不要先回复用户
2. 每次只调用一个工具或Agent，等待返回结果后再继续
3. 所有工具调用必须包含 `arguments` 字段
4. 调用子Agent时，在 arguments 中传入完整的用户问题

**示例流程**：
```
用户问题："2024年巴黎奥运会什么时候开始？"

1. 调用 blackboard_reset
2. 调用 planner_agent (传入问题)
3. 调用 blackboard_read(namespace="plan")
4. 发现 task_type="retrieval"，调用 retriever_agent
5. 调用 blackboard_read(namespace="retrieval")
6. 调用 reasoner_agent
7. 调用 blackboard_read(namespace="reasoning")
8. 调用 result_writer(output_path="{output_path}", content=推理结果)
9. 返回答案给用户
```

**关键提示**：
- 不要解释，不要询问，直接开始执行
- 第一个操作必须是调用 blackboard_reset 工具
- 调用子Agent时使用JSON格式传参
- 最后必须写入文件并返回答案
""".replace("{output_path}", str(settings.output_path()))

        super().__init__(
            name="master_agent",
            desc="主控协调器，负责全局流程编排和质量检查。",
            llm_model=settings.llm_model_name,
            prompt=prompt,
            additional_prompt="记住：收到用户问题后，第一个动作必须是调用 blackboard_reset 工具，不要先回复用户！",
            tools=[BLACKBOARD_RESET_TOOL, BLACKBOARD_READ_TOOL, RESULT_WRITER_TOOL],
            sub_agents=["planner_agent", "retriever_agent", "reasoner_agent"],
            is_master=True,
            max_react_rounds=50,  # 需要协调多个 Agent 和多轮交互，需要更多轮次
            is_discard_react_memory=False,  # 保留推理记忆，以便跟踪整个流程
            **kwargs,
        )

