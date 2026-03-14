"""
本地节点配置文件。

使用方式：
    cp node_client/config.example.py node_client/config.py
    # 编辑 config.py 填写真实配置
"""

# 服务器 WebSocket 地址
SERVER_URL = "ws://your-server-ip:8765"

# 节点唯一 ID（与服务器 config.py 中 NODE_TOKENS 的键一致）
NODE_ID = "home-pc"

# 认证令牌（与服务器 config.py 中 NODE_TOKENS[NODE_ID] 一致）
TOKEN = "your-token-here"

# 节点显示名称（可选）
DISPLAY_NAME = "家里电脑"
