"""report_search 工具：通过 MCP「报表检索」服务检索报表目录。"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

from insightagent.config import InsightConfig


class ReportSearchInput(BaseModel):
    query: str = Field(description="检索式：由用户问题提炼/改写的关键词组合，可含指标同义词")
    top_k: int = Field(default=3, ge=1, le=10)


class ReportSearchTool(BaseTool):
    name = "report_search"
    description = (
        "在报表目录中做语义检索（后端为 MCP 报表检索服务），"
        "返回最相关的报表（名称、链接、指标清单、业务描述、相似度）。"
        "结果不足时请改写检索式（扩展指标同义词，如 营收→收入/营业收入）再试。"
    )
    input_model = ReportSearchInput

    def __init__(
        self,
        config: InsightConfig,
        *,
        server: str,
        tool: str = "search",
        collection: str = "",
    ) -> None:
        self._server = server
        self._mcp_tool = tool
        self._collection = collection or (config.milvus.collection if config.milvus else "")
        self._mcp = None  # 会话装配时注入的 McpClientManager

    def attach_mcp(self, manager) -> None:
        """注入会话级 MCP 客户端管理器（会话池在裁剪工具白名单后调用）。"""
        self._mcp = manager

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: ReportSearchInput, context: ToolExecutionContext) -> ToolResult:
        del context
        if self._mcp is None:
            return ToolResult(is_error=True, output="报表检索不可用：会话未装配 MCP 客户端。")
        if not self._collection:
            return ToolResult(
                is_error=True,
                output="报表检索不可用：未指定 collection（config.yaml 的 milvus.collection 或 plugin.json 的 mcp.collection）。",
            )
        payload = {
            "collection_name": self._collection,
            "query_text": arguments.query,
            "top_k": arguments.top_k,
        }
        try:
            raw = await self._mcp.call_tool(self._server, self._mcp_tool, payload)
        except Exception as exc:  # noqa: BLE001 - 连接/调用失败都转成工具错误
            return ToolResult(
                is_error=True,
                output=f"报表检索失败（MCP {self._server}/{self._mcp_tool}）: {exc}",
            )
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return ToolResult(output=raw)
        hits = data.get("hits") if isinstance(data, dict) else None
        if hits is None:
            return ToolResult(output=raw)  # 未知结构原样透传，交给模型解读
        results = [self._normalize_hit(hit) for hit in hits]
        if not results:
            return ToolResult(
                output=json.dumps(
                    {"results": [], "hint": "无相关报表，建议更换检索关键词（扩展同义词）后重试。"},
                    ensure_ascii=False,
                )
            )
        return ToolResult(
            output=json.dumps(
                {"query": arguments.query, "source": f"mcp:{self._server}", "results": results},
                ensure_ascii=False,
                indent=2,
            )
        )

    @staticmethod
    def _normalize_hit(hit) -> dict:
        """MCP hit（{score,id,text}）→ 与本地检索一致的扁平结果。"""
        if not isinstance(hit, dict):
            return {"score": 0.0, "text": str(hit)}
        fields = hit.get("text")
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except json.JSONDecodeError:
                fields = {"text": fields}
        if not isinstance(fields, dict):
            fields = {"text": str(fields)}
        item = {"score": float(hit.get("score") or 0.0)}
        item.update(fields)
        if hit.get("id") and "id" not in item:
            item["id"] = hit["id"]
        return item
