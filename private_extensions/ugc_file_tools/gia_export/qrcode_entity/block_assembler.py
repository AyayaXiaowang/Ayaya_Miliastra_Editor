from __future__ import annotations

from .block_model import BlockModel
from .proto_gen.asset_pb2 import Asset, AssetMeta
from .proto_gen.entity_pb2 import (
    Component,
    Entity,
    EntityData,
    NameProperty,
    Position,
    Property,
    Rotation,
    Scale,
    TemplateReference,
    TransformComponent,
)
from .proto_gen.gia_pb2 import GIACollection


class BlockAssembler:
    """将 BlockModel 列表编码为 GIACollection protobuf bytes。"""

    def __init__(self, entity_id_start: int):
        self.entity_id_start = int(entity_id_start)
        self.current_entity_id = int(entity_id_start)

    @staticmethod
    def _create_component_transform(block: BlockModel) -> Component:
        position = Position(x=float(block.position_x), y=float(block.position_y), z=float(block.position_z))
        rotation = Rotation(x=float(block.rotation_x), y=float(block.rotation_y), z=float(block.rotation_z))
        scale = Scale(x=float(block.scale_x), y=float(block.scale_y), z=float(block.scale_z))
        transform_data = TransformComponent(
            position=position,
            rotation=rotation,
            scale=scale,
            field_501=4294967295,  # -1 unsigned
        )
        return Component(component_type=Component.ComponentType.TRANSFORM, transform=transform_data)

    @staticmethod
    def _create_property_name(name: str) -> Property:
        name_prop = NameProperty(name=str(name), static_block=NameProperty.StaticBlock.STATIC)
        return Property(property_type=Property.PropertyType.NAME, name=name_prop)

    def _create_entity_core(self, *, block: BlockModel, entity_id: int, template_id: int) -> EntityData:
        template_ref = TemplateReference(template_id=int(template_id), field_2=1)
        core = EntityData(entity_id=int(entity_id), template=template_ref, template_id_ref=int(template_id))

        if str(block.name or ""):
            core.properties.extend([self._create_property_name(str(block.name))])
        core.components.extend([self._create_component_transform(block)])
        return core

    @staticmethod
    def _create_asset_meta(entity_id: int) -> AssetMeta:
        return AssetMeta(field_2=1, meta_type=AssetMeta.AssetMetaType.ENTITY, asset_id=int(entity_id))

    def _generate_entity_id(self, block: BlockModel) -> int:
        if block.entity_id is None:
            eid = int(self.current_entity_id)
            self.current_entity_id += 1
            return eid
        return int(block.entity_id)

    def _create_asset(self, block: BlockModel) -> Asset:
        entity_id = self._generate_entity_id(block)
        entity_name = str(block.name) if str(block.name or "") else f"Entity_{entity_id}"

        data = self._create_entity_core(block=block, entity_id=int(entity_id), template_id=int(block.template_id))
        entity_data = Entity(data=data, field_2=0, template_id=int(block.template_id))
        meta = self._create_asset_meta(int(entity_id))
        return Asset(meta=meta, name=str(entity_name), type=Asset.AssetType.ENTITY, entity_data=entity_data)

    def assemble(self, blocks: list[BlockModel]) -> bytes:
        collection = GIACollection()
        for block in list(blocks or []):
            collection.Assets.append(self._create_asset(block))
        return collection.SerializeToString()

    def reset_entity_id(self, start_id: int | None = None) -> None:
        self.current_entity_id = int(start_id) if start_id is not None else int(self.entity_id_start)

