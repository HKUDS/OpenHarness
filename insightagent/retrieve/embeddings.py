"""OpenAI 兼容 embedding 客户端（同步调用，由工具层 to_thread 包装）。"""

from __future__ import annotations

from openai import OpenAI

from insightagent.config import EmbeddingConfig


class EmbeddingError(RuntimeError):
    """查询向量化失败。"""


class EmbeddingClient:
    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._client: OpenAI | None = None

    def _ensure_client(self) -> OpenAI:
        if self._client is None:
            if not (self._config.base_url and self._config.model):
                raise EmbeddingError("embedding 未配置 base_url/model")
            self._client = OpenAI(base_url=self._config.base_url, api_key=self._config.api_key or "EMPTY", timeout=30)
        return self._client

    def embed_query(self, text: str) -> list[float]:
        try:
            resp = self._ensure_client().embeddings.create(model=self._config.model, input=text)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"embedding 调用失败: {exc}") from exc
        return list(resp.data[0].embedding)

    def probe(self) -> int:
        """自检：返回向量维度。"""
        return len(self.embed_query("ping"))
