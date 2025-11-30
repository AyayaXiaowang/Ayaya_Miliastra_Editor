"""游戏状态管理 - 变量、实体、事件系统"""

from typing import Any, Dict, List, Optional, Callable, Tuple
import random


class MockEntity:
    """Mock实体对象"""
    
    def __init__(self, entity_id: str, name: str = "未命名实体"):
        self.entity_id = entity_id
        self.name = name
        self.position = [0.0, 0.0, 0.0]
        self.rotation = [0.0, 0.0, 0.0]
        self.variables = {}  # 自定义变量
        
    def __repr__(self):
        return f"<Entity:{self.name}>"


class GameRuntime:
    """游戏运行时环境"""
    
    def __init__(self):
        # 变量系统
        self.custom_variables = {}  # 自定义变量 {entity_id: {var_name: value}}
        self.graph_variables = {}   # 节点图变量 {var_name: value}
        self.local_variables = {}   # 局部变量 {var_id: value}
        
        # 实体系统
        self.entities = {}  # {entity_id: MockEntity}
        self.entity_counter = 0
        
        # 事件系统
        self.event_handlers: Dict[str, List[Tuple[Callable, Optional[str]]]] = {}
        
        # 节点图挂载系统
        self.attached_graphs = {}  # {entity_id: [graph_instances]}
        
        # Mock系统状态
        self.music_volume = 100
        self.current_music = None
        self.timers = {}
        
        # 创建一些默认实体
        self._create_default_entities()
    
    def _create_default_entities(self):
        """创建默认实体用于测试"""
        self.create_mock_entity("自身实体")
        self.create_mock_entity("玩家1")
        self.create_mock_entity("敌人1")

    def _update_variable_store(
        self,
        storage: Dict[str, Any],
        key: str,
        value: Any,
        log_prefix: str,
        log_target: str,
        trigger_event: bool = False,
        event_var_name: Optional[str] = None,
    ):
        """统一的变量写入辅助，负责存值、日志与事件通知。"""
        storage[key] = value
        print(f"[{log_prefix}] {log_target} = {value}")
        if trigger_event and event_var_name:
            self.trigger_event(f"变量变化_{event_var_name}", value=value)
    
    # ========== 变量系统 ==========
    
    def set_custom_variable(self, entity, var_name: str, value: Any, trigger_event: bool = False):
        """设置自定义变量"""
        entity_id = self._get_entity_id(entity)
        entity_variables = self.custom_variables.setdefault(entity_id, {})
        entity_label = entity.name if isinstance(entity, MockEntity) else str(entity)
        log_target = f"{entity_label}.{var_name}"
        self._update_variable_store(
            entity_variables,
            var_name,
            value,
            "自定义变量",
            log_target,
            trigger_event,
            var_name,
        )
    
    def get_custom_variable(self, entity, var_name: str, default=None):
        """获取自定义变量"""
        entity_id = self._get_entity_id(entity)
        return self.custom_variables.get(entity_id, {}).get(var_name, default)
    
    def set_graph_variable(self, var_name: str, value: Any, trigger_event: bool = False):
        """设置节点图变量"""
        self._update_variable_store(
            self.graph_variables,
            var_name,
            value,
            "节点图变量",
            var_name,
            trigger_event,
            var_name,
        )
    
    def get_graph_variable(self, var_name: str, default=None):
        """获取节点图变量"""
        return self.graph_variables.get(var_name, default)
    
    def create_local_variable(self, initial_value=None):
        """创建局部变量"""
        var_id = f"local_{len(self.local_variables)}"
        self.local_variables[var_id] = initial_value
        return var_id, initial_value
    
    def set_local_variable(self, var_id: str, value: Any):
        """设置局部变量"""
        self._update_variable_store(
            self.local_variables,
            var_id,
            value,
            "局部变量",
            var_id,
        )
    
    def get_local_variable(self, var_id: str, default=None):
        """获取局部变量"""
        return self.local_variables.get(var_id, default)
    
    # ========== 实体系统 ==========
    
    def _get_entity_id(self, entity) -> str:
        """获取实体ID"""
        if isinstance(entity, MockEntity):
            return entity.entity_id
        elif isinstance(entity, str):
            return entity
        else:
            return str(entity)
    
    def create_mock_entity(self, name: str = "新实体") -> MockEntity:
        """创建Mock实体"""
        self.entity_counter += 1
        entity_id = f"entity_{self.entity_counter}"
        entity = MockEntity(entity_id, name)
        self.entities[entity_id] = entity
        print(f"[创建实体] {name} (ID:{entity_id})")
        return entity
    
    def destroy_entity(self, entity):
        """销毁实体"""
        entity_id = self._get_entity_id(entity)
        if entity_id in self.entities:
            entity_name = self.entities[entity_id].name
            del self.entities[entity_id]
            print(f"[销毁实体] {entity_name}")
            self._cleanup_entity_state(entity_id)
        else:
            print(f"[警告] 尝试销毁不存在的实体: {entity_id}")

    def _cleanup_entity_state(self, entity_id: str):
        """销毁实体后联动清理所有挂靠状态（变量、定时器、事件、节点图）。"""
        self.custom_variables.pop(entity_id, None)
        self.attached_graphs.pop(entity_id, None)
        timer_prefix = f"{entity_id}_"
        timers_to_remove = [key for key in self.timers.keys() if key.startswith(timer_prefix)]
        for timer_key in timers_to_remove:
            del self.timers[timer_key]
        for event_name in list(self.event_handlers.keys()):
            remaining_handlers = [
                (handler, owner_id)
                for handler, owner_id in self.event_handlers[event_name]
                if owner_id != entity_id
            ]
            if remaining_handlers:
                self.event_handlers[event_name] = remaining_handlers
            else:
                del self.event_handlers[event_name]
    
    def get_entity(self, entity_id: str) -> Optional[MockEntity]:
        """获取实体"""
        return self.entities.get(entity_id)
    
    def get_all_entities(self) -> List[MockEntity]:
        """获取所有实体"""
        return list(self.entities.values())
    
    # ========== 事件系统 ==========
    
    def trigger_event(self, event_name: str, **kwargs):
        """触发事件
        
        Args:
            event_name: 事件名称
            **kwargs: 事件参数
        """
        print(f"[事件触发] {event_name}")
        
        # 调用注册的处理器
        if event_name in self.event_handlers:
            for handler, _ in self.event_handlers[event_name]:
                handler(**kwargs)
    
    def register_event_handler(self, event_name: str, handler: Callable, owner=None):
        """注册事件处理器
        
        Args:
            event_name: 事件名称
            handler: 处理函数
            owner: 挂载的实体（可选，用于实体销毁时自动清理）
        """
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        owner_id = self._get_entity_id(owner) if owner is not None else None
        self.event_handlers[event_name].append((handler, owner_id))
    
    def emit_signal(
        self,
        signal_id: str,
        params: Optional[Dict[str, Any]] = None,
        target_entity=None,
    ) -> None:
        """发送信号（基于事件系统的轻量封装）。

        - 事件名使用 signal_id 作为唯一键；
        - 事件参数规范：
          * 事件源实体: 实体
          * 事件源GUID: GUID
          * 信号来源实体: 实体（通常与事件源实体相同）
          * 其余键值对来自 params（视作信号参数）。
        """
        if params is None:
            params = {}

        source_entity = target_entity if target_entity is not None else self.create_mock_entity("信号来源实体")
        event_kwargs: Dict[str, Any] = {
            "事件源实体": source_entity,
            "事件源GUID": f"signal_{signal_id}",
            "信号来源实体": source_entity,
        }
        # 信号参数按原样并入事件上下文
        event_kwargs.update(params)

        self.trigger_event(signal_id, **event_kwargs)
    
    def attach_graph(self, graph_class, owner_entity):
        """虚拟挂载节点图到实体
        
        Args:
            graph_class: 节点图类
            owner_entity: 挂载的实体
            
        Returns:
            graph_instance: 节点图实例
        """
        print(f"[节点图挂载] {graph_class.__name__} → {owner_entity}")
        
        # 创建节点图实例
        graph_instance = graph_class(self, owner_entity)
        
        # 记录挂载关系
        if owner_entity.entity_id not in self.attached_graphs:
            self.attached_graphs[owner_entity.entity_id] = []
        
        self.attached_graphs[owner_entity.entity_id].append(graph_instance)
        
        # 注册事件处理器
        graph_instance.register_handlers()
        
        return graph_instance
    
    # ========== Mock系统 ==========
    
    def play_music(self, music_index: int, volume: int = 100):
        """播放音乐（Mock）"""
        self.current_music = music_index
        self.music_volume = volume
        print(f"[音乐] 播放音乐#{music_index}, 音量={volume}")
    
    def stop_music(self):
        """停止音乐（Mock）"""
        self.current_music = None
        print(f"[音乐] 停止播放")
    
    def play_sound(self, sound_index: int, volume: int = 100):
        """播放音效（Mock）"""
        print(f"[音效] 播放音效#{sound_index}, 音量={volume}")
    
    def play_effect(self, effect_id: str, entity, position=None):
        """播放特效（Mock）"""
        entity_name = entity.name if isinstance(entity, MockEntity) else str(entity)
        print(f"[特效] 在{entity_name}播放特效: {effect_id}")
    
    def start_timer(self, entity, timer_name: str, duration: float, is_loop: bool = False):
        """启动定时器（Mock）"""
        entity_id = self._get_entity_id(entity)
        timer_key = f"{entity_id}_{timer_name}"
        self.timers[timer_key] = {
            "duration": duration,
            "is_loop": is_loop,
            "remaining": duration
        }
        print(f"[定时器] 启动定时器'{timer_name}', 时长={duration}秒, 循环={is_loop}")
    
    def stop_timer(self, entity, timer_name: str):
        """停止定时器（Mock）"""
        entity_id = self._get_entity_id(entity)
        timer_key = f"{entity_id}_{timer_name}"
        if timer_key in self.timers:
            del self.timers[timer_key]
            print(f"[定时器] 停止定时器'{timer_name}'")
    
    def show_ui(self, ui_name: str, player_entity):
        """显示UI（Mock）"""
        print(f"[UI] 显示界面: {ui_name}")
    
    def hide_ui(self, ui_name: str, player_entity):
        """隐藏UI（Mock）"""
        print(f"[UI] 隐藏界面: {ui_name}")
    
    # ========== 工具方法 ==========
    
    def random_int(self, min_val: int, max_val: int) -> int:
        """获取随机整数"""
        return random.randint(min_val, max_val)
    
    def random_float(self, min_val: float, max_val: float) -> float:
        """获取随机浮点数"""
        return random.uniform(min_val, max_val)
    
    def log(self, message: str):
        """输出日志"""
        print(f"[日志] {message}")

