# graph_code/utils 模块

## 目录用途
提供节点图代码解析的公共工具函数，统一处理元数据提取、AST操作、注释提取等通用逻辑。

## 模块职责

### metadata_extractor.py
- 从 docstring 提取节点图基础元数据（graph_id、graph_name、graph_type、description 等），图变量一律忽略 docstring，仅在代码中声明。
- 读取源码默认使用 `utf-8-sig`，兼容 Windows 常见的 UTF-8 BOM；避免 `ast.parse` 因 `U+FEFF` 失败。
- 解析代码级图变量声明：扫描模块顶层的 `GRAPH_VARIABLES: list[GraphVariableConfig]`，提取变量名、类型、默认值、是否对外暴露，以及字典类型变量的 `dict_key_type` / `dict_value_type`，统一写入 `GraphMetadata.graph_variables`，作为图变量的唯一事实来源。
  - 结构体类图变量支持可选 `struct_name`：当 `variable_type` 为 `结构体/结构体列表` 且显式提供 `struct_name="某结构体定义名"` 时，会被提取并写入 `graph_variables`，用于后续写回存档/结构体语义校验。
  - 默认值提取支持一元 +/- 数值常量（例如 `-1` / `-1.0`），避免负数字面量在 AST 中被误判为不可提取。
- 解析动态端口信息（多分支节点的动态输出端口）。
- 统一元数据结构定义（GraphMetadata dataclass）。

### authoring_tools.py
- 面向“写节点图体验”的纯函数工具（不改变解析/校验契约）：从代码级 `GRAPH_VARIABLES` 生成 `GV.xxx` 形式的图变量名常量块，减少字符串拼写风险并获得 IDE 补全。

### ast_utils.py
- 常量值提取：`extract_constant_value()` - 从 AST 节点提取静态常量值，统一供 IR 与复合节点等场景复用
  - 支持标准常量（int/float/str/bool/None）（项目要求 Python 3.10+，不再保留旧版 AST 节点兼容分支）
  - 支持一元 +/- 数值常量（例如 `-1` / `+1.0`），用于多分支 case 值与 range 参数等场景
  - 支持列表/元组/字典等容器字面量（递归提取元素/键值；任一子项不可静态提取则整体视为不可提取，避免“半可提取”污染上下文）
  - 对 `self.owner_entity` 返回字符串表达式供上层按“图所属实体”语义处理；
  - 对以下划线开头的实例字段默认视为运行期状态（不可静态提取），但若解析器已将节点图类体内的“类常量”以 key=`"self._xxx"` 注入模块常量上下文，则 `self._xxx` 可被静态提取（用于定时器名称、变量名等标识性参数回填）；
  - 其余公开字段返回 `"self.<字段名>"` 形式交由上层使用
- 格式检测：`is_class_structure_format()` - 判断代码是否为类结构格式（事件方法）
- 旧函数式复合节点格式已移除，不再提供“按顶层函数签名识别复合节点”的工具函数，避免支持口径漂移。
- AST通用工具：简化AST遍历与模式匹配

### comment_extractor.py
- 注释提取：`extract_comments()` - 使用tokenize提取代码中的所有注释
- 注释关联：`associate_comments_to_nodes()` - 将注释与节点关联（块注释、行尾注释、composite_id）
- 事件流注释提取：提取 "===事件流N===" 格式的注释
- 关联策略优先使用节点 `source_lineno` 精确匹配，缺失行号时再回退按创建顺序处理，并在写入事件流注释前自动扩容列表

### composite_instance_utils.py
- `iter_composite_instance_pairs()`：扫描 `self.xxx = ClassName(...)`，为解析和校验提供一致的实例别名/类名对。
- `collect_composite_instance_aliases()`：遍历整个模块，收集所有复合节点实例别名集合，供语法规则复用。

### graph_code_rewrite_config.py
- 语法糖归一化改写的**单一配置源**：集中维护列表/字典字面量上限、以及 `enable_shared_composite_sugars`（共享复合节点语法糖）开关策略，供解析入口与 validate 规则复用，避免口径漂移与重复改写链路。

### list_literal_rewriter.py
- 列表相关语法糖归一化：在 Graph Code/复合节点类方法体内允许使用非空列表字面量 `[...]` 以及常见列表原地修改写法，并在“解析/校验入口”统一改写为等价的节点调用：
  - `[...]` → 【拼装列表】
  - `目标列表[序号] = 值` → 【对列表修改值】（仅单下标，不支持切片）
  - `del 目标列表[序号]` → 【对列表移除值】（仅单下标，不支持切片）
  - `目标列表.insert(序号, 值)` → 【对列表插入值】（仅位置参数）
  - `目标列表.clear()` → 【清除列表】
  - `目标列表.extend(接入列表)` → 【拼接列表】（仅位置参数）
