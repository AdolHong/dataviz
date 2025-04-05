# 导入所有路由
from . import fs_routes
from . import report_routes
from . import query_routes
from . import artifact_routes
from . import auth_routes

# 提供路由模块
__all__ = ['fs_routes', 'report_routes', 'query_routes', 'artifact_routes', 'auth_routes']
