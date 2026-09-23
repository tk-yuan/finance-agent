"""配置层测试：验证缺 key 能尽早报错。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-xxx")
    s = Settings(_env_file=None)
    assert s.vector_store if hasattr(s, "vector_store") else True
    assert s.siliconflow_chat_model == "Qwen/Qwen3-8B"
