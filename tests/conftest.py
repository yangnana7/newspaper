import os

# Ensure fixed environment for imports in CI and local runs
os.environ.setdefault("DATABASE_URL", "postgresql://127.0.0.1/newshub")
os.environ.setdefault("APP_BIND_HOST", "127.0.0.1")
os.environ.setdefault("APP_BIND_PORT", "3011")
os.environ.setdefault("CI", "true")

