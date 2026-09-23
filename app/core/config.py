"""应用配置：把所有配置集中在这里，用 pydantic 做类型校验。

为什么这么做（关键）：
你以前的练习代码，API key 直接硬编码在 .py 文件里。坏处有三：
1. key 写在代码里，一上传 GitHub 就泄露；
2. 换 key 要改代码，容易漏；
3. 缺 key 时程序跑到一半才崩，报错看不懂。

这里用 pydantic-settings 解决：配置写在 .env 文件里，代码只读；
缺了关键项，程序「启动那一刻」就报错，并告诉你该去哪申请。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigError

# 缺 key 时给人看的提示（比一句冷冰冰的 "validation error" 有用得多）
_KEY_HINT = (
    "缺少 SILICONFLOW_API_KEY。\n"
    "  打开 https://cloud.siliconflow.cn 注册 → 左侧「API 密钥」→ 新建，\n"
    "  把 key 填进项目根目录的 .env 文件：SILICONFLOW_API_KEY=sk-xxxxxx"
)


class Settings(BaseSettings):
    """所有配置项。类里的每个字段名，会自动去 .env 里找同名大写变量。"""

    # 这一行告诉 pydantic：从 .env 文件读配置，找不到的字段忽略
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用基础 ----
    app_name: str = "finance-agent"
    app_env: str = "dev"
    log_level: str = "INFO"

    # ---- 模型服务商：硅基流动 ----
    siliconflow_api_key: str = Field(default="", description="硅基流动 API Key")
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    # 模型名不写死：服务商随时上下架模型，改 .env 即可切换
    siliconflow_chat_model: str = "Qwen/Qwen3-8B"
    siliconflow_embed_model: str = "BAAI/bge-m3"

    # ---- 数据库：账本存哪 ----
    # SQLite 单文件，零配置；后面要上 PostgreSQL 只改这一行
    database_url: str = "sqlite:///data/ledger.db"

    # ---- RAG：企业私有知识库 ----
    chroma_dir: str = "./data/chroma"
    chunk_size: int = 500
    chunk_overlap: int = 50

    @field_validator("siliconflow_api_key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        """校验 key：空了就直接抛错，并附上人话提示。"""
        value = value.strip()
        if not value:
            raise ValueError(_KEY_HINT)
        return value

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """全局唯一的配置对象。第一次调用时完成校验，之后都返回缓存。

    lru_cache 保证只读一次 .env、只校验一次，重复调用不会重复读盘。
    """
    try:
        return Settings()
    except ValidationError as exc:
        # 把 pydantic 的报错转成我们的 ConfigError，信息更清楚
        errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise ConfigError("配置校验失败：\n  - " + "\n  - ".join(errors)) from exc