- `for x in [...]` **不允许**：for 的迭代器位置禁止直接使用列表字面量，必须先显式声明带中文类型注解的列表变量（例如 `列表: "整数列表" = [1,2,3]`），再 `for x in 列表:`。
- 约束：禁止空列表 `[]`、禁止元素数超过上限、禁止 `[*xs]` 这类 Starred 扩展语法（无法静态展开）；不处理模块/类体顶层列表字面量（无法转换为节点）。

### dict_literal_rewriter.py
- 字典字面量语法糖归一化：字典必须具备**显式键/值类型**，因此仅允许以“带别名字典中文类型注解的变量声明”形式出现：
  - ✅ 允许：`映射: "键类型-值类型字典" = {k: v}` / `映射: "键类型_值类型字典" = {k: v}`
  - ❌ 禁止：直接在节点调用入参或其它表达式里内联 `{...}`（会报错 `CODE_DICT_LITERAL_TYPED_ANNOTATION_REQUIRED`）
  - 解析/校验入口仍会将合法的 `{k: v}` 统一改写为等价的【拼装字典】节点调用（`拼装字典(self.game, k0, v0, k1, v1, ...)`）。
- `for x in {...}` **不允许**：for 的迭代器位置禁止直接使用字典字面量；字典遍历应先用【获取字典中键组成的列表】/【获取字典中值组成的列表】得到列表变量，再进行 for 迭代。
- 约束：禁止空字典 `{}`、禁止键值对数量超过上限（默认 50）、禁止 `{**d}` 这类展开语法（无法静态展开）；不处理模块/类体顶层字典字面量（无法转换为节点）。

### syntax_sugar_rewriter.py
- 常见 Python 语法糖归一化：在 Graph Code/复合节点类方法体内，将解析器/IR 不直接支持的语法统一改写为等价的“节点调用（Call）”形态，复用后续端口必填/同型输入/布尔条件等规则。
  - 共享复合节点语法糖（仅普通节点图启用）：对 `any/all/sum`、`整数列表[start:end]`、以及“整数/浮点数三元表达式（X if 条件 else Y）”等高频但不支持写法自动改写为共享复合节点调用，并注入 `__init__` 中的实例声明以保证 IR 识别；复合节点文件默认关闭以避免“复合内嵌套复合”违规。
  - 扩展：允许直接写“共享复合节点名(...)”（如 `整数列表_按布尔掩码过滤(...)`、`实体列表_按评分取前K(...)` 等），解析器会自动注入实例并改写为对应入口方法调用，从而避免业务脚本手动实例化复合节点。
  - 图所属实体语法糖：`self.owner_entity` → 【获取自身实体】（等价于 `获取自身实体(self.game)`），使“所属实体”在图中显式表现为可连线/可搜索的节点输出。
  - 列表下标读取：`值 = 列表[序号]` → 【获取列表对应值】
  - len(...):
    - len(列表)：`len(列表)` → 【获取列表长度】
    - len(字典变量)（仅 server）：`len(字典变量)` → 【查询字典长度】
  - abs(数值)：`abs(x)` → 【绝对值运算】
- pow（仅 server）：`pow(a, b)` → 【幂运算】
- print（仅 server，且仅语句形态）：`print(x)` → 【打印字符串】（若 x 非字符串，会自动插入【数据类型转换】）
  - max/min：
    - `max(列表)` / `min(列表)` → 【获取列表最大值】/【获取列表最小值】
    - `max(a, b)` / `min(a, b)`：
      - server → 【取较大值】/【取较小值】（单节点）
      - client → `获取列表最大值/获取列表最小值(列表=拼装列表(a, b))`
    - 常见 clamp 写法（仅 server，且需能可靠识别上下限/输入）：`max(下限, min(上限, 输入))` / `min(上限, max(下限, 输入))`
      → 【范围限制运算】（单节点；无法判定时会保持为 max/min 嵌套写法）
  - 类型转换：`int/float/str/bool(x)` → 【数据类型转换】（输出类型由承接端口/变量注解决定）
  - 取整（仅 server）：`round/floor/ceil(x)` → 【取整数运算】（取整方式=取整逻辑_四舍五入/取整逻辑_向下取整/取整逻辑_向上取整）
- 字典读取/写入：
  - `值 = 字典[键]` / `字典[键] = 值` / `del 字典[键]` → 【以键查询字典值】/【对字典设置或新增键值对】/【以键对字典移除键值对】
  - `值 = 字典.get(键)` → 【以键查询字典值】（仅支持 1 个位置参数）
