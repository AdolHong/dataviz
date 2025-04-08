from fastapi import APIRouter, Request, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
import hashlib
import jwt
import datetime
from secrets import token_hex
from typing import Dict, Optional
from pydantic import BaseModel
from utils.fs_utils import FILE_TOKEN_PATH

# 创建Router
router = APIRouter(tags=["auth"], prefix="/api/auth")

# 用于存储用户凭证的字典，实际应用中应使用数据库
# 这里密码已经预先用SHA256哈希过（实际情况下应该加盐）
USERS = {
    "adol": "f09a31c2bb20aeee1e1ce6639c32226098bdaaf949b247b775f845aafadda2bd",  # adol
    # "user": "04f8996da763b7a969b1028ee3007569eaf3a635486ddab211d512c85b9df8fb",   # user
}
# 活跃token列表（用于验证和注销）
ACTIVE_TOKENS = {}

# 用于JWT签名的密钥
# SECRET_KEY = token_hex(32)
# 固定下来, 多个进程共用一个SECRET_KEY
SECRET_KEY = 'cd3fd8928370f07e726ed4a519ffdc3b3da24b66819c55595ad7e4c7c2bb36b3'


def generate_sha256_hash(password):
    """
    # 示例用法
    password = "your_password"
    hashed_password = generate_sha256_hash(password)
    print(f"SHA256哈希后的密码：{hashed_password}")


    """
    # 创建SHA256哈希对象
    sha256_hash = hashlib.sha256()

    # 将密码转换为字节并更新哈希对象
    sha256_hash.update(password.encode('utf-8'))

    # 获取十六进制的哈希值
    hashed_password = sha256_hash.hexdigest()

    return hashed_password


# 定义请求和响应模型
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    username: Optional[str] = None


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """处理用户登录请求"""
    username = request.username
    password = request.password  # 客户端已哈希的密码

    # 验证用户名和密码
    if username not in USERS or USERS[username] != password:
        return TokenResponse(success=False, message="用户名或密码错误")

    # 生成JWT令牌
    exp_time = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    payload = {
        "username": username,
        "exp": exp_time
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    # 保存token到活跃列表
    ACTIVE_TOKENS[token] = username

    return TokenResponse(
        success=True,
        message="登录成功",
        token=token,
        username=username
    )


@router.get("/verify", response_model=TokenResponse)
async def verify_token(authorization: Optional[str] = Header(None)):
    """验证token是否有效"""
    if not authorization or not authorization.startswith('Bearer '):
        return TokenResponse(success=False, message="未提供认证令牌")

    token = authorization.split(' ')[1]

    # 验证token是否在活跃列表中
    if token not in ACTIVE_TOKENS:
        return TokenResponse(success=False, message="令牌已失效")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = payload.get('username')

        return TokenResponse(
            success=True,
            message="令牌有效",
            username=username
        )
    except jwt.ExpiredSignatureError:
        # 移除过期token
        if token in ACTIVE_TOKENS:
            del ACTIVE_TOKENS[token]
        return TokenResponse(success=False, message="令牌已过期")
    except jwt.InvalidTokenError:
        return TokenResponse(success=False, message="无效的令牌")


@router.post("/logout", response_model=TokenResponse)
async def logout(authorization: Optional[str] = Header(None)):
    """注销用户登录"""
    if not authorization or not authorization.startswith('Bearer '):
        return TokenResponse(success=False, message="未提供认证令牌")

    token = authorization.split(' ')[1]

    # 从活跃token列表中移除
    if token in ACTIVE_TOKENS:
        del ACTIVE_TOKENS[token]
        return TokenResponse(success=True, message="已成功注销")

    return TokenResponse(success=False, message="令牌不存在或已失效")

# 验证token的依赖函数


async def verify_token_dependency(authorization: Optional[str] = Header(None)):
    """用于FastAPI依赖注入的验证函数"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = authorization.split(' ')[1]

    # 验证token是否在活跃列表中
    if token not in ACTIVE_TOKENS:
        raise HTTPException(status_code=401, detail="令牌已失效")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get('username')
    except jwt.ExpiredSignatureError:
        # 移除过期token
        if token in ACTIVE_TOKENS:
            del ACTIVE_TOKENS[token]
        raise HTTPException(status_code=401, detail="令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的令牌")

# 用于兼容之前代码的函数


def token_required(f):
    """
    保留此函数用于兼容现有代码，但不再使用装饰器模式
    应使用FastAPI的依赖注入模式：Depends(verify_token_dependency)
    """
    return f
