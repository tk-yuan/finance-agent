"""pytest 全局配置。

**关键**：测试必须使用独立的临时数据库，绝不能碰生产数据库。
这里在导入 app 之前就把 DATABASE_URL 指向临时文件——
因为数据库引擎在 app.db.session 被 import 时就会创建，晚设置就来不及了。

（教训：早期版本没做隔离，跑一次测试就把真实账本清空了。）
"""

from __future__ import annotations

import os
import tempfile

# ---- 必须在任何 app 导入之前执行 ----
_TMP_DIR = tempfile.mkdtemp(prefix="finance_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test.db"
os.environ["CHROMA_DIR"] = f"{_TMP_DIR}/chroma"
os.environ.setdefault("SILICONFLOW_API_KEY", "sk-test-placeholder")
