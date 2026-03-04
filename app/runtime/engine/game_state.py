"""游戏状态管理 - 变量、实体、事件系统"""

from typing import Any, Dict, List, Optional, Callable, Tuple
import random
import time
import copy

from app.runtime.engine.trace_logging import TraceRecorder


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
        self._timer_token_counter: int = 0

        # 在场玩家（本地测试：可配置人数，用于“等待其他玩家/投票门槛”等逻辑）
        self.present_player_count: int = 1
        self.present_players: List[MockEntity] = []

        # UI 模拟状态（用于本地测试/教学，不代表真实游戏 UI）
        self.ui_patches: List[Dict[str, Any]] = []
        self.ui_current_layout_by_player: Dict[str, int] = {}
        self.ui_widget_state_by_player: Dict[str, Dict[int, str]] = {}
        self.ui_active_groups_by_player: Dict[str, set[int]] = {}
        self.ui_binding_root_entity_id: str = ""
        self.ui_lv_defaults: Dict[str, Any] = {}

        # 运行期事件追踪
        self.trace_recorder = TraceRecorder()
        
        # 创建一些默认实体
        self._create_default_entities()
        self.set_present_player_count(self.present_player_count)

    def record_trace_event(self, kind: str, message: str, **details: Any) -> None:
        """将运行时事件写入 TraceRecorder，便于统一的执行链路追踪。"""
        if self.trace_recorder is None:
            return
        self.trace_recorder.record(
            source="runtime",
            kind=kind,
            message=message,
            stack=[],
            **details,
        )
    
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
        self.record_trace_event(
            kind="variable",
            message=f"{log_prefix}:{log_target}",
            value=value,
            trigger_event=trigger_event,
        )
        if trigger_event and event_var_name:
            self.trigger_event(f"变量变化_{event_var_name}", value=value)
    
    # ========== 变量系统 ==========
    
    def set_custom_variable(self, entity, var_name: str, value: Any, trigger_event: bool = False):
        """设置自定义变量"""
        entity_id = self._get_entity_id(entity)
        entity_variables = self.custom_variables.setdefault(entity_id, {})
        entity_label = entity.name if isinstance(entity, MockEntity) else str(entity)
        log_target = f"{entity_label}.{var_name}"
        # 约定：UI 绑定（lv.*）的根实体通常是“关卡实体”，其自定义变量以 `UI*` 开头。
        # 本地测试用该字段快速定位 UI 绑定数据来源实体。
        if str(var_name or "").startswith("UI"):
            self.ui_binding_root_entity_id = str(entity_id)
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
        store = self.custom_variables.get(entity_id, {})
        if isinstance(store, dict) and (var_name in store):
            return store.get(var_name, default)

        # 本地测试：当 UI HTML 提供了 lv.* 默认值时，允许在首次读取时自动补齐到实体自定义变量中，
        # 以避免节点图侧“对字典写 key”在变量不存在时变成 no-op（真实游戏中这些 UI 变量通常是预置的）。
        if isinstance(self.ui_lv_defaults, dict) and (var_name in self.ui_lv_defaults):
            entity_variables = self.custom_variables.setdefault(entity_id, {})
            value = copy.deepcopy(self.ui_lv_defaults.get(var_name))
            entity_variables[var_name] = value
            if str(var_name or "").startswith("UI"):
                self.ui_binding_root_entity_id = str(entity_id)
            return value

        return default
    
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

    def find_entity_by_name(self, name: str) -> Optional[MockEntity]:
        """按名称查找实体（离线模拟：用于复用玩家/owner 等固定命名实体）。"""
        desired = str(name or "").strip()
        if not desired:
            return None
        for ent in self.entities.values():
            if getattr(ent, "name", None) == desired:
                return ent
        return None

    def set_present_player_count(self, count: int) -> None:
        """设置在场玩家数量，并确保 `玩家1..玩家N` 实体存在且稳定复用。"""
        value = int(count)
        if value <= 0:
            value = 1
        self.present_player_count = int(value)
        players: List[MockEntity] = []
        for i in range(1, int(value) + 1):
            name = f"玩家{i}"
            ent = self.find_entity_by_name(name)
            if ent is None:
                ent = self.create_mock_entity(name)
            players.append(ent)
        self.present_players = players

    def get_present_player_entities(self) -> List[MockEntity]:
        """获取在场玩家实体列表（保证至少返回 1 个玩家）。"""
        if isinstance(self.present_players, list) and self.present_players:
            return list(self.present_players)
        self.set_present_player_count(self.present_player_count or 1)
        return list(self.present_players)

    def set_ui_lv_defaults(self, defaults: Dict[str, Any]) -> None:
        """设置 UI HTML 的 lv.* 默认值映射（key 为去掉 'lv.' 前缀后的变量名）。"""
        if not isinstance(defaults, dict):
            raise TypeError("defaults 必须是 dict")
        self.ui_lv_defaults = dict(defaults)
    
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
    
    def get_entity(self, entity_id: str | int) -> Optional[MockEntity]:
        """获取实体"""
        # 兼容：部分节点图会以“数值 GUID”查询实体（离线环境下不存在真实 GUID->实体映射），
        # 这里为本地测试提供“按需创建”的最小可用语义：
        # - int GUID：以 str(guid) 作为实体ID创建并缓存
        # - 数字字符串：同上
        if isinstance(entity_id, int):
            key = str(int(entity_id))
            existing = self.entities.get(key)
            if existing is not None:
                return existing
            entity = MockEntity(key, name=f"GUID实体_{key}")
            self.entities[key] = entity
            return entity
        if isinstance(entity_id, str):
            key = entity_id
            existing = self.entities.get(key)
            if existing is not None:
                return existing
            if key.isdigit():
                entity = MockEntity(key, name=f"GUID实体_{key}")
                self.entities[key] = entity
                return entity
            return None
        return None
    
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
        self.record_trace_event(
            kind="event",
            message=event_name,
            payload=dict(kwargs),
        )
        
        # 调用注册的处理器
        handlers = self.event_handlers.get(event_name)
        if handlers:
            for handler, owner_id in handlers:
                owner_id_text = str(owner_id) if owner_id is not None else ""
                owner_name = ""
                if owner_id_text:
                    ent = self.entities.get(owner_id_text, None)
                    if ent is not None:
                        owner_name = str(getattr(ent, "name", "") or "")
                owner_label = owner_id_text if owner_id_text else "<global>"
                if owner_name:
                    owner_label = f"{owner_id_text}({owner_name})"

                graph_obj = getattr(handler, "__self__", None)
                graph_class = ""
                graph_name = ""
                if graph_obj is not None:
                    graph_class = str(getattr(getattr(graph_obj, "__class__", None), "__name__", "") or "")
                    doc = getattr(getattr(graph_obj, "__class__", None), "__doc__", None)
                    if isinstance(doc, str):
                        text = doc.strip()
                        prefix = "节点图类："
                        if text.startswith(prefix):
                            graph_name = text[len(prefix) :].strip()

                handler_name = str(getattr(handler, "__name__", "") or getattr(handler, "__qualname__", "") or "handler")
                graph_label = graph_name or graph_class
                graph_handler = f"{graph_label}.{handler_name}" if graph_label else handler_name

                src_ent = kwargs.get("事件源实体", None)
                src_id = str(self._get_entity_id(src_ent)) if src_ent is not None else ""
                src_name = str(getattr(src_ent, "name", "") or "") if isinstance(src_ent, MockEntity) else ""
                src_label = src_id
                if src_id and src_name:
                    src_label = f"{src_id}({src_name})"

                src_guid = kwargs.get("事件源GUID", None)
                timer_name = kwargs.get("定时器名称", None)

                extra = ""
                if timer_name is not None:
                    extra = f" timer={str(timer_name)}"
                if src_guid is not None:
                    extra = f"{extra} guid={str(src_guid)}"
                if src_label:
                    extra = f"{extra} src={src_label}"

                print(f"[事件分发] {event_name} -> {owner_label} :: {graph_handler}{extra}")
                self.record_trace_event(
                    kind="event_dispatch",
                    message=event_name,
                    owner_entity_id=owner_id_text,
                    owner_entity_name=owner_name,
                    graph_name=graph_name,
                    graph_class=graph_class,
                    handler=handler_name,
                    source_entity_id=src_id,
                    source_entity_name=src_name,
                    source_guid=src_guid,
                    timer_name=str(timer_name) if timer_name is not None else "",
                )

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

    # ========== UI（离线模拟） ==========

    def drain_ui_patches(self) -> List[Dict[str, Any]]:
        """取出并清空 UI patch 列表（用于 UIHarness/HTTP API 回显）。"""
        patches = list(self.ui_patches)
        self.ui_patches = []
        return patches

    def ui_switch_layout(self, player_entity, layout_index: int) -> None:
        """切换玩家当前 UI 布局（离线模拟）。"""
        player_id = self._get_entity_id(player_entity)
        index = int(layout_index)
        self.ui_current_layout_by_player[player_id] = index
        patch = {"op": "switch_layout", "player_id": player_id, "layout_index": index}
        self.ui_patches.append(patch)
        self.record_trace_event(kind="ui", message="switch_layout", **patch)

    def ui_set_widget_state(self, player_entity, widget_index: int, state: str) -> None:
        """修改界面控件/控件组状态（离线模拟）。"""
        player_id = self._get_entity_id(player_entity)
        idx = int(widget_index)
        state_text = str(state or "")
        store = self.ui_widget_state_by_player.setdefault(player_id, {})
        store[idx] = state_text
        patch = {
            "op": "set_widget_state",
            "player_id": player_id,
            "widget_index": idx,
            "state": state_text,
        }
        self.ui_patches.append(patch)
        self.record_trace_event(kind="ui", message="set_widget_state", **patch)

    def ui_activate_widget_group(self, player_entity, group_index: int) -> None:
        """激活控件组库内控件组（离线模拟）。"""
        player_id = self._get_entity_id(player_entity)
        idx = int(group_index)
        active = self.ui_active_groups_by_player.setdefault(player_id, set())
        active.add(idx)
        patch = {"op": "activate_widget_group", "player_id": player_id, "group_index": idx}
        self.ui_patches.append(patch)
        self.record_trace_event(kind="ui", message="activate_widget_group", **patch)

    def ui_remove_widget_group(self, player_entity, group_index: int) -> None:
        """移除控件组库内控件组（离线模拟）。"""
        player_id = self._get_entity_id(player_entity)
        idx = int(group_index)
        active = self.ui_active_groups_by_player.setdefault(player_id, set())
        if idx in active:
            active.remove(idx)
        patch = {"op": "remove_widget_group", "player_id": player_id, "group_index": idx}
        self.ui_patches.append(patch)
        self.record_trace_event(kind="ui", message="remove_widget_group", **patch)
    
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
        self.start_timer_sequence(entity, timer_name, [float(duration)], is_loop)

    def start_timer_sequence(self, entity, timer_name: str, timer_sequence: List[float], is_loop: bool = False) -> None:
        """启动“序列定时器”（与 UGC 定时器语义对齐：触发【定时器触发时】事件）。"""
        entity_id = self._get_entity_id(entity)
        timer_key = f"{entity_id}_{timer_name}"

        if not isinstance(timer_sequence, list) or (not timer_sequence):
            return
        seq: List[float] = [float(x) for x in timer_sequence]
        seq = sorted(seq)

        loop_duration = float(seq[-1])
        if loop_duration <= 0:
            raise ValueError(f"定时器序列最后一项必须 > 0: {timer_sequence!r}")

        now = float(time.monotonic())
        self._timer_token_counter += 1
        self.timers[timer_key] = {
            "entity_id": str(entity_id),
            "timer_name": str(timer_name),
            "sequence": seq,
            "is_loop": bool(is_loop),
            "loop_duration": loop_duration,
            "start_time": now,
            "token": int(self._timer_token_counter),
            "loop_count": 0,
            "next_index": 0,
            "next_fire_time": now + float(seq[0]),
        }
        print(f"[定时器] 启动定时器'{timer_name}', 序列={seq}, 循环={is_loop}")
    
    def stop_timer(self, entity, timer_name: str):
        """停止定时器（Mock）"""
        entity_id = self._get_entity_id(entity)
        timer_key = f"{entity_id}_{timer_name}"
        if timer_key in self.timers:
            del self.timers[timer_key]
            print(f"[定时器] 停止定时器'{timer_name}'")

    def start_motor(
        self,
        entity,
        *,
        motor_name: str,
        duration: float,
        target_position: List[float],
        target_rotation: List[float],
        lock_rotation: bool,
    ) -> None:
        """启动离线基础运动器模拟：到期后更新位姿并触发 `基础运动器停止时`。

        说明：
        - 基于定时器系统实现，确保与普通定时器按时间先后统一排序触发，避免“时间大步推进时先把所有定时器跑完再处理运动器”的乱序问题。
        - 内部会创建一个特殊 timer（不触发 `定时器触发时`，而是触发 `基础运动器停止时`）。
        """
        mname = str(motor_name or "").strip()
        if not mname:
            raise ValueError("motor_name 不能为空")
        dur = float(duration)
        if dur < 0:
            raise ValueError(f"duration 必须 >= 0: {duration!r}")

        ent_id = self._get_entity_id(entity)
        timer_name = f"__motor__{mname}"

        if dur <= 0:
            src_entity = self.get_entity(str(ent_id))
            if src_entity is None:
                return
            pos = list(target_position) if isinstance(target_position, list) else list(target_position)
            if isinstance(pos, list) and len(pos) == 3:
                src_entity.position = [float(pos[0]), float(pos[1]), float(pos[2])]
            rot = list(target_rotation) if isinstance(target_rotation, list) else list(target_rotation)
            if bool(lock_rotation) and isinstance(rot, list) and len(rot) == 3:
                src_entity.rotation = [float(rot[0]), float(rot[1]), float(rot[2])]
            self.trigger_event(
                "基础运动器停止时",
                事件源实体=src_entity,
                事件源GUID=0,
                运动器名称=mname,
            )
            return

        # 复用 timer 驱动，但在 tick 中会按 kind=__motor__ 分支改为触发“基础运动器停止时”
        self.start_timer_sequence(entity, timer_name, [float(dur)], is_loop=False)
        timer_key = f"{ent_id}_{timer_name}"
        info = self.timers.get(timer_key, None)
        if isinstance(info, dict):
            info["kind"] = "__motor__"
            info["motor_name"] = str(mname)
            info["target_position"] = list(target_position) if isinstance(target_position, list) else list(target_position)
            info["target_rotation"] = list(target_rotation) if isinstance(target_rotation, list) else list(target_rotation)
            info["lock_rotation"] = bool(lock_rotation)

    def stop_motor(self, entity, *, motor_name: str, fire_stop_event: bool = True) -> None:
        """停止并删除离线基础运动器模拟，可选触发 `基础运动器停止时`。"""
        mname = str(motor_name or "").strip()
        if not mname:
            raise ValueError("motor_name 不能为空")
        ent_id = self._get_entity_id(entity)
        timer_name = f"__motor__{mname}"
        timer_key = f"{ent_id}_{timer_name}"
        existed = timer_key in self.timers
        if existed:
            del self.timers[timer_key]

        if fire_stop_event:
            src_entity = self.get_entity(str(ent_id))
            if src_entity is not None:
                self.trigger_event(
                    "基础运动器停止时",
                    事件源实体=src_entity,
                    事件源GUID=0,
                    运动器名称=str(mname),
                )

    def tick(self, now: Optional[float] = None, *, max_fires: Optional[int] = None) -> int:
        """推进本地 MockRuntime 的时间（用于本地测试的定时器驱动）。

        Args:
            now: 指定当前时间（用于本地测试的虚拟时钟）；None 表示使用 time.monotonic()
            max_fires: 本次 tick 最多触发多少次“定时器触发时”事件；None 表示不限制（默认行为）
        """
        t = float(time.monotonic() if now is None else now)
        limit = None if max_fires is None else int(max_fires)
        if limit is not None and limit <= 0:
            return 0
        return int(self._tick_timers(now=t, max_fires=limit))

    def _tick_timers(self, *, now: float, max_fires: Optional[int]) -> int:
        fired = 0
        # 每次只触发“最早到期”的一个定时器节点，避免乱序；循环直到没有到期项。
        while True:
            if max_fires is not None and int(fired) >= int(max_fires):
                return int(fired)
            due_key: Optional[str] = None
            due_time: Optional[float] = None
            for key, info in list(self.timers.items()):
                if not isinstance(info, dict):
                    continue
                nft = info.get("next_fire_time", None)
                if not isinstance(nft, (int, float)):
                    continue
                if float(nft) > float(now):
                    continue
                if due_time is None or float(nft) < float(due_time):
                    due_key = str(key)
                    due_time = float(nft)

            if due_key is None:
                return int(fired)

            info = self.timers.get(due_key, None)
            if not isinstance(info, dict):
                continue
            nft = info.get("next_fire_time", None)
            if not isinstance(nft, (int, float)) or float(nft) > float(now):
                continue

            entity_id = str(info.get("entity_id") or "")
            timer_name = str(info.get("timer_name") or "")
            sequence = info.get("sequence", None)
            if not isinstance(sequence, list) or (not sequence):
                del self.timers[due_key]
                continue

            next_index = int(info.get("next_index", 0))
            loop_count = int(info.get("loop_count", 0))
            token = int(info.get("token", 0))
            src_entity = self.get_entity(entity_id)
            if src_entity is None:
                # 实体不存在：直接销毁定时器
                del self.timers[due_key]
                continue

            kind = str(info.get("kind") or "")
            if kind == "__motor__":
                pos = info.get("target_position", None)
                if isinstance(pos, list) and len(pos) == 3:
                    src_entity.position = [float(pos[0]), float(pos[1]), float(pos[2])]
                rot = info.get("target_rotation", None)
                lock_rot = bool(info.get("lock_rotation", False))
                if lock_rot and isinstance(rot, list) and len(rot) == 3:
                    src_entity.rotation = [float(rot[0]), float(rot[1]), float(rot[2])]
                motor_name = str(info.get("motor_name") or "")
                self.trigger_event(
                    "基础运动器停止时",
                    事件源实体=src_entity,
                    事件源GUID=0,
                    运动器名称=motor_name,
                )
            else:
                # 触发事件：与节点图事件 `定时器触发时` 对齐
                self.trigger_event(
                    "定时器触发时",
                    事件源实体=src_entity,
                    事件源GUID=0,
                    定时器名称=timer_name,
                    定时器序列序号=int(next_index + 1),
                    循环次数=int(loop_count),
                )
            fired += 1

            # 事件流中可能终止/重启了定时器；重新取一次确保状态一致
            info2 = self.timers.get(due_key, None)
            if not isinstance(info2, dict):
                continue
            if int(info2.get("token", 0)) != token:
                # 定时器在事件流中被重启/替换：不在此处推进序列，避免覆盖新定时器状态
                continue

            sequence2 = info2.get("sequence", None)
            if not isinstance(sequence2, list) or (not sequence2):
                del self.timers[due_key]
                continue

            is_loop = bool(info2.get("is_loop", False))
            loop_duration = float(info2.get("loop_duration", float(sequence2[-1])))
            start_time = float(info2.get("start_time", float(now)))

            next_index2 = int(info2.get("next_index", 0)) + 1
            loop_count2 = int(info2.get("loop_count", 0))

            if next_index2 >= len(sequence2):
                if is_loop:
                    loop_count2 += 1
                    next_index2 = 0
                else:
                    del self.timers[due_key]
                    continue

            info2["next_index"] = int(next_index2)
            info2["loop_count"] = int(loop_count2)
            info2["next_fire_time"] = start_time + loop_count2 * loop_duration + float(sequence2[next_index2])
    
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

