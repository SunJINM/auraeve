"""
本地节点启动入口。

用法：
    python -m node_client --server ws://your-server:8765 --node-id home-pc --token your-token

或在 node_client/config.py 中填写默认配置后直接运行：
    python -m node_client
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path


def _load_config() -> dict:
    """尝试加载 node_client/config.py，若不存在返回空字典。"""
    config_path = Path(__file__).parent / "config.py"
    if not config_path.exists():
        return {}
    import importlib.util
    spec = importlib.util.spec_from_file_location("node_config", config_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {
        "server_url": getattr(mod, "SERVER_URL", ""),
        "node_id": getattr(mod, "NODE_ID", ""),
        "token": getattr(mod, "TOKEN", ""),
        "display_name": getattr(mod, "DISPLAY_NAME", ""),
    }


async def main() -> None:
    from loguru import logger
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    # 先加载配置文件默认值
    file_cfg = _load_config()

    parser = argparse.ArgumentParser(description="auraeve 本地节点客户端")
    parser.add_argument("--server", default=file_cfg.get("server_url", ""),
                        help="服务器 WebSocket 地址，例如 ws://192.168.1.100:8765")
    parser.add_argument("--node-id", default=file_cfg.get("node_id", ""),
                        help="节点唯一 ID（与服务器配置中的 node_id 一致）")
    parser.add_argument("--token", default=file_cfg.get("token", ""),
                        help="认证令牌（与服务器配置中的 token 一致）")
    parser.add_argument("--name", default=file_cfg.get("display_name", ""),
                        help="节点显示名称（可选，默认使用 node-id）")
    args = parser.parse_args()

    if not args.server:
        parser.error("必须提供 --server 参数或在 node_client/config.py 中设置 SERVER_URL")
    if not args.node_id:
        parser.error("必须提供 --node-id 参数或在 node_client/config.py 中设置 NODE_ID")
    if not args.token:
        parser.error("必须提供 --token 参数或在 node_client/config.py 中设置 TOKEN")

    from node_client.client import NodeClient
    client = NodeClient(
        server_url=args.server,
        node_id=args.node_id,
        token=args.token,
        display_name=args.name or args.node_id,
    )

    loop = asyncio.get_running_loop()

    def _on_signal():
        logger.info("正在关闭节点客户端...")
        client.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass

    logger.info(f"节点 ID：{args.node_id}，显示名：{args.name or args.node_id}")
    await client.run()
    logger.info("节点客户端已停止。")


if __name__ == "__main__":
    asyncio.run(main())
