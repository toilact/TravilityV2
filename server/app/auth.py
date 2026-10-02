import datetime as dt

import bcrypt
import jwt
import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import settings
from app.db import get_conn

router = APIRouter(prefix="/auth")
bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def bcrypt_limit(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("Mật khẩu tối đa 72 byte (khoảng 24 ký tự có dấu)")
        return v


class RegisterBody(Credentials):
    full_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, v: str) -> str:
        value = " ".join(v.split())
        if not value:
            raise ValueError("Họ và tên không được để trống")
        return value

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        digits = "".join(c for c in v if c.isdigit())
        if not 9 <= len(digits) <= 15:
            raise ValueError("Số điện thoại không hợp lệ")
        return digits


class AccountUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, v: str) -> str:
        return RegisterBody.clean_full_name(v)

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        return RegisterBody.clean_phone(v)


def make_token(user_id: int) -> str:
    exp = dt.datetime.now(dt.UTC) + dt.timedelta(days=7)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    if cred is None:
        raise HTTPException(401, "Cần đăng nhập")
    try:
        return int(jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])["sub"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Phiên đăng nhập hết hạn, đăng nhập lại nhé") from None


@router.post("/register", status_code=201)
def register(body: RegisterBody, conn=Depends(get_conn)):
    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    try:
        row = conn.execute(
            "INSERT INTO users(email, password_hash, full_name, phone) VALUES (%s, %s, %s, %s) RETURNING id",
            (body.email.lower(), pw_hash, body.full_name, body.phone),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Email đã được đăng ký") from None
    return {"token": make_token(row["id"])}


@router.post("/login")
def login(body: Credentials, conn=Depends(get_conn)):
    row = conn.execute("SELECT id, password_hash FROM users WHERE email = %s", (body.email.lower(),)).fetchone()
    if not row or not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise HTTPException(401, "Sai email hoặc mật khẩu")
    return {"token": make_token(row["id"])}


@router.get("/me")
def me(user_id: int = Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(
        "SELECT id, email, full_name, phone FROM users WHERE id = %s", (user_id,)
    ).fetchone()


@router.put("/me")
def update_me(body: AccountUpdate, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(
        "UPDATE users SET full_name = %s, phone = %s WHERE id = %s "
        "RETURNING id, email, full_name, phone",
        (body.full_name, body.phone, user_id),
    ).fetchone()
