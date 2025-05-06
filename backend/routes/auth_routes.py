from fastapi import APIRouter, Request, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
import hashlib
import jwt
import datetime
import os
import json
import asyncio
import aiofiles
from secrets import token_hex
from typing import Dict, Optional
from pydantic import BaseModel
from utils.fs_utils import FILE_TOKEN_PATH

# 创建Router
router = APIRouter(tags=["auth"], prefix="/api/auth")


# 用于JWT签名的密钥
# SECRET_KEY = token_hex(32)
# 固定下来, 多个进程共用一个SECRET_KEY
SECRET_KEY = 'cd3fd8928370f07e726ed4a519ffdc3b3da24b66819c55595ad7e4c7c2bb36b3'

# 用于存储用户凭证的字典，实际应用中应使用数据库
USERS = {
    "adol": "f09a31c2bb20aeee1e1ce6639c32226098bdaaf949b247b775f845aafadda2bd",  # adol
    "evans": 'b0a85ea55612378ea58b08566dc8f36828af614f56edccf76ac4f0026381d3a2',  # evans
    "barry": '4466d77ec4cef2cc72774eb1f294f0bb9a5e13efba81cfcf4007bdfe9ce2a244',  # barry
    "anderson": '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92'  # anderson
}
# 活跃token列表（用于验证和注销）
ACTIVE_TOKENS = {}


def generate_sha256_hash(password):
    """
    生成密码的SHA256哈希值
    """
    # 创建SHA256哈希对象
    sha256_hash = hashlib.sha256()
    sha256_hash.update(password.encode('utf-8'))
    return sha256_hash.hexdigest()

# 定义请求和响应模型


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    username: Optional[str] = None


async def get_active_tokens() -> Dict[str, str]:
    """
    异步获取活跃的 token

    Returns:
        Dict[str, str]: token 到用户名的映射
    """
    tokens_file = os.path.join(FILE_TOKEN_PATH, "active_tokens.json")

    # 确保目录存在
    os.makedirs(FILE_TOKEN_PATH, exist_ok=True)

    if not os.path.exists(tokens_file):
        return {}

    try:
        async with aiofiles.open(tokens_file, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {}


async def save_active_tokens(tokens: Dict[str, str]):
    """
    异步保存活跃的 token

    Args:
        tokens (Dict[str, str]): token 到用户名的映射
    """
    tokens_file = os.path.join(FILE_TOKEN_PATH, "active_tokens.json")

    try:
        async with aiofiles.open(tokens_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(tokens, ensure_ascii=False, indent=2))
    except IOError as e:
        print(f"保存 token 时发生错误: {e}")


async def is_user_already_logged_in(username: str) -> bool:
    """
    检查用户是否已经登录

    Args:
        username (str): 用户名

    Returns:
        bool: 用户是否已登录
    """
    active_tokens = await get_active_tokens()
    return username in active_tokens.values()


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """处理用户登录请求"""
    username = request.username
    password = request.password  # 客户端已哈希的密码

    # 检查用户是否已登录， 允许多次登陆
    if await is_user_already_logged_in(username):
        print(f"用户 {username} 已在其他地方登录")

    # 验证用户名和密码
    if username not in USERS or USERS[username] != password:
        return TokenResponse(success=False, message="用户名或密码错误")

    # 生成JWT令牌
    exp_time = datetime.datetime.utcnow() + datetime.timedelta(hours=24 * 30)  # token 30天过期
    payload = {
        "username": username,
        "exp": exp_time
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    # 获取并更新活跃 token
    active_tokens = await get_active_tokens()
    active_tokens[token] = username
    await save_active_tokens(active_tokens)

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

    # 获取活跃 token
    active_tokens = await get_active_tokens()

    # 验证token是否在活跃列表中
    if token not in active_tokens:
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
        if token in active_tokens:
            del active_tokens[token]
            await save_active_tokens(active_tokens)
        return TokenResponse(success=False, message="令牌已过期")
    except jwt.InvalidTokenError:
        return TokenResponse(success=False, message="无效的令牌")


@router.post("/logout", response_model=TokenResponse)
async def logout(authorization: Optional[str] = Header(None)):
    """注销用户登录"""
    if not authorization or not authorization.startswith('Bearer '):
        return TokenResponse(success=False, message="未提供认证令牌")

    token = authorization.split(' ')[1]

    # 获取并更新活跃 token
    active_tokens = await get_active_tokens()

    # 从活跃token列表中移除
    if token in active_tokens:
        del active_tokens[token]
        await save_active_tokens(active_tokens)
        return TokenResponse(success=True, message="已成功注销")

    return TokenResponse(success=False, message="令牌不存在或已失效")


async def verify_token_dependency(authorization: Optional[str] = Header(None)):
    """用于FastAPI依赖注入的验证函数"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = authorization.split(' ')[1]

    # 获取活跃 token
    active_tokens = await get_active_tokens()

    # 验证token是否在活跃列表中
    if token not in active_tokens:
        raise HTTPException(status_code=401, detail="令牌已失效")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get('username')
    except jwt.ExpiredSignatureError:
        # 移除过期token
        if token in active_tokens:
            del active_tokens[token]
            await save_active_tokens(active_tokens)
        raise HTTPException(status_code=401, detail="令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的令牌")


def token_required(f):
    """
    保留此函数用于兼容现有代码，但不再使用装饰器模式
    应使用FastAPI的依赖注入模式：Depends(verify_token_dependency)
    """
    return f
