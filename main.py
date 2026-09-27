"""
A股多因子选股平台 - FastAPI 后端
包含用户注册、登录、JWT认证
"""

import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic_settings import BaseSettings

# ========== 配置 ==========
class Settings(BaseSettings):
    secret_key: str = secrets.token_hex(32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7天
    database_path: str = os.path.join(os.path.dirname(__file__), "users.db")

settings = Settings()

# ========== 数据库 ==========
def get_db():
    return sqlite3.connect(settings.database_path, detect_types=sqlite3.PARSE_DECLTYPES)

@contextmanager
def get_cursor():
    db = get_db()
    try:
        cursor = db.cursor()
        yield cursor
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    with get_cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_vip INTEGER DEFAULT 0,
                vip_expire TEXT DEFAULT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS login_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

# ========== 密码 ==========
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

# ========== JWT ==========
security = HTTPBearer(auto_error=False)

def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token无效或已过期")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    token_data = decode_token(credentials.credentials)
    username = token_data.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token无效")
    with get_cursor() as c:
        c.execute("SELECT id, username, email, is_vip, vip_expire, created_at FROM users WHERE username=?", (username,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="用户不存在")
        return {
            "id": row[0], "username": row[1], "email": row[2],
            "is_vip": bool(row[3]), "vip_expire": row[4], "created_at": row[5]
        }

def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    if not credentials:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None

# ========== Pydantic 模型 ==========
class RegisterIn(BaseModel):
    username: str
    email: str
    password: str

class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_vip: bool
    vip_expire: Optional[str]
    created_at: str

# ========== FastAPI App ==========
app = FastAPI(title="A股多因子选股平台 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

# ========== 认证接口 ==========

@app.post("/api/auth/register", response_model=TokenOut, tags=["认证"])
def register(body: RegisterIn):
    """用户注册"""
    if len(body.username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少3个字符")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6个字符")
    if "@" not in body.email:
        raise HTTPException(status_code=400, detail="请输入有效邮箱")

    with get_cursor() as c:
        c.execute("SELECT id FROM users WHERE username=?", (body.username,))
        if c.fetchone():
            raise HTTPException(status_code=409, detail="用户名已存在")
        c.execute("SELECT id FROM users WHERE email=?", (body.email,))
        if c.fetchone():
            raise HTTPException(status_code=409, detail="邮箱已被注册")

        hashed = hash_password(body.password)
        c.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
            (body.username, body.email, hashed)
        )
        user_id = c.lastrowid

    token = create_token({"sub": body.username})
    return TokenOut(
        access_token=token,
        user={"id": user_id, "username": body.username, "email": body.email, "is_vip": False, "vip_expire": None}
    )

@app.post("/api/auth/login", response_model=TokenOut, tags=["认证"])
def login(body: LoginIn):
    """用户登录"""
    with get_cursor() as c:
        c.execute("SELECT id, username, email, password_hash, is_vip, vip_expire, created_at FROM users WHERE username=?", (body.username,))
        row = c.fetchone()
        if not row or not verify_password(body.password, row[3]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        token = create_token({"sub": row[1]})
        return TokenOut(
            access_token=token,
            user={"id": row[0], "username": row[1], "email": row[2], "is_vip": bool(row[4]), "vip_expire": row[5]}
        )

@app.get("/api/auth/me", response_model=UserOut, tags=["认证"])
def me(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserOut(
        id=user["id"], username=user["username"], email=user["email"],
        is_vip=user["is_vip"], vip_expire=user["vip_expire"],
        created_at=str(user["created_at"])
    )

@app.post("/api/auth/logout", tags=["认证"])
def logout(user: dict = Depends(get_current_user)):
    """退出登录（前端删除token即可，这里做记录）"""
    return {"msg": "已退出登录"}

# ========== 健康检查 ==========
@app.get("/api/health", tags=["系统"])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# ========== 前端文件服务 ==========
@app.get("/{path:path}", tags=["前端"])
def serve_frontend(path: str):
    """非API路径全部重定向到前端，由前端路由处理"""
    # 静态资源直接返回
    static_extensions = ['.js', '.css', '.png', '.jpg', '.ico', '.woff', '.woff2']
    if any(path.endswith(ext) for ext in static_extensions):
        file_path = os.path.join(os.path.dirname(__file__), "static", path)
        if os.path.exists(file_path):
            from fastapi.responses import FileResponse
            return FileResponse(file_path)
    # 其余重定向到 index.html（SPA）
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    return {"error": "static/index.html not found"}

@app.get("/", tags=["前端"])
def root():
    """根路径返回前端"""
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    return {"msg": "A股多因子选股平台 API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
