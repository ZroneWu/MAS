# MultiAgent Workflow 实现说明

## 实现完成情况

✅ 已完成四个核心 Agent 的实现：
- **PlannerAgent**: 分析问题并制定解决策略
- **RetrieverAgent**: 从互联网获取信息（支持多轮检索）
- **ReasonerAgent**: 进行逻辑推理并生成答案
- **MasterAgent**: 全局流程编排和质量检查

## 系统架构

### 1. 黑板系统（Blackboard）
所有 Agent 通过共享黑板进行协作，使用三个命名空间：
- `plan`: 存储 PlannerAgent 生成的计划
- `retrieval`: 存储 RetrieverAgent 的检索结果
- `reasoning`: 存储 ReasonerAgent 的推理结果

### 2. 工作流程

```
用户问题 → MasterAgent
              ↓
       1. blackboard_reset() 清空黑板
              ↓
       2. 调用 planner_agent 分析问题
              ↓
       3. 读取 plan 命名空间
              ↓
       4. 如果需要检索 → 调用 retriever_agent
              ↓
       5. 读取 retrieval 命名空间（如果有检索）
              ↓
       6. 调用 reasoner_agent 推理
              ↓
       7. 读取 reasoning 命名空间
              ↓
       8. 质量检查
              ↓
       9. 调用 result_writer 写入文件
              ↓
       10. 返回最终答案
```

### 3. Agent 详细说明

#### PlannerAgent（规划专家）
**工具**:
- `blackboard_write`: 写入计划到黑板
- `blackboard_read`: 读取黑板内容

**输出格式**（写入 `plan` 命名空间）:
```json
{
  "query": "标准化后的用户问题",
  "attachments": ["附件路径列表"],
  "task_type": "retrieval | reasoning | hybrid",
  "search_keywords": ["关键词1", "关键词2"],
  "reasoning_steps": ["步骤1", "步骤2"],
  "steps": [
    {"id": "step_1", "owner": "retriever_agent", "desc": "描述"}
  ],
  "constraints": {
    "format": "输出格式",
    "required_keys": ["必需字段"],
    "bounds": {}
  },
  "reasoning_hints": ["提示1", "提示2"]
}
```

#### RetrieverAgent（检索专家）
**工具**:
- `blackboard_read`: 读取计划
- `blackboard_write`: 写入检索结果
- `web_retriever`: 调用 DuckDuckGo API 进行网页检索

**特点**:
- 支持多轮检索（最多3轮）
- 自动评估结果质量并决定是否继续检索
- 支持中英文关键词切换

**输出格式**（写入 `retrieval` 命名空间）:
```json
{
  "query": "原始查询",
  "search_keywords": ["使用的关键词"],
  "results": [
    {"title": "标题", "url": "URL", "snippet": "摘要"}
  ],
  "status": "success | no_results | error",
  "rounds": 1,
  "metadata": {
    "api_limitations": "说明",
    "retrieval_note": "备注"
  }
}
```

#### ReasonerAgent（推理专家）
**工具**:
- `blackboard_read`: 读取计划和检索结果
- `blackboard_write`: 写入推理结果
- `calculate_expression`: 进行数学计算

**推理策略**:
- 直接引用：检索结果直接包含答案
- 逻辑推导：基于检索结果进行推理
- 数值计算：使用数学工具计算
- 组合推理：结合多个证据源

**输出格式**（写入 `reasoning` 命名空间）:
```json
{
  "answer": "最终答案",
  "reasoning": "推理过程",
  "citations": ["引用URL"],
  "confidence": "high | medium | low",
  "evidence_used": ["证据1", "证据2"]
}
```

#### MasterAgent（主控协调器）
**工具**:
- `blackboard_reset`: 重置黑板
- `blackboard_read`: 读取黑板所有内容
- `result_writer`: 写入结果文件

**子Agent**:
- planner_agent
- retriever_agent
- reasoner_agent

**职责**:
1. 初始化黑板
2. 按顺序调用各专家 Agent
3. 监控执行状态
4. 质量检查
5. 错误纠正（最多重试1次）
6. 写入结果文件

## 使用方法

### 1. 命令行使用

```bash
# 单个问题查询
python -m workflow.cli --query "2024年巴黎奥运会什么时候开始？"

# 带附件的问题
python -m workflow.cli --query "分析图片中的人物身份" --attachments dataset/valid/image.jpg

# 指定输出目录
python -m workflow.cli --query "问题" --output-dir ./outputs --result-filename answer.md

# 限制Web检索结果数量
python -m workflow.cli --query "问题" --max-web-results 5
```

