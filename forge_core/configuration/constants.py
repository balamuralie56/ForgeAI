from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

CONFIG_DIR = ROOT_DIR / "config"

DATA_DIR = ROOT_DIR / "forge_data"

LOG_DIR = DATA_DIR / "logs"

CACHE_DIR = DATA_DIR / "cache"

DATABASE_DIR = DATA_DIR / "databases"

EMBEDDING_DIR = DATA_DIR / "embeddings"

BACKUP_DIR = DATA_DIR / "backups"