"""服务级系统提示词：意图判断 + 插件路由 + 能力工作流。"""

from __future__ import annotations

from insightagent.plugin_support import LoadedPlugin

BASE_PROMPT = """你是企业数据智能体，负责回答两类问题：报表检索与数据查询分析。

## 工作流程

1. **意图判断**：判断用户问题是"找报表"、"查数据/数据分析"，还是"结合报表口径查数据"。仅使用当前可用的工具。
2. **报表检索**（若可用 report_search）：提炼检索意图并扩展指标同义词（如 营收→收入/营业收入），调用 report_search(top_k=3)；结果不足改写检索式重试，最多再试 2 次。
3. **数据查询**（若可用 db_list/db_schema/db_query）：
   - db_list 定位目标库 → db_schema 确认表结构 → 说明推理并生成单条只读 SELECT/WITH → db_query 执行；
   - 执行报错时读错误信息修正 SQL 重试，最多 3 次；结果被截断时改写为聚合查询。
4. **交叉印证**：涉及指标口径时，可先 report_search 获取口径定义，再据此写 SQL，回答中注明口径来源。
5. **输出报告**：中文结构化——结论先行 / 关键数字 / markdown 表格 / 报表链接（如有）/ 数据局限说明。

## 思考过程

- 推理与分析过程请写在思考中，最终报告只保留结论与关键依据。

## 原则

- 诚实：查不到、检索无结果就明说，绝不编造数据、表名、报表名或链接。
- 只读：仅执行只读查询；任何写操作请求直接拒绝并说明原因。
- 工具缺失：当问题需要的能力工具不可用时，明确告知用户缺什么配置。
"""


def build_system_prompt(plugins: list[LoadedPlugin], cfg) -> str:
    """服务级基础提示词 + 已装配插件的能力说明。"""
    parts: list[str] = [BASE_PROMPT]
    limits = (
        f"\n## 当前限制\n\n- 单查询返回行数上限: {cfg.agent.max_rows}\n"
        f"- 查询超时: {cfg.agent.query_timeout_seconds}s\n"
        f"- SQL 失败重试上限: {cfg.agent.sql_retry_limit} 次\n"
        f"- 检索式改写重试上限: {cfg.agent.search_retry_limit} 次\n"
    )
    parts.append(limits)
    for plugin in plugins:
        tool_names = ", ".join(t.name for t in plugin.tools) or "（无）"
        parts.append(f"\n## 已装配能力: {plugin.name}\n\n{plugin.description}\n\n可用工具: {tool_names}\n")
    return "".join(parts)


def build_capability_addendum(mcp_tools: list, skills: list) -> str:
    """会话级能力附录：本次启用的 MCP 连接器工具与技能清单（追加到系统提示词）。"""
    parts: list[str] = []
    if mcp_tools:
        lines = [f"- `{t.name}`: {(t.description or '').strip().splitlines()[0] if t.description else ''}" for t in mcp_tools]
        parts.append(
            "## 已启用 MCP 连接器工具\n\n"
            "以下工具来自外部 MCP 服务器，调用方式与其他工具相同：\n" + "\n".join(lines) + "\n"
        )
    if skills:
        lines = [f"- `{s.name}`: {s.description or ''}" for s in skills]
        parts.append(
            "## 已启用技能（skill）\n\n"
            "可用 `skill` 工具按名称读取技能全文，先读技能再按其方法完成任务：\n" + "\n".join(lines) + "\n"
        )
    return "\n".join(parts)
