"""NapCat / QQ 操作工具集。

通过 NapCat channel 的 _call_action 方法调用 OneBot v11 API。
工具列表：
- napcat_get_group_list    获取已加入的群列表
- napcat_get_group_members 获取群成员列表
- napcat_get_friend_list   获取好友列表
- napcat_get_bot_info      获取机器人自身信息
- napcat_send_poke         戳一戳（私聊或群内）
- napcat_delete_msg        撤回消息
- napcat_friend_request    处理好友请求（同意/拒绝）
- napcat_group_request     处理群邀请（同意/拒绝）
- napcat_leave_group       退出/解散群
- napcat_get_stranger_info     获取陌生人信息（昵称、性别、年龄等）
- napcat_get_group_member_info 获取单个群成员详情
- napcat_send_voice        发语音消息（TTS + 直接发送，一步完成）
"""

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Awaitable

from auraeve.agent.tools.base import Tool


class _NapCatBase(Tool):
    """NapCat 工具基类，持有 call_action 回调。"""

    def __init__(self, call_action: Callable[[str, dict], Awaitable[Any]]):
        self._call = call_action

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}


# ─────────────────────────────────────────────────────────────────────────────


class NapCatGetGroupListTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_get_group_list"

    @property
    def description(self) -> str:
        return "获取机器人已加入的所有 QQ 群列表，返回群号、群名、成员数等信息。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> str:
        result = await self._call("get_group_list", {})
        if not result:
            return "获取群列表失败或暂未加入任何群。"
        groups = result if isinstance(result, list) else []
        lines = [f"共 {len(groups)} 个群："]
        for g in groups:
            lines.append(f"- {g.get('group_name', '未知')}（{g.get('group_id')}）成员 {g.get('member_count', '?')} 人")
        return "\n".join(lines)


class NapCatGetGroupMembersTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_get_group_members"

    @property
    def description(self) -> str:
        return "获取指定 QQ 群的成员列表，返回成员 QQ、昵称、群昵称、角色等。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "群号"},
            },
            "required": ["group_id"],
        }

    async def execute(self, group_id: str, **kwargs) -> str:
        result = await self._call("get_group_member_list", {"group_id": int(group_id)})
        if not result:
            return f"获取群 {group_id} 成员失败。"
        members = result if isinstance(result, list) else []
        lines = [f"群 {group_id} 共 {len(members)} 名成员："]
        for m in members:
            role = {"owner": "群主", "admin": "管理员", "member": "成员"}.get(m.get("role", ""), "成员")
            name = m.get("card") or m.get("nickname", "未知")
            lines.append(f"- {name}（{m.get('user_id')}）{role}")
        return "\n".join(lines)


class NapCatGetFriendListTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_get_friend_list"

    @property
    def description(self) -> str:
        return "获取机器人的 QQ 好友列表，返回 QQ 号、昵称、备注等。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> str:
        result = await self._call("get_friend_list", {})
        if not result:
            return "获取好友列表失败或暂无好友。"
        friends = result if isinstance(result, list) else []
        lines = [f"共 {len(friends)} 位好友："]
        for f in friends:
            remark = f.get("remark", "")
            name = remark or f.get("nickname", "未知")
            lines.append(f"- {name}（{f.get('user_id')}）")
        return "\n".join(lines)


class NapCatGetBotInfoTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_get_bot_info"

    @property
    def description(self) -> str:
        return "获取机器人自身的 QQ 号、昵称等基本信息。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> str:
        result = await self._call("get_login_info", {})
        if not result:
            return "获取机器人信息失败。"
        return f"QQ：{result.get('user_id')}，昵称：{result.get('nickname')}"


class NapCatSendPokeTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_send_poke"

    @property
    def description(self) -> str:
        return "戳一戳某人（私聊或群内）。私聊传 user_id，群内同时传 group_id。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "目标 QQ 号"},
                "group_id": {"type": "string", "description": "群号（群内戳时必填）"},
            },
            "required": ["user_id"],
        }

    async def execute(self, user_id: str, group_id: str = "", **kwargs) -> str:
        params: dict = {"user_id": int(user_id)}
        if group_id:
            params["group_id"] = int(group_id)
        await self._call("send_poke", params)
        return f"已戳 {user_id}。"


class NapCatDeleteMsgTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_delete_msg"

    @property
    def description(self) -> str:
        return "撤回一条消息（需要 message_id，通常来自收到消息的 metadata）。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "要撤回的消息 ID"},
            },
            "required": ["message_id"],
        }

    async def execute(self, message_id: str, **kwargs) -> str:
        await self._call("delete_msg", {"message_id": int(message_id)})
        return f"消息 {message_id} 已撤回。"


