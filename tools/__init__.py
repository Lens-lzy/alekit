"""工具集合。新增工具：在此注册即可出现在左侧工具栏。"""

from tools.base import Tool  # noqa: F401
from tools.converter_tool import ConverterTool
from tools.ppt_compress_tool import PptCompressTool

# 工具注册表 —— 加新工具只改这一行
TOOLS: list[type[Tool]] = [
    ConverterTool,
    PptCompressTool,
]
