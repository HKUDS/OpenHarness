"""insightagent CLI：serve / check / ask / plugins。"""

from __future__ import annotations

import asyncio

import typer

from insightagent.config import load_config
from insightagent.plugin_support import (
    PluginResolutionError,
    build_deps,
    discover_plugins,
    resolve_plugins,
)

app = typer.Typer(add_completion=False, help="企业数据智能体：报表检索 + 数据查询分析（SSE 服务）")
plugins_app = typer.Typer(add_completion=False, help="能力插件管理")
app.add_typer(plugins_app, name="plugins")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="监听地址（默认取配置 server.host）"),
    port: int | None = typer.Option(None, help="监听端口（默认取配置 server.port，默认 8760）"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径（默认 ~/.insightagent/config.yaml）"),
) -> None:
    """启动 HTTP + SSE 服务。"""
    from insightagent.server import serve as run_server

    cfg = load_config(config) if config else load_config()
    typer.echo(f"配置: {cfg.config_path}")
    typer.echo(f"监听: {host or cfg.server.host}:{port or cfg.server.port}")
    run_server(cfg, host=host, port=port)


@app.command()
def check(
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """逐项自检：数据库/Milvus/embedding/LLM profile/能力插件。"""
    cfg = load_config(config) if config else load_config()
    typer.echo(f"配置文件: {cfg.config_path}")
    all_ok = True

    for db in cfg.databases:
        try:
            deps = build_deps(cfg)
            asyncio.run(deps.query_engine.ping(db.id))
            typer.secho(f"[ready] 数据库 {db.id} ({db.type}) 连通，只读权限可用", fg=typer.colors.GREEN)
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            typer.secho(f"[blocked] 数据库 {db.id} ({db.type}): {exc}", fg=typer.colors.RED)

    if cfg.milvus is not None:
        try:
            from pymilvus import MilvusClient

            client = MilvusClient(uri=cfg.milvus.uri)
            collections = client.list_collections()
            if cfg.milvus.collection not in collections:
                raise RuntimeError(f"collection {cfg.milvus.collection!r} 不存在，可用: {collections}")
            typer.secho(f"[ready] Milvus {cfg.milvus.uri} 连通，collection {cfg.milvus.collection} 存在", fg=typer.colors.GREEN)
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            typer.secho(f"[blocked] Milvus: {exc}", fg=typer.colors.RED)

    if cfg.embedding is not None:
        try:
            deps = build_deps(cfg)
            assert deps.embeddings is not None
            dim = deps.embeddings.probe()
            typer.secho(f"[ready] embedding {cfg.embedding.model} 可用，维度 {dim}", fg=typer.colors.GREEN)
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            typer.secho(f"[blocked] embedding: {exc}", fg=typer.colors.RED)

    try:
        from openharness.ui.runtime import build_runtime, close_runtime

        settings_kwargs = {}
        if cfg.agent.profile:
            settings_kwargs["active_profile"] = cfg.agent.profile
        if cfg.agent.model:
            settings_kwargs["model"] = cfg.agent.model

        async def _probe():
            bundle = await build_runtime(**settings_kwargs)
            await close_runtime(bundle)

        asyncio.run(_probe())
        typer.secho("[ready] OpenHarness LLM profile 可解析", fg=typer.colors.GREEN)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        all_ok = False
        message = str(exc).strip() or f"{exc.__class__.__name__}（详见上方错误说明）"
        typer.secho(f"[blocked] OpenHarness LLM profile: {message}", fg=typer.colors.RED)

    for plugin in discover_plugins(cfg):
        state = "ready" if plugin.ready else f"blocked ({plugin.reason})"
        color = typer.colors.GREEN if plugin.ready else typer.colors.YELLOW
        enabled = "启用" if plugin.name in cfg.agent.default_plugins else "停用"
        typer.secho(f"[plugin] {plugin.name} [{enabled}] {plugin.description} -> {state}", fg=color)

    typer.echo("")
    if all_ok:
        typer.secho("全部自检通过，可以 insightagent serve 启动服务。", fg=typer.colors.GREEN)
    else:
        typer.secho("存在 blocked 项，请修复配置后重试（blocked 的能力插件会自动降级为不可选）。", fg=typer.colors.YELLOW)


@plugins_app.command("list")
def plugins_list(
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """列出能力插件及启停/自检状态。"""
    cfg = load_config(config) if config else load_config()
    discovered = discover_plugins(cfg)
    if not discovered:
        typer.echo(f"未发现能力插件（plugin_root: {cfg.plugin_root_path()}）")
        return
    for plugin in discovered:
        enabled = "启用" if plugin.name in cfg.agent.default_plugins else "停用"
        state = "ready" if plugin.ready else f"blocked: {plugin.reason}"
        typer.echo(f"{plugin.name:<16} [{enabled}] {plugin.description} -> {state}")


@app.command()
def ask(
    question: str = typer.Argument(..., help="问题，如 \"上个月销量前5的客户\""),
    plugins: str | None = typer.Option(None, "--plugins", help="逗号分隔插件名，默认自动选择"),
    no_session: bool = typer.Option(False, "--no-session", help="ephemeral 模式，不落盘"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """终端直测：流式打印事件。"""
    from insightagent.session_pool import SessionPool

    cfg = load_config(config) if config else load_config()
    pool = SessionPool(cfg)
    requested = [name.strip() for name in plugins.split(",") if name.strip()] if plugins else None
    try:
        loaded, skipped = resolve_plugins(requested, cfg, deps=pool.deps)
    except PluginResolutionError as exc:
        typer.secho(f"插件解析失败: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc
    if not loaded:
        typer.secho("无可用能力插件：" + str(skipped), fg=typer.colors.RED)
        raise typer.Exit(code=2)
    for item in skipped:
        typer.secho(f"[skipped] {item['plugin']}: {item['reason']}", fg=typer.colors.YELLOW)

    session_id = None if no_session else "cli-ask"

    async def _run() -> None:
        streamed_chars = 0
        thought_chars = 0
        try:
            async for payload in pool.stream_chat(message=question, session_id=session_id, loaded=loaded):
                kind = payload.get("type")
                if kind == "thinking_delta":
                    thought_chars += len(payload.get("text", ""))
                    typer.secho(payload.get("text", ""), nl=False, fg=typer.colors.BLACK)
                elif kind == "assistant_delta":
                    if streamed_chars == 0 and thought_chars > 0:
                        typer.echo("\n")
                    streamed_chars += len(payload.get("text", ""))
                    typer.echo(payload.get("text", ""), nl=False)
                elif kind == "turn_complete":
                    text = payload.get("text") or ""
                    # delta 已流式打印过完整文本则不重复；否则补打（异常兜底路径）
                    if text and len(text) > streamed_chars:
                        typer.echo("\n" + text)
                    else:
                        typer.echo("")
                elif kind == "tool_started":
                    typer.secho(f"\n[tool] {payload.get('tool_name')} {payload.get('tool_input')}", fg=typer.colors.CYAN)
                elif kind == "tool_completed":
                    is_error = payload.get("is_error")
                    preview = str(payload.get("output", ""))[:200]
                    color = typer.colors.RED if is_error else typer.colors.BLUE
                    typer.secho(f"[tool→] {preview}", fg=color)
                elif kind == "error":
                    typer.secho(f"[error] {payload.get('message')}", fg=typer.colors.RED)
        finally:
            await pool.close_all()

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
