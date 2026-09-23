"""导入账单 CLI：python -m scripts.import_bill <账单CSV路径>

把支付宝/微信导出的账单 CSV 解析、自动分类、批量导入账本。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import init_db  # noqa: E402
from app.services.bill_importer import import_bill  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("用法：python -m scripts.import_bill <账单CSV路径>")
        sys.exit(1)

    init_db()
    path = sys.argv[1]
    try:
        result = import_bill(path)
    except Exception as exc:
        print(f"✗ 导入失败：{exc}")
        sys.exit(1)

    print(f"✓ 解析 {result['total_parsed']} 笔")
    print(f"✓ 新增 {result['added']} 笔")
    print(f"  跳过重复 {result['skipped_duplicates']} 笔")


if __name__ == "__main__":
    main()
