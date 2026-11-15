import os
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class Config:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./tfwatch.db"))
    public_url: str = field(default_factory=lambda: os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/"))
    encryption_key: str = field(default_factory=lambda: os.getenv("ENCRYPTION_KEY", ""))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_mode: str = field(default_factory=lambda: os.getenv("SMTP_MODE", "starttls"))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", ""))
    source_url: str = field(default_factory=lambda: os.getenv("SOURCE_URL", ""))
    static_dir: Path = field(default_factory=lambda: Path(os.getenv(
        "STATIC_DIR", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    )))

    @property
    def secure_cookie(self):
        return self.public_url.startswith("https://")

    def cipher(self):
        return Fernet(self.encryption_key.encode())
