"""
公共 Schema 兼容导出层。

新代码请直接从 app.common.response 导入：
    from app.common.response import ApiResponse, PageData, PaginationParams
"""

from app.common.response import (  # noqa: F401
    ApiResponse,
    ErrorResponse,
    PageData,
    PaginationParams,
)

# 向后兼容别名
PageResponse = PageData
