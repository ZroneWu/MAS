# MultiAgent 工作流系统

基于 OxyGent 框架的多智能体协作系统，用于解决复杂问题，包括需要互联网信息检索和深度推理的任务。

## 系统架构

本系统包含四个核心智能体（Agent），通过共享黑板（Blackboard）进行协作：

### 1. PlannerAgent（规划专家）

**职责**：分析问题并制定解决策略

**功能**：
- 解析用户查询和附件，理解任务目标
- 判断问题类型：
  - **需要外部信息的问题**：识别需要搜索的关键词，交给 RetrieverAgent
  - **需要推理的问题**：分解求解步骤或给出思考方向，交给 ReasonerAgent
- 生成多步骤执行计划
- 识别答案格式约束和任务类型
- 将计划写入黑板 `plan` 命名空间

**输出格式**：
```json
{
  "query": "标准化后的用户问题",
  "attachments": ["附件路径列表"],
  "task_type": "retrieval" | "reasoning" | "hybrid",
  "search_keywords": ["搜索关键词列表"],
  "reasoning_steps": ["推理步骤或思考方向"],
  "steps": [
    {
      "id": "步骤标识",
      "owner": "负责的Agent名称",
      "desc": "步骤描述"
    }
  ],
  "constraints": {
    "format": "输出格式",
    "required_keys": ["必需字段"],
    "bounds": {}
  },
  "reasoning_hints": ["推理提示"]
}
```

### 2. RetrieverAgent（检索专家）

**职责**：从互联网获取信息

**功能**：
- 从黑板读取计划，提取检索关键词
- 调用 `web_retriever` 工具执行网页检索（使用 DuckDuckGo API）
- **支持多轮检索**：如果第一轮结果不充分，根据原问题或检索结果生成新的关键词继续检索
- 优化检索策略（中文/英文关键词、时效性问题处理等）
- 将检索结果写入黑板 `retrieval` 命名空间

**多轮检索策略**：
- 最多进行3轮检索
- 每轮检索后评估结果质量
- 如果结果不充分，尝试更具体的关键词或不同的关键词组合

**输出格式**：
```json
{
  "query": "原始查询",
  "search_keywords": ["实际使用的搜索关键词列表"],
  "results": [
    {
      "title": "结果标题",
      "url": "结果URL",
      "snippet": "摘要信息"
    }
  ],
  "status": "success" | "no_results" | "error",
  "rounds": 检索轮数,
  "metadata": {
    "api_limitations": "API限制说明",
    "retrieval_note": "检索备注"
  }
}
```

### 3. ReasonerAgent（推理专家）

**职责**：逻辑推理和答案生成

**功能**：
- 从黑板读取计划和检索结果
- 根据任务类型选择推理策略（直接引用、逻辑推导、数值计算、组合推理）
- 按照计划中的 `reasoning_steps` 进行逐步推理
- 使用数学工具进行计算（如需要）
- 生成符合格式约束的最终答案
- 将推理结果写入黑板 `reasoning` 命名空间

**推理策略**：
- **直接引用**：检索结果直接包含答案时引用并标注来源
- **逻辑推导**：基于检索结果进行逻辑推理
- **数值计算**：使用数学工具进行计算
- **组合推理**：结合多个证据源进行综合分析

**输出格式**：
```json
{
  "answer": "最终答案",
  "reasoning": "推理过程",
  "citations": ["引用的检索结果URL"],
  "confidence": "high" | "medium" | "low",
  "evidence_used": ["使用的证据摘要"]
}
```

### 4. MasterAgent（主控协调器）

**职责**：全局流程编排和质量检查

**功能**：
- 初始化黑板状态，清空上一轮任务的残留数据
- 按照固定流水线顺序调用各专家Agent：Planner → Retriever → Reasoner
- 监控每个阶段的执行状态
- **质量检查**：在流程结束时，回顾黑板中的所有内容，检查：
  1. 逻辑一致性：答案是否与问题匹配？推理过程是否合理？
  2. 格式正确性：答案是否符合约束要求？
  3. 证据充分性：是否使用了检索结果？检索结果是否相关？
  4. 推理完整性：推理步骤是否完整？
  5. 答案准确性：答案是否合理？是否有明显的错误？
