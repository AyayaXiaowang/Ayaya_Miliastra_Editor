## 目录用途
- 读取并解析 Graph_Generater 的“项目存档/存档包”目录（例如 `assets/资源库/项目存档/<package_id>/`），将包内资源与节点图原始结构加载为“程序可识别”的 Python 数据结构。
- 提供与导出器解耦的“加载层”：导出器负责落盘与索引生成；本目录负责按索引读取、做基础归一化与跨引用解析（不做业务语义猜测）。

## 当前状态
- 支持按索引加载：元件库、实体摆放、战斗预设、管理配置等资源 JSON。
- 支持加载节点图原始结构：`节点图/原始解析/pyugc_graphs*` 与 `pyugc_node_defs*`，并对节点记录中的常量/端口索引做基础归一化。
- 节点图连线（edges）已可解析为 Python dataclass：区分 `flow/data` 两类边，并保留端口引用（data=端口索引；flow=group/branch）。
- `解析状态.md` 不再要求存在于存档包根目录；优先指向 `ugc_file_tools/parse_status/<package_id>/解析状态.md`（兼容历史产物 fallback）。
  - 解析状态路径定位以 `ugc_file_tools.repo_paths.ugc_file_tools_root()` 为单一真源，不依赖外层工作区目录布局。
- 兼容“极简存档包”：若某些资源索引文件（例如 `元件库/templates_index.json`）不存在，则视为该类资源为空列表（不会因为缺索引文件直接失败）。

## 注意事项
- 不使用 try/except；读取失败或结构不符直接抛出，便于定位数据问题与保持一致性。
- 节点图“生成可执行 Graph Code”属于更高层的语义映射工作，不在本目录强行保证。
- 当前 edges 仍是“结构级别”表示：端口名称/节点语义（type_id→节点名）需要结合校准图与映射表逐步完善。
- CLI/脚本如需配置控制台编码，统一使用 `ugc_file_tools/console_encoding.py`，避免在多个文件内重复样板代码。
- 本文件不记录修改历史，仅保持用途/状态/注意事项的实时描述。