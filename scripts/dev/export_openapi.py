"""导出 FastAPI OpenAPI 到 apps/web/api/schema.json（ADR 0071 单一来源）。

用法：uv run --package medicalrag-api python scripts/dev/export_openapi.py
CI 契约门禁：openapi-typescript --check 检测漂移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "apps" / "web" / "api" / "schema.json"


def main() -> None:
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite://",
            operator_emails="ops@clinic.example",
            object_root=str(ROOT / ".objects"),
        )
    )
    schema = app.openapi()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI 已导出: {OUT} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    sys.exit(main())