- **错误纠正**：如果发现问题，总结错误原因，让相关Agent重新生成（最多重试1次）

**工作流程**：
```
1. 黑板初始化（清空所有命名空间）
2. 调用 PlannerAgent 制定计划
3. 如果需要检索，调用 RetrieverAgent（可能多轮）
4. 调用 ReasonerAgent 进行推理
5. 质量检查：
   - 如果通过 → 返回最终答案
   - 如果发现问题 → 重新调用相关Agent → 再次质量检查
```

## 黑板系统（Blackboard）

所有Agent通过共享黑板进行数据交换，使用命名空间隔离不同阶段的数据：

- **`plan`**：存储PlannerAgent生成的计划
- **`retrieval`**：存储RetrieverAgent的检索结果
- **`reasoning`**：存储ReasonerAgent的推理结果

### 黑板操作工具

- `blackboard_write`：写入内容到指定命名空间
- `blackboard_read`：从指定命名空间读取内容
- `blackboard_reset`：重置指定命名空间或清空整个黑板

## 使用示例

### 命令行使用

```bash
# 单个问题查询
python -m workflow.cli --query "2024年巴黎奥运会什么时候开始？"

# 带附件的问题
python -m workflow.cli --query "分析图片中的人物身份" --attachments dataset/valid/image.jpg

# 指定输出目录和文件名
python -m workflow.cli --query "问题" --output-dir ./outputs --result-filename answer.md

# 限制Web检索结果数量
python -m workflow.cli --query "问题" --max-web-results 5
```

### 批量评估

```bash
# 评估数据集
python -m evaluator --dataset dataset/valid/data.jsonl --attachments-dir dataset/valid --output outputs/eval_results.jsonl --artifact-dir outputs/artifacts --max-tasks 10
```

### 代码中使用

```python
from workflow import WorkflowSettings, run_cli
import asyncio

settings = WorkflowSettings(
    output_dir="./outputs",
    result_filename="answer.md",
    max_web_results=3,
    llm_model_name="default_llm"
)

async def main():
    result = await run_cli(
        settings,
        query="2024年巴黎奥运会什么时候开始？",
        attachments=[]
    )
    print(result["result"])

asyncio.run(main())
```

## 配置说明

### 环境变量

在 `.env` 文件中配置LLM相关参数：

```env
DEFAULT_LLM_API_KEY=your_api_key
DEFAULT_LLM_BASE_URL=https://api.example.com
DEFAULT_LLM_MODEL_NAME=your_model_name
```

### WorkflowSettings

```python
@dataclass
class WorkflowSettings:
    dataset_path: Optional[str] = None      # 数据集路径
    max_tasks: int = 1                      # 最大任务数
    output_dir: str = "./outputs"           # 输出目录
    result_filename: str = "answer.md"      # 结果文件名
    max_web_results: int = 3                # Web检索最大结果数
    llm_model_name: str = "default_llm"     # LLM模型名称
    llm_token_limits: dict[str, int] = {}   # Token限制
```

## 工作流程详解

### 完整执行流程