- 包含判断：`值 in 列表` / `值 not in 列表` / `键 in 字典` / `键 not in 字典` → 【列表是否包含该值】/【查询字典是否包含特定键】（`not in` 通过【逻辑非运算】包裹实现）
  - `值 in 字典.values()` / `值 not in 字典.values()`（仅 server）：→ 【查询字典是否包含特定值】（`not in` 通过【逻辑非运算】包裹实现）
  - `键 in 字典.keys()` / `键 not in 字典.keys()`（仅 server）：→ 【查询字典是否包含特定键】（与 `键 in 字典` 语义一致；`not in` 同上）
  - if 内联比较：`A == B`、`A > B`、`A <= B` 等 → 对应比较节点（按 scope 映射：server 用“数值大于/小于…”，client 用“是否大于/小于…”）
- `!=`：通过【是否相等】+【逻辑非运算】实现（避免生成 Python 的 `not <expr>`，解析器不直接支持 UnaryOp）
  - 逻辑组合：`A and B` / `A or B` → 【逻辑与运算】/【逻辑或运算】（按 scope 映射输入端口名：server=输入1/输入2，client=条件1/条件2）
  - 逻辑异或：`A ^ B` → 【逻辑异或运算】（仅当 A/B 均可稳定识别为布尔值时才改写；server/client 均支持）
  - 逻辑非：`not 条件` → 【逻辑非运算】
  - 增量赋值：`x += y` / `x -= y` / `x *= y` / `x /= y` → `x = 加/减/乘/除法运算(...)`
  - 列表原地拼接（仅 server）：`列表A += 列表B` → 【拼接列表】（保持 in-place 语义；client 缺少等价节点会报错）
  - 二元算术：`a + b` / `a - b` / `a * b` / `a / b` → 【加/减/乘/除法运算】（支持嵌套表达式折叠）
  - 三维向量运算符（按中文类型注解稳定识别后才改写，server/client 均支持）：
    - `向量A + 向量B` / `向量A - 向量B` → 【三维向量加法】/【三维向量减法】
    - `向量 * 缩放倍率` / `缩放倍率 * 向量` → 【三维向量缩放】
    - `向量A @ 向量B` → 【三维向量内积】
    - `向量A ^ 向量B` → 【三维向量外积】
    - `abs(向量)` → 【三维向量模运算】
  - 三维向量字面量（按中文类型注解稳定识别后才改写，server/client 均支持）：
    - `向量: "三维向量" = (x, y, z)` / `向量: "三维向量" = [x, y, z]`
      → `创建三维向量(self.game, X分量=x, Y分量=y, Z分量=z)`
    - 若列表字面量已被重写为 `拼装列表(self.game, x, y, z)`，且目标变量类型为“三维向量”，同样会再归一化为 `创建三维向量(...)`
  - 一元运算：`-x` / `+x` → `0 - x`（【减法运算】）/ `x`（避免保留 UnaryOp）
  - 运算符（仅 server）：
    - `%`：`a % b` → “正模”语义（模数为正时结果在 `[0, 模数-1]`）。普通节点图优先改写为共享复合节点 `整数_正模运算` 调用；复合节点文件内部（禁止嵌套复合）则回退为等价节点链 `((a % m) + m) % m`。
    - `**`：`a ** b` → 【幂运算】
    - 位运算：`a & b` / `a | b` / `a ^ b` / `a << n` / `a >> n` / `~a` → 【按位与/按位或/按位异或/左移运算/右移运算/按位取补运算】
    - 按位读出折叠：严格匹配典型模板后可单节点折叠为【按位读出】（仅 server）
    - 按位写入折叠：严格匹配典型模板后可单节点折叠为【按位写入】（仅 server；支持 mask 内联或严格两步模板）
  - math.xxx(...)（仅 server）：
    - `math.sin/cos/tan(x)` → 【正弦函数/余弦函数/正切函数】
    - `math.asin/acos/atan(x)` → 【反正弦函数/反余弦函数/反正切函数】
    - `math.sqrt(x)` → 【算术平方根运算】
  - `math.pow(a, b)` → 【幂运算】
    - `math.log(x, base)` → 【对数运算】（仅两参形式）
  - `math.fabs(x)` → 【绝对值运算】
  - 容器方法（仅 server）：
    - `列表变量.sort()` / `列表变量.sort(reverse=True/False)` → 【列表排序】
    - `字典变量.keys()` / `字典变量.values()` → 【获取字典中键组成的列表】/【获取字典中值组成的列表】
    - `字典变量.clear()` → 【清空字典】
  - enumerate：`for 序号, 元素 in enumerate(列表变量):` → `len + range + 列表下标读取`
    - 约束：列表变量必须带中文类型注解（例如 `"整数列表"`），以便推断元素类型并为 `元素` 自动补齐注解
