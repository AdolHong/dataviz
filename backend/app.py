from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn

from routes import fs_routes, report_routes, query_routes, artifact_routes, auth_routes
from utils.fs_utils import DATA_DIR, FS_DATA_FILE, FILE_STORAGE_PATH, save_fs_data, FILE_DELETED_PATH, FILE_CACHE_PATH

app = FastAPI()

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

# 注册路由
app.include_router(fs_routes.router, prefix="/api")
app.include_router(report_routes.router, prefix="/api")
app.include_router(query_routes.router, prefix="/api")
app.include_router(artifact_routes.router, prefix="/api")
app.include_router(auth_routes.router)  # auth_routes已设置prefix="/api/auth"

# 启动初始化：如果数据文件不存在，创建一个空的文件系统
@app.on_event("startup")
def startup_event():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(FILE_STORAGE_PATH):
        os.makedirs(FILE_STORAGE_PATH, exist_ok=True)
    
    if not os.path.exists(FILE_DELETED_PATH):
        os.makedirs(FILE_DELETED_PATH, exist_ok=True)
    
    if not os.path.exists(FILE_CACHE_PATH):
        os.makedirs(FILE_CACHE_PATH, exist_ok=True)
    
    if not os.path.exists(FS_DATA_FILE):
        save_fs_data([])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
