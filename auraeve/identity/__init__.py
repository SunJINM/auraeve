"""统一身份域：跨渠道身份解析与关系管理。"""

from .service import IdentityService
from .resolver import IdentityResolver

__all__ = ["IdentityService", "IdentityResolver"]