class NapCatFriendRequestTool(_NapCatBase):
    def __init__(self, call_action: Callable[[str, dict], Awaitable[Any]], friend_flags: dict[str, str]):
        super().__init__(call_action)
        self._friend_flags = friend_flags

    @property
    def name(self) -> str:
        return "napcat_friend_request"

    @property
    def description(self) -> str:
        return "处理好友申请，同意或拒绝。传入申请人的 QQ 号即可，无需手动填写 flag。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "申请人的 QQ 号"},
                "approve": {"type": "boolean", "description": "true 同意，false 拒绝"},
                "remark": {"type": "string", "description": "同意时设置的备注名（可选）"},
            },
            "required": ["user_id", "approve"],
        }

    async def execute(self, user_id: str, approve: bool, remark: str = "", **kwargs) -> str:
        flag = self._friend_flags.get(str(user_id))
        if not flag:
            return f"未找到 QQ {user_id} 的好友申请记录，可能已过期或不存在。"
        params: dict = {"flag": flag, "approve": approve}
        if remark:
            params["remark"] = remark
        await self._call("set_friend_add_request", params)
        self._friend_flags.pop(str(user_id), None)
        return f"好友请求已{'同意' if approve else '拒绝'}。"


class NapCatGroupRequestTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_group_request"

    @property
    def description(self) -> str:
        return "处理加群邀请，同意或拒绝。flag 和 sub_type 来自群邀请事件的 metadata。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "flag": {"type": "string", "description": "群请求的 flag（来自请求事件）"},
                "sub_type": {"type": "string", "description": "add 或 invite"},
                "approve": {"type": "boolean", "description": "true 同意，false 拒绝"},
                "reason": {"type": "string", "description": "拒绝时的理由（可选）"},
            },
            "required": ["flag", "sub_type", "approve"],
        }

    async def execute(self, flag: str, sub_type: str, approve: bool, reason: str = "", **kwargs) -> str:
        params: dict = {"flag": flag, "sub_type": sub_type, "approve": approve}
        if reason:
            params["reason"] = reason
        await self._call("set_group_add_request", params)
        return f"群请求已{'同意' if approve else '拒绝'}。"


class NapCatLeaveGroupTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_leave_group"

    @property
    def description(self) -> str:
        return "退出指定 QQ 群。is_dismiss 为 true 时解散群（仅群主可用），默认为 false（普通退群）。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "要退出的群号"},
                "is_dismiss": {"type": "boolean", "description": "是否解散群（群主专用，默认 false）"},
            },
            "required": ["group_id"],
        }

    async def execute(self, group_id: str, is_dismiss: bool = False, **kwargs) -> str:
        await self._call("set_group_leave", {"group_id": int(group_id), "is_dismiss": is_dismiss})
        action = "解散" if is_dismiss else "退出"
        return f"已{action}群 {group_id}。"


class NapCatGetStrangerInfoTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_get_stranger_info"

    @property
    def description(self) -> str:
        return "获取任意 QQ 用户的基本信息（昵称、性别、年龄、所在地等），不需要是好友。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "目标 QQ 号"},
            },
            "required": ["user_id"],
        }

    async def execute(self, user_id: str, **kwargs) -> str:
        result = await self._call("get_stranger_info", {"user_id": int(user_id)})
        if not result:
            return f"获取用户 {user_id} 信息失败。"
        sex_map = {"male": "男", "female": "女", "unknown": "未知"}
        sex = sex_map.get(result.get("sex", "unknown"), "未知")
        age = result.get("age", "?")
        return (
            f"QQ：{result.get('user_id')}\n"
            f"昵称：{result.get('nickname', '未知')}\n"
            f"性别：{sex}，年龄：{age}\n"
            f"签名：{result.get('sign', '（无）')}"
        )


class NapCatGetGroupMemberInfoTool(_NapCatBase):
    @property
    def name(self) -> str:
        return "napcat_get_group_member_info"

    @property
    def description(self) -> str:
        return "获取指定群内某位成员的详细信息，包括入群时间、最后发言时间、头衔、禁言状态等。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "群号"},
                "user_id": {"type": "string", "description": "成员 QQ 号"},
            },
            "required": ["group_id", "user_id"],
        }

    async def execute(self, group_id: str, user_id: str, **kwargs) -> str:
        result = await self._call("get_group_member_info", {
            "group_id": int(group_id),
            "user_id": int(user_id),
        })
        if not result:
            return f"获取群 {group_id} 成员 {user_id} 信息失败。"
        role_map = {"owner": "群主", "admin": "管理员", "member": "成员"}
        role = role_map.get(result.get("role", ""), "成员")
        name = result.get("card") or result.get("nickname", "未知")
        import datetime
        def ts(t):
            return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d") if t else "未知"
        mute_until = result.get("shut_up_timestamp", 0)
        mute_str = f"禁言至 {ts(mute_until)}" if mute_until and mute_until > 0 else "未禁言"
        return (
            f"QQ：{result.get('user_id')}，昵称：{result.get('nickname', '未知')}\n"
            f"群昵称：{result.get('card', '（无）')}，角色：{role}\n"
            f"入群：{ts(result.get('join_time', 0))}，最后发言：{ts(result.get('last_sent_time', 0))}\n"
            f"头衔：{result.get('title', '（无）')}，{mute_str}"
        )


