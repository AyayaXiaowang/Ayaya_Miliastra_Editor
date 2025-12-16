from __future__ import annotations

from .management_sections_base import *


class MainCameraSection(BaseManagementSection):
    """主镜头管理 Section（对应 `ManagementData.main_cameras`）。"""

    section_key = "main_cameras"
    tree_label = "📷 主镜头"
    type_name = "主镜头"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for camera_id, camera_data in package.management.main_cameras.items():
            camera_name = str(camera_data.get("camera_name", ""))
            camera_type = str(camera_data.get("camera_type", "follow"))
            fov_value = float(camera_data.get("fov", 90.0))
            follow_target_text = str(camera_data.get("follow_target", ""))

            display_name = camera_name or str(camera_id)
            attr1 = f"类型: {camera_type}" if camera_type else ""
            attr2 = f"FOV: {fov_value:.1f}"
            attr3 = f"跟随目标: {follow_target_text or '无'}"
            description_text = str(camera_data.get("description", ""))

            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=attr1,
                attr2=attr2,
                attr3=attr3,
                description=description_text,
                last_modified=self._get_last_modified_text(camera_data),
                user_data=(self.section_key, str(camera_id)),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        existing_ids: Optional[set[str]] = None,
        allow_edit_id: bool = True,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "camera_id": "",
            "camera_name": "",
            "camera_type": "follow",
            "fov": 90.0,
            "near_clip": 0.1,
            "far_clip": 1000.0,
            "follow_target": "",
            "follow_distance": 5.0,
            "follow_height": 2.0,
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(460, 520))

        id_edit = builder.add_line_edit(
            "镜头ID*:",
            str(initial_values.get("camera_id", "")),
            "用于在数据中唯一标识该镜头",
        )
        if not allow_edit_id:
            id_edit.setReadOnly(True)

        name_edit = builder.add_line_edit(
            "镜头名称*:",
            str(initial_values.get("camera_name", "")),
            "用于编辑器展示的名称",
        )
        type_combo = builder.add_combo_box(
            "镜头类型:",
            ["follow", "fixed", "path", "custom"],
            str(initial_values.get("camera_type", "follow")),
        )
        fov_spin = builder.add_double_spin_box(
            "视野角度(FOV):",
            minimum=30.0,
            maximum=120.0,
            value=float(initial_values.get("fov", 90.0)),
            decimals=1,
            single_step=1.0,
            suffix="°",
        )
        near_spin = builder.add_double_spin_box(
            "近裁剪面:",
            minimum=0.01,
            maximum=10.0,
            value=float(initial_values.get("near_clip", 0.1)),
            decimals=2,
            single_step=0.01,
        )
        far_spin = builder.add_double_spin_box(
            "远裁剪面:",
            minimum=100.0,
            maximum=10000.0,
            value=float(initial_values.get("far_clip", 1000.0)),
            decimals=1,
            single_step=10.0,
        )
        follow_target_edit = builder.add_line_edit(
            "跟随目标:",
            str(initial_values.get("follow_target", "")),
            "可选，填写需要跟随的实体ID",
        )
        distance_spin = builder.add_double_spin_box(
            "跟随距离:",
            minimum=0.0,
            maximum=100.0,
            value=float(initial_values.get("follow_distance", 5.0)),
            decimals=2,
            single_step=0.5,
        )
        height_spin = builder.add_double_spin_box(
            "跟随高度:",
            minimum=-50.0,
            maximum=50.0,
            value=float(initial_values.get("follow_height", 2.0)),
            decimals=2,
            single_step=0.5,
        )
        description_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        normalized_existing_ids: set[str] = set()
        if existing_ids is not None:
            for value in existing_ids:
                normalized_existing_ids.add(str(value))

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from app.ui.foundation import dialog_utils

            camera_id_text = id_edit.text().strip()
            if not camera_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入镜头ID",
                )
                return False

            if allow_edit_id and normalized_existing_ids:
                original_id = str(initial_values.get("camera_id", ""))
                if camera_id_text != original_id and camera_id_text in normalized_existing_ids:
                    dialog_utils.show_warning_dialog(
                        dialog_self,
                        "提示",
                        "该镜头ID已存在，请输入其他ID",
                    )
                    return False

            if not name_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入镜头名称",
                )
                return False

            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "camera_id": id_edit.text().strip(),
            "camera_name": name_edit.text().strip(),
            "camera_type": str(type_combo.currentText()),
            "fov": float(fov_spin.value()),
            "near_clip": float(near_spin.value()),
            "far_clip": float(far_spin.value()),
            "follow_target": follow_target_edit.text().strip(),
            "follow_distance": float(distance_spin.value()),
            "follow_height": float(height_spin.value()),
            "description": description_edit.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        cameras_mapping = package.management.main_cameras
        if not isinstance(cameras_mapping, dict):
            cameras_mapping = {}
            package.management.main_cameras = cameras_mapping

        existing_ids: set[str] = set(cameras_mapping.keys())
        camera_id_value = generate_prefixed_id("camera")
        while camera_id_value in existing_ids:
            camera_id_value = generate_prefixed_id("camera")

        default_index = len(cameras_mapping) + 1
        camera_name_value = f"主镜头{default_index}"

        payload: Dict[str, Any] = {
            "camera_id": camera_id_value,
            "camera_name": camera_name_value,
            "camera_type": "follow",
            "fov": 90.0,
            "near_clip": 0.1,
            "far_clip": 1000.0,
            "follow_target": "",
            "follow_distance": 5.0,
            "follow_height": 2.0,
            "description": "",
            "metadata": {},
        }
        cameras_mapping[camera_id_value] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        camera_data = package.management.main_cameras.get(item_id)
        if camera_data is None:
            return False

        initial_values = {
            "camera_id": item_id,
            "camera_name": camera_data.get("camera_name", ""),
            "camera_type": camera_data.get("camera_type", "follow"),
            "fov": camera_data.get("fov", 90.0),
            "near_clip": camera_data.get("near_clip", 0.1),
            "far_clip": camera_data.get("far_clip", 1000.0),
            "follow_target": camera_data.get("follow_target", ""),
            "follow_distance": camera_data.get("follow_distance", 5.0),
            "follow_height": camera_data.get("follow_height", 2.0),
            "description": camera_data.get("description", ""),
        }
        dialog_data = self._build_form(
            parent_widget,
            title="编辑主镜头",
            initial=initial_values,
            existing_ids=None,
            allow_edit_id=False,
        )
        if dialog_data is None:
            return False

        camera_data["camera_id"] = item_id
        camera_data["camera_name"] = dialog_data["camera_name"]
        camera_data["camera_type"] = dialog_data["camera_type"]
        camera_data["fov"] = dialog_data["fov"]
        camera_data["near_clip"] = dialog_data["near_clip"]
        camera_data["far_clip"] = dialog_data["far_clip"]
        camera_data["follow_target"] = dialog_data["follow_target"]
        camera_data["follow_distance"] = dialog_data["follow_distance"]
        camera_data["follow_height"] = dialog_data["follow_height"]
        camera_data["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.main_cameras:
            return False
        del package.management.main_cameras[item_id]
        return True