```
用户问题
    ↓
MasterAgent 初始化黑板
    ↓
PlannerAgent 分析问题
    ├─→ 判断任务类型
    ├─→ 生成搜索关键词（如果需要检索）
    ├─→ 生成推理步骤（如果需要推理）
    └─→ 写入黑板 plan 命名空间
    ↓
RetrieverAgent（如果需要）
    ├─→ 读取计划，提取关键词
    ├─→ 执行第一轮检索
    ├─→ 评估结果质量
    ├─→ 如果需要，执行多轮检索（最多3轮）
    └─→ 写入黑板 retrieval 命名空间
    ↓
ReasonerAgent 推理
    ├─→ 读取计划和检索结果
    ├─→ 按照推理步骤逐步推理
    ├─→ 使用数学工具计算（如需要）
    ├─→ 生成最终答案
    └─→ 写入黑板 reasoning 命名空间
    ↓
MasterAgent 质量检查
    ├─→ 读取所有黑板内容
    ├─→ 检查逻辑一致性、格式正确性、证据充分性等
    ├─→ 如果发现问题：
    │   ├─→ 总结错误原因
    │   ├─→ 重新调用相关Agent（最多重试1次）
    │   └─→ 再次质量检查
    └─→ 如果通过：
        └─→ 返回最终答案
```

### 多轮检索示例

对于复杂问题，RetrieverAgent可能需要进行多轮检索：

1. **第一轮**：使用原始关键词检索
2. **评估**：如果结果不充分，分析原因
3. **第二轮**：尝试更具体的关键词或不同的关键词组合
4. **第三轮**：如果仍不充分，尝试英文关键词或其他角度

例如，查询"2024年巴黎奥运会开幕式时间"：
- 第一轮：`["2024年巴黎奥运会开幕式"]`
- 第二轮：`["Paris Olympics 2024 opening ceremony", "2024年7月26日"]`
- 第三轮：`["2024夏季奥运会开幕式时间"]`

### 错误纠正机制

MasterAgent的质量检查包括：

1. **逻辑一致性检查**：
   - 答案是否回答了问题？
   - 推理过程是否合理？
   - 是否有逻辑矛盾？

2. **格式正确性检查**：
   - 答案格式是否符合约束要求？
   - 是否包含所有必需字段？

3. **证据充分性检查**：
   - 对于需要检索的问题，是否使用了检索结果？
   - 检索结果是否与问题相关？

4. **推理完整性检查**：
   - 推理步骤是否完整？
   - 是否有遗漏的关键步骤？

5. **答案准确性检查**：
   - 答案是否合理？
   - 是否有明显的错误或矛盾？

如果发现问题，MasterAgent会：
1. 总结错误原因和来由
2. 根据错误类型，决定重新调用哪个Agent：
   - 计划问题 → 重新调用 PlannerAgent
   - 检索不充分 → 重新调用 RetrieverAgent（最多重试1次）
   - 推理问题 → 重新调用 ReasonerAgent（最多重试1次）
3. 重新执行质量检查

## 依赖项

主要依赖：
- `oxygent`：多智能体协作框架
- `httpx`：HTTP客户端（用于Web检索）
- `PIL`：图像处理（用于多模态支持）

## 项目结构

```
workflow/
├── agents.py              # Agent定义（Planner, Retriever, Reasoner, Master）
├── blackboard.py          # 黑板系统实现
├── builder.py             # 工作流构建器
├── cli.py                 # 命令行接口
├── constants.py           # 常量定义
├── evaluator.py           # 批量评估工具
├── settings.py            # 配置类
├── tooling.py             # 工具函数（Web检索、文件操作等）
├── utils.py               # 工具函数
└── README.md              # 本文档
```

## 注意事项

1. **LLM配置**：确保正确配置LLM API密钥和端点
2. **网络访问**：RetrieverAgent需要网络访问以进行Web检索
3. **重试限制**：为避免无限循环，错误纠正最多重试1次
4. **多轮检索限制**：RetrieverAgent最多进行3轮检索
5. **黑板状态**：每次任务开始前，MasterAgent会清空黑板，避免跨任务污染

## 扩展建议

1. **添加更多检索源**：除了DuckDuckGo，可以集成其他搜索引擎API
2. **增强推理能力**：为ReasonerAgent添加更多专业工具（如代码执行、数据分析等）
3. **优化检索策略**：根据问题类型自动选择最佳检索策略
4. **并行处理**：对于可以并行执行的任务，支持多Agent并行协作
5. **持久化存储**：将黑板状态持久化，支持断点续传

## 许可证

[根据项目实际情况填写]