# ─────────────────────────────────────────────────────────────────────────────


class NapCatSendVoiceTool(Tool):
    """
    发语音消息（TTS + 直接发送，一步完成）。

    使用 edge-tts 生成语音，以 base64 内嵌方式发送 record 消息段。
    兼容 NapCat 部署在 Docker / 远程服务器的情况（无需共享文件系统）。
    发送成功后返回空字符串，loop.py 会自动抑制额外的文字回复。
    """

    def __init__(self, call_action: Callable[[str, dict], Awaitable[Any]], media_dir: Path):
        self._call = call_action
        self._media_dir = media_dir

    @property
    def name(self) -> str:
        return "napcat_send_voice"

    @property
    def description(self) -> str:
        return (
            "将文字转为语音并直接发送给指定 QQ 用户或群（TTS + 发送一步完成）。"
            "发送成功后返回空字符串——任务已完成，**不要再说任何额外的话**。\n"
            "chat_id 格式：private:QQ号（私聊）或 group:群号（群聊）。\n"
            "当用户要求用语音回复时，使用此工具，然后直接返回空字符串。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要转为语音的文字内容",
                },
                "chat_id": {
                    "type": "string",
                    "description": "发送目标，格式：private:QQ号（私聊）或 group:群号（群聊）",
                },
                "voice": {
                    "type": "string",
                    "description": (
                        "声音名称，默认 zh-CN-XiaoxiaoNeural（甜美女声）。"
                        "其他可选：zh-CN-YunxiNeural（男声）、zh-CN-XiaohanNeural（温柔女声）"
                    ),
                },
            },
            "required": ["text", "chat_id"],
        }

    async def execute(
        self, text: str, chat_id: str, voice: str = "zh-CN-XiaoxiaoNeural", **kwargs
    ) -> str:
        try:
            import edge_tts
        except ImportError:
            return "错误：edge-tts 未安装，请运行 pip install edge-tts"

        import base64

        self._media_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._media_dir / f"tts_{uuid.uuid4().hex[:8]}.mp3"

        # 去除 emoji（Unicode 表情符号），TTS 引擎无法朗读
        import re
        text = re.sub(r'[\U00010000-\U0010FFFF]|'           # 扩展区表情（🎉🔥等）
                      r'[\u2600-\u27BF]|'                    # 杂项符号（☀✨等）
                      r'[\uFE00-\uFE0F]|'                    # 变体选择符
                      r'[\u200D\u200B\u200C\uFEFF]',         # 零宽字符
                      '', text).strip()
        if not text:
            return ""  # 纯 emoji 消息，跳过 TTS

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))
        except Exception as e:
            return f"TTS 生成失败：{e}"

        try:
            with open(output_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
        except OSError as e:
            return f"读取音频文件失败：{e}"

        record_segment = [{"type": "record", "data": {"file": f"base64://{b64}"}}]

        try:
            if chat_id.startswith("group:"):
                group_id = chat_id[6:]
                await self._call("send_group_msg", {
                    "group_id": int(group_id),
                    "message": record_segment,
                })
            else:
                user_id = chat_id[8:] if chat_id.startswith("private:") else chat_id
                await self._call("send_private_msg", {
                    "user_id": int(user_id),
                    "message": record_segment,
                })
        finally:
            import os
            try:
                os.unlink(output_path)
            except OSError:
                pass

        return ""  # 空字符串 → loop.py 不发送额外文字


# ─────────────────────────────────────────────────────────────────────────────

def create_napcat_tools(
    call_action: Callable[[str, dict], Awaitable[Any]],
    friend_flags: dict[str, str],
    media_dir: Path | None = None,
) -> list[Tool]:
    """创建所有 NapCat 工具，传入 call_action 回调和 media_dir（语音输出目录）。"""
    tools: list[Tool] = [
        NapCatGetGroupListTool(call_action),
        NapCatGetGroupMembersTool(call_action),
        NapCatGetFriendListTool(call_action),
        NapCatGetBotInfoTool(call_action),
        NapCatSendPokeTool(call_action),
        NapCatDeleteMsgTool(call_action),
        NapCatFriendRequestTool(call_action, friend_flags),
        NapCatGroupRequestTool(call_action),
        NapCatLeaveGroupTool(call_action),
        NapCatGetStrangerInfoTool(call_action),
        NapCatGetGroupMemberInfoTool(call_action),
    ]
    if media_dir is not None:
        tools.append(NapCatSendVoiceTool(call_action, media_dir))
    return tools