- append/pop（不新增节点）：
  - `目标列表.append(x)`（仅 server）→ `对列表插入值(列表=目标列表, 插入序号=<大常量>, 插入值=x)`（单节点；利用 insert 越界等价 append；client 侧缺少等价节点会报错）
  - `目标列表.pop(序号)`（仅 server，且仅语句形态）→ `对列表移除值(列表=目标列表, 移除序号=序号)`（不支持承接返回值；如需删除请优先用 `del 目标列表[序号]`）
  - `目标字典.pop(键)`（仅 server，且仅语句形态）→ `以键对字典移除键值对(字典=目标字典, 键=键)`（不支持承接返回值；如需安全删除/返回值请拆分为查询+分支+删除）
  - random.xxx(...)：
    - `random.randint(a, b)`（仅 server）→ 【获取随机整数】
    - `random.uniform(a, b)` → server【获取随机浮点数】 / client【获取随机数】
    - `random.random()` → server【获取随机浮点数(下限=0.0, 上限=1.0)】 / client【获取随机数(下限=0.0, 上限=1.0)】
  - time（仅 server）：
    - `time.time()` → 【查询时间戳（UTC+0时区）】（输出为整数时间戳）
  - datetime（仅 server）：
    - `datetime.fromtimestamp(ts)` → 【根据时间戳计算格式化时间】（输出：年/月/日/时/分/秒）
    - `datetime.fromtimestamp(ts).isoweekday()` → 【根据时间戳计算星期几】（输出：1~7）
    - `datetime.fromtimestamp(ts).weekday() + 1` → 【根据时间戳计算星期几】（单节点）
    - `datetime(...).timestamp()` → 【根据格式化时间计算时间戳】
  - math 扩展：
    - `math.radians(x)` / `math.degrees(x)` → 【角度转弧度】/【弧度转角度】（server/client 均支持；端口名按作用域映射）
    - `math.dist(p1, p2)`（仅 server）→ 【两坐标点距离】
    - `math.pi`（仅 server）→ 【圆周率】
  - dict 扩展：
    - `dict(zip(键列表, 值列表))`（仅 server）→ 【建立字典】
  - 文件拆分（保持对外 API 与行为不变；仅做组织与可维护性优化）：
    - `syntax_sugar_rewriter.py`：对外入口（`rewrite_graph_code_syntax_sugars` / `SyntaxSugarRewriteIssue`）
    - `syntax_sugar_rewriter_constants.py`：节点名/端口名映射与 scope 归一化
    - `syntax_sugar_rewriter_issue.py`：Issue 数据结构
    - `syntax_sugar_rewriter_ast_helpers.py`：AST 辅助函数
    - `syntax_sugar_rewriter_transformer.py`：轻量 wrapper（组装 mixin，导出 `_GraphCodeSyntaxSugarTransformer`）
    - `syntax_sugar_rewriter_transformer_base.py`：Transformer 共享状态与工具方法（位运算折叠/time&datetime/clamp 等）
    - `syntax_sugar_rewriter_transformer_stmt.py`：语句级改写（AnnAssign/For/Assign/Delete/AugAssign/Expr/FunctionDef）
    - `syntax_sugar_rewriter_transformer_expr_binary.py`：表达式级改写（BinOp/UnaryOp）
    - `syntax_sugar_rewriter_transformer_expr_access.py`：表达式级改写（Attribute/Subscript）
    - `syntax_sugar_rewriter_transformer_expr_call.py`：表达式级改写（Call）
    - `syntax_sugar_rewriter_transformer_expr_compare.py`：表达式级改写（Compare/BoolOp）

## 设计原则
1. **纯函数设计**：所有工具函数无副作用，易于测试
2. **类型安全**：完整的类型标注，使用dataclass定义结构
3. **错误透明**：不使用try-catch，错误直接抛出
4. **单一职责**：每个函数专注一项具体任务

## 当前状态
已完成基础工具模块的提取和整合；语法糖重写 Transformer 已按职责拆分为多个小文件，降低单文件体积并便于后续扩展。

## 注意事项
- 工具函数不依赖具体的解析器实现
- AST工具函数需要处理Python 3.10+的match/case语法
- 图变量只解析代码级 `GRAPH_VARIABLES`，docstring 中的“节点图变量”段不再生效
- 常量提取需要正确处理 NOT_EXTRACTABLE 哨兵值；容器字面量需避免“部分可提取”导致哨兵泄漏到上下文/缓存中
- 注释关联不应覆盖节点已存在的有效源码行号：若 `source_lineno` 已为正数，则只关联注释文本，不重写行号。

---
注意：本文件不记录修改历史。始终保持对"目录用途、当前状态、注意事项"的实时描述。

