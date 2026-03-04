from __future__ import annotations


def is_nep_reflection_type_expr(type_expr: str) -> bool:
    """
    判断 NodeEditorPack pin TypeExpr 是否为“反射/泛型端口”表达式（需要 ConcreteBase/indexOfConcrete）。

    已知真源形态（NodeEditorPack / genshin-ts）：
    - R<T> / R<K> / R<V>：反射泛型
    - L<R<T>>：列表包裹的反射泛型
    - D<R<K>,R<V>>：字典家族的 K/V 双泛型
    """
    t = str(type_expr or "").strip()
    if t == "":
        return False
    if t.startswith("R<") and t.endswith(">") and len(t) > 3:
        return True
    if t.startswith("L<R<") and t.endswith(">>"):
        return True
    if t.startswith("D<") and "R<" in t:
        return True
    return False

