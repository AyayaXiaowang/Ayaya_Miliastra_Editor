from pathlib import Path
import sys
import types
from PyQt6 import QtWidgets
from app.models.view_modes import ViewMode

WORKSPACE_ROOT = Path(__file__).resolve().parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
APP_DIR = WORKSPACE_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

stub_module = types.ModuleType("rapidocr_onnxruntime")
class RapidOCR:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
    def __call__(self, *args, **kwargs):
        return None
stub_module.RapidOCR = RapidOCR
sys.modules["rapidocr_onnxruntime"] = stub_module

from ui.main_window import MainWindowV2

app = QtWidgets.QApplication([])
window = MainWindowV2(WORKSPACE_ROOT)

print("initial_mode", ViewMode.from_index(window.central_stack.currentIndex()))
print("initial_side_tabs", [window.side_tab.tabText(i) for i in range(window.side_tab.count())])

window._on_mode_changed("combat")
print("after_switch_combat", ViewMode.from_index(window.central_stack.currentIndex()))
print("side_tabs_after_combat", [window.side_tab.tabText(i) for i in range(window.side_tab.count())])

combat_widget = window.combat_widget
combat_widget.set_context(window.package_controller.current_package)

player_item = None
skill_item = None
for idx in range(combat_widget.item_list.count()):
    item = combat_widget.item_list.item(idx)
    user_data = combat_widget._get_item_user_data(item)
    if not user_data:
        continue
    section_key, item_id = user_data
    if section_key == "player_template" and player_item is None:
        player_item = item
    if section_key == "skill" and skill_item is None:
        skill_item = item

if player_item is not None:
    combat_widget.item_list.setCurrentItem(player_item)
    combat_widget._on_item_selection_changed()
    print("after_select_player_template", [window.side_tab.tabText(i) for i in range(window.side_tab.count())])

if skill_item is not None:
    combat_widget.item_list.setCurrentItem(skill_item)
    combat_widget._on_item_selection_changed()
    print("after_select_skill", [window.side_tab.tabText(i) for i in range(window.side_tab.count())])
    section_key, item_id = combat_widget._get_item_user_data(skill_item)
    window._on_skill_selected(item_id)
    print("after_manual_on_skill_selected", [window.side_tab.tabText(i) for i in range(window.side_tab.count())])

