"""临时脚本：扫描测试项目中所有自定义变量名和图变量名，找出超过20字符的。"""
import re
import os

MAX_LEN = 20

# 1. 扫描注册表中的 variable_name
reg_path = r"assets\资源库\项目存档\测试项目\管理配置\关卡变量\自定义变量注册表.py"
with open(reg_path, encoding="utf-8-sig") as f:
    content = f.read()

names = re.findall(r'variable_name\s*=\s*"(.*?)"', content)
print("=== 自定义变量注册表 variable_name ===")
over_count = 0
for n in names:
    if len(n) > MAX_LEN:
        print(f"  OVER [{len(n)}] {n!r}")
        over_count += 1
if over_count == 0:
    print("  (无超长)")
print()

# 2. 扫描关卡变量定义文件中的 variable_name
print("=== 关卡变量文件 variable_name ===")
over_count2 = 0
lv_root = r"assets\资源库\项目存档\测试项目\管理配置\关卡变量"
for dirpath, dirs, files in os.walk(lv_root):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if not fn.endswith(".py"):
            continue
        fp = os.path.join(dirpath, fn)
        with open(fp, encoding="utf-8-sig") as f:
            src = f.read()
        found = re.findall(r'"variable_name"\s*:\s*"(.*?)"', src)
        found += re.findall(r'variable_name\s*=\s*"(.*?)"', src)
        for vn in found:
            if len(vn) > MAX_LEN:
                print(f"  OVER [{len(vn)}] {vn!r}  <-- {fp}")
                over_count2 += 1
if over_count2 == 0:
    print("  (无超长)")
print()

# 3. 扫描所有节点图中的 GRAPH_VARIABLES
print("=== 节点图 GRAPH_VARIABLES ===")
over_count3 = 0
for root_dir in [
    r"assets\资源库\项目存档\测试项目\节点图",
    r"assets\资源库\项目存档\测试项目\复合节点库",
]:
    if not os.path.isdir(root_dir):
        continue
    for dirpath, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, encoding="utf-8-sig") as f:
                src = f.read()
            if "GRAPH_VARIABLES" not in src:
                continue
            # 提取 GRAPH_VARIABLES 块中的变量名（作为 key）
            m = re.search(r"GRAPH_VARIABLES\s*=\s*\{(.*?)\}", src, re.DOTALL)
            if not m:
                continue
            block = m.group(1)
            var_keys = re.findall(r'"(.*?)"\s*:', block)
            for vk in var_keys:
                if len(vk) > MAX_LEN:
                    print(f"  OVER [{len(vk)}] {vk!r}  <-- {fp}")
                    over_count3 += 1
if over_count3 == 0:
    print("  (无超长)")
print()

# 4. 扫描节点图中使用的自定义变量引用
print("=== 节点图中引用自定义变量名（节点参数） ===")
over_count4 = 0
for root_dir in [
    r"assets\资源库\项目存档\测试项目\节点图",
    r"assets\资源库\项目存档\测试项目\复合节点库",
]:
    if not os.path.isdir(root_dir):
        continue
    for dirpath, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, encoding="utf-8-sig") as f:
                src = f.read()
            # 找自定义变量名参数
            refs = re.findall(r'\.自定义变量名\("(.*?)"\)', src)
            for vn in refs:
                if len(vn) > MAX_LEN:
                    print(f"  OVER [{len(vn)}] {vn!r}  <-- {fp}")
                    over_count4 += 1
if over_count4 == 0:
    print("  (无超长)")

print()
print("=== 扫描完成 ===")
