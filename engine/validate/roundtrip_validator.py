from __future__ import annotations
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol, Any

from engine.graph.models.graph_model import GraphModel
from engine.nodes.node_definition_loader import NodeDef


class GraphCodeGenerator(Protocol):
    def generate_code(self, graph_model: GraphModel, metadata: Optional[Dict[str, Any]] = None) -> str: ...


@dataclass
class RoundtripValidationResult:
    """往返验证结果"""
    success: bool
    error_type: str = ""  # "generation" | "syntax" | "execution" | "empty"
    error_message: str = ""
    error_details: str = ""  # 技术细节（如堆栈跟踪）
    line_number: Optional[int] = None


class RoundtripValidator:
    """节点图代码往返验证器
    
    验证流程：
    1. GraphModel -> 代码（生成）
    2. 代码 -> Python语法检查
    3. 代码 -> 解析 -> GraphModel
    4. 检查解析后的GraphModel是否有效
    """
    
    def __init__(
        self,
        workspace_path: Path,
        node_library: Dict[str, NodeDef],
        *,
        code_generator: GraphCodeGenerator,
    ):
        self.workspace_path = workspace_path
        self.node_library = node_library
        self._code_generator = code_generator
        self._parser = None
    
    def validate(self, graph_model: GraphModel, metadata: Optional[Dict] = None) -> RoundtripValidationResult:
        """验证GraphModel能否被正确序列化和反序列化"""
        generated_code = self._generate_code(graph_model, metadata)
        if not isinstance(generated_code, str):
            return RoundtripValidationResult(
                success=False,
                error_type="generation",
                error_message="代码生成失败，返回值类型异常",
                error_details=f"返回类型: {type(generated_code).__name__}",
            )
        
        if not generated_code or len(generated_code.strip()) < 50:
            return RoundtripValidationResult(
                success=False,
                error_type="empty",
                error_message="生成的代码为空或过短",
                error_details=f"代码长度: {len(generated_code)} 字符"
            )
        
        syntax_result = self._check_syntax(generated_code)
        if not syntax_result.success:
            return syntax_result
        
        parse_result = self._parse(generated_code)
        if not parse_result.success:
            return RoundtripValidationResult(
                success=False,
                error_type=parse_result.error_type or "execution",
                error_message=parse_result.error_message,
                error_details=parse_result.error_details,
                line_number=parse_result.line_number,
            )
        
        parsed_model = parse_result.parsed_model
        if len(graph_model.nodes) > 0 and (not parsed_model or len(parsed_model.nodes) == 0):
            return RoundtripValidationResult(
                success=False,
                error_type="empty",
                error_message="解析后的节点图为空",
                error_details=f"原始节点数: {len(graph_model.nodes)}, 解析后节点数: 0"
            )
        
        return RoundtripValidationResult(success=True)
    
    def _generate_code(self, graph_model: GraphModel, metadata: Optional[Dict]) -> str:
        """生成可执行的类结构 Python 代码"""
        return self._code_generator.generate_code(graph_model, metadata)
    
    def _check_syntax(self, generated_code: str) -> RoundtripValidationResult:
        """检查代码的 Python 语法"""
        try:
            compile(generated_code, "<roundtrip>", "exec")
        except SyntaxError as exc:
            line_info = f"第 {exc.lineno} 行" if exc.lineno else "未知行"
            return RoundtripValidationResult(
                success=False,
                error_type="syntax",
                error_message="生成的代码未通过 Python 语法检查",
                error_details=f"{line_info}: {exc.msg}",
                line_number=exc.lineno,
            )
        return RoundtripValidationResult(success=True)
    
    def _parse(self, generated_code: str) -> 'ParseResult':
        """尝试解析生成的代码"""
        from engine.graph.graph_code_parser import GraphParseError

        parser = self._get_parser()
        with _temporary_graph_file("roundtrip_parse_", generated_code) as temp_file:
            try:
                graph_model, _ = parser.parse_file(temp_file)
            except GraphParseError as exc:
                return ParseResult(
                    success=False,
                    error_type="execution",
                    error_message=str(exc),
                    error_details=getattr(exc, "message", str(exc)),
                    line_number=getattr(exc, "line_number", None),
                )
            except Exception as exc:
                return ParseResult(
                    success=False,
                    error_type="execution",
                    error_message=str(exc),
                    error_details=repr(exc),
                )
        return ParseResult(success=True, parsed_model=graph_model)

    def _get_parser(self):
        if self._parser is None:
            from engine.graph.graph_code_parser import GraphCodeParser

            self._parser = GraphCodeParser(
                self.workspace_path,
                node_library=self.node_library,
                verbose=False,
            )
        return self._parser


@contextmanager
def _temporary_graph_file(prefix: str, generated_code: str):
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        temp_file = temp_dir / "graph_roundtrip.py"
        temp_file.write_text(generated_code, encoding="utf-8")
        yield temp_file
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@dataclass
class ParseResult:
    success: bool
    error_type: str = ""
    error_message: str = ""
    error_details: str = ""
    line_number: Optional[int] = None
    parsed_model: Optional[GraphModel] = None


