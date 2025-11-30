"""
音频与音乐配置模块
包含背景音乐管理配置
"""

from dataclasses import dataclass, field


# ============================================================================
# 背景音乐管理配置
# ============================================================================

@dataclass
class BackgroundMusicConfig:
    """背景音乐配置"""
    music_id: str
    music_name: str
    audio_file: str = ""
    volume: float = 1.0
    loop: bool = True
    fade_in_duration: float = 0.0
    fade_out_duration: float = 0.0
    trigger_condition: str = ""  # 触发条件
    description: str = ""
    metadata: dict = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "music_id": self.music_id,
            "music_name": self.music_name,
            "audio_file": self.audio_file,
            "volume": self.volume,
            "loop": self.loop,
            "fade_in_duration": self.fade_in_duration,
            "fade_out_duration": self.fade_out_duration,
            "trigger_condition": self.trigger_condition,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'BackgroundMusicConfig':
        return BackgroundMusicConfig(
            music_id=data["music_id"],
            music_name=data["music_name"],
            audio_file=data.get("audio_file", ""),
            volume=data.get("volume", 1.0),
            loop=data.get("loop", True),
            fade_in_duration=data.get("fade_in_duration", 0.0),
            fade_out_duration=data.get("fade_out_duration", 0.0),
            trigger_condition=data.get("trigger_condition", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


if __name__ == "__main__":
    print("=== 音频与音乐配置测试 ===\n")
    
    # 测试背景音乐
    print("1. 背景音乐配置:")
    music = BackgroundMusicConfig(
        music_id="bgm_001",
        music_name="主题音乐",
        audio_file="theme_music.mp3",
        volume=0.8,
        loop=True,
        fade_in_duration=2.0,
        fade_out_duration=1.5
    )
    print(f"   音乐名: {music.music_name}")
    print(f"   音量: {music.volume}")
    print(f"   循环: {music.loop}")
    print(f"   淡入时长: {music.fade_in_duration}秒")
    
    # 测试序列化
    print("\n2. 序列化测试:")
    music_data = music.serialize()
    music_restored = BackgroundMusicConfig.deserialize(music_data)
    print(f"   序列化成功: {music.music_name == music_restored.music_name}")
    
    print("\n✅ 音频与音乐配置测试完成")

