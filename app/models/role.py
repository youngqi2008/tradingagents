"""小程序用户角色（与会员等级独立）"""

from typing import List, Optional

from pydantic import BaseModel, Field


# 内置角色编码（种子数据）
ROLE_NORMAL = "normal"
ROLE_RISK_OFFICER = "risk_officer"

DEFAULT_MP_ROLE = ROLE_NORMAL

# 启动种子；运营可在后台增改
DEFAULT_MP_ROLES: List[dict] = [
    {
        "code": ROLE_NORMAL,
        "name": "普通",
        "description": "默认小程序用户角色",
        "sort_order": 0,
        "is_default": True,
    },
    {
        "code": ROLE_RISK_OFFICER,
        "name": "风控专员",
        "description": "可授予风控相关能力的专员角色",
        "sort_order": 10,
        "is_default": False,
    },
]

# 兼容旧调用的静态兜底（DB 未就绪时）
MP_ROLES = DEFAULT_MP_ROLES
MP_ROLE_CODES = {r["code"] for r in DEFAULT_MP_ROLES}
MP_ROLE_NAME_MAP = {r["code"]: r["name"] for r in DEFAULT_MP_ROLES}


class RoleInfo(BaseModel):
    id: Optional[str] = None
    code: str
    name: str
    description: str = ""
    sort_order: int = 0
    is_default: bool = False
    is_active: bool = True
    user_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=32, description="英文编码，如 risk_officer")
    description: str = Field(default="", max_length=512)
    sort_order: int = 0
    is_default: bool = False


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=512)
    sort_order: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(..., description="角色编码")


class GrantRoleRequest(BaseModel):
    user_ids: List[str] = Field(..., min_length=1, description="小程序用户 ID 列表")
    role: str = Field(..., description="要授予的角色编码")


def role_display_name(role: Optional[str], name_map: Optional[dict] = None) -> str:
    if not role:
        role = DEFAULT_MP_ROLE
    if name_map and role in name_map:
        return name_map[role]
    return MP_ROLE_NAME_MAP.get(role, role)


def list_mp_roles() -> List[RoleInfo]:
    """静态兜底列表（优先使用 role_service.list_roles）"""
    return [RoleInfo(**{k: v for k, v in r.items() if k in RoleInfo.model_fields}) for r in DEFAULT_MP_ROLES]


def is_valid_mp_role(role: Optional[str]) -> bool:
    """静态校验兜底；正式路径请用 role_service.is_valid_role"""
    return bool(role) and role in MP_ROLE_CODES
