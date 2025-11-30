"""
聊天配置模块
包含文字聊天频道管理配置
"""

from dataclasses import dataclass, field


# ============================================================================
# 文字聊天管理配置
# ============================================================================

@dataclass
class ChatChannelConfig:
    """文字聊天频道配置"""
    channel_id: str
    channel_name: str
    channel_type: str = "global"  # global/team/whisper/system
    max_message_length: int = 200
    allow_emotes: bool = True
    filter_profanity: bool = True
    message_history_limit: int = 100
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_type": self.channel_type,
            "max_message_length": self.max_message_length,
            "allow_emotes": self.allow_emotes,
            "filter_profanity": self.filter_profanity,
            "message_history_limit": self.message_history_limit,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'ChatChannelConfig':
        return ChatChannelConfig(
            channel_id=data["channel_id"],
            channel_name=data["channel_name"],
            channel_type=data.get("channel_type", "global"),
            max_message_length=data.get("max_message_length", 200),
            allow_emotes=data.get("allow_emotes", True),
            filter_profanity=data.get("filter_profanity", True),
            message_history_limit=data.get("message_history_limit", 100),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 聊天配置测试 ===\n")
    
    # 测试聊天频道
    print("1. 聊天频道配置:")
    channel = ChatChannelConfig(
        channel_id="channel_001",
        channel_name="全局频道",
        channel_type="global",
        max_message_length=200,
        allow_emotes=True,
        filter_profanity=True
    )
    print(f"   频道名: {channel.channel_name}")
    print(f"   频道类型: {channel.channel_type}")
    print(f"   最大消息长度: {channel.max_message_length}")
    print(f"   允许表情: {channel.allow_emotes}")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    data = channel.serialize()
    restored = ChatChannelConfig.deserialize(data)
    print(f"   序列化成功: {channel.channel_name == restored.channel_name}")
    
    print("\n✅ 聊天配置测试完成")