### 2. 批量评估

```bash
cd workflow

# 评估数据集（最多10个任务）
python -m evaluator \
  --dataset dataset/valid/data.jsonl \
  --attachments-dir dataset/valid \
  --output outputs/eval_results.jsonl \
  --artifact-dir outputs/artifacts \
  --max-tasks 10

# 继续未完成的评估
python -m evaluator \
  --dataset dataset/valid/data.jsonl \
  --attachments-dir dataset/valid \
  --output outputs/eval_results.jsonl \
  --artifact-dir outputs/artifacts \
  --max-tasks 100
```

### 3. 代码中使用

```python
import asyncio
from workflow import WorkflowSettings, run_cli

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

在项目根目录或 workflow 目录创建 `.env` 文件：

```env
DEFAULT_LLM_API_KEY=your_api_key
DEFAULT_LLM_BASE_URL=https://api.example.com
DEFAULT_LLM_MODEL_NAME=your_model_name
```

### WorkflowSettings 参数

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

## 关键特性

### 1. 多轮检索
RetrieverAgent 会自动评估检索结果质量，如果不充分会进行多轮检索（最多3轮）：
- 第一轮：使用原始关键词
- 第二轮：尝试更具体的关键词或不同组合
- 第三轮：尝试英文关键词或其他角度

### 2. 质量检查
MasterAgent 在流程结束时进行全面的质量检查：
- 逻辑一致性
- 格式正确性
- 证据充分性
- 推理完整性
- 答案准确性

### 3. 错误纠正
如果质量检查发现问题，MasterAgent 会：
- 总结错误原因
- 根据错误类型重新调用相关 Agent
- 最多重试1次，避免无限循环

### 4. 结果持久化
每个任务的结果都会写入文件：
- 单个任务：写入指定的 `result_filename`
- 批量评估：每个任务写入 `{task_id}.md`，并在 `eval_results.jsonl` 中记录

## 注意事项

1. **LLM配置**: 确保正确配置 LLM API 密钥和端点
2. **网络访问**: RetrieverAgent 需要网络访问以进行 Web 检索
3. **重试限制**: 错误纠正最多重试1次
4. **多轮检索限制**: RetrieverAgent 最多进行3轮检索
5. **黑板状态**: 每次任务开始前，MasterAgent 会清空黑板

## 文件结构

```
workflow/
├── agents.py              # 四个核心 Agent 的实现
├── blackboard.py          # 黑板系统
├── builder.py             # 工作流构建器
├── cli.py                 # 命令行接口
├── constants.py           # 常量定义
├── evaluator.py           # 批量评估工具
├── settings.py            # 配置类
├── tooling.py             # 工具函数
├── utils.py               # 工具函数
├── __init__.py            # 包初始化
└── README.md              # 详细文档
```

## 扩展建议

1. **添加更多检索源**: 除了 DuckDuckGo，可以集成其他搜索引擎 API
2. **增强推理能力**: 为 ReasonerAgent 添加更多专业工具
3. **优化检索策略**: 根据问题类型自动选择最佳检索策略
4. **并行处理**: 支持多 Agent 并行协作
5. **持久化存储**: 将黑板状态持久化，支持断点续传

## 故障排查

### 问题1: Agent 不调用工具
**现象**: MasterAgent 只回复文字，不调用工具

**解决方法**:
- 检查 prompt 是否足够明确
- 确保 additional_prompt 强调了必须调用工具
- 增加 max_react_rounds 参数

### 问题2: 工具不存在
**现象**: 错误 "Tool [xxx] not exists"

**解决方法**:
- 检查工具名称是否正确
- 确保在 builder.py 中注册了所有必需的工具
- 检查 preset_tools 是否正确导入

### 问题3: 检索结果为空
**现象**: RetrieverAgent 返回空结果

**解决方法**:
- DuckDuckGo API 可能返回有限结果，这是正常的
- 尝试调整搜索关键词
- 增加 max_web_results 参数

### 问题4: 黑板数据污染
**现象**: 不同任务之间的数据混淆

**解决方法**:
- 确保 MasterAgent 在每次任务开始前调用 blackboard_reset
- 检查黑板锁是否正常工作

## 测试

运行测试脚本验证系统：

```bash
# 测试 Agent 导入和实例化
python test_agents_import.py

# 测试完整工作流
python test_workflow_agents.py
```

## 版本信息

- 实现日期: 2025-11-12
- OxyGent 版本: 1.0.0
- Python 版本要求: >= 3.8

## 许可证

遵循 OxyGent 框架的许可证要求。

