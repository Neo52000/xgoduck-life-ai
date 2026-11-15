from dataclasses import dataclass
from pathlib import Path
import os


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    admin_user: str
    admin_password: str
    robot_api_key: str
    openai_api_key: str = ""
    vision_model: str = "gpt-4.1-mini"
    auto_vision: bool = False
    max_ai_calls_per_day: int = 20
    max_image_bytes: int = 5 * 1024 * 1024
    allow_wikipedia: bool = True
    remote_reference_matching: bool = False
    max_reference_images: int = 8
    max_research_per_cycle: int = 2
    code_revision: str = "lifeai-3.3.0"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/lifeai.sqlite3"),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            admin_user=os.getenv("ADMIN_USER", "admin"),
            admin_password=os.getenv("ADMIN_PASSWORD", ""),
            robot_api_key=os.getenv("ROBOT_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            vision_model=os.getenv("VISION_MODEL", "gpt-4.1-mini"),
            auto_vision=truthy(os.getenv("AUTO_VISION", "false")),
            max_ai_calls_per_day=int(os.getenv("MAX_AI_CALLS_PER_DAY", "20")),
            allow_wikipedia=truthy(os.getenv("ALLOW_WIKIPEDIA", "true")),
            remote_reference_matching=truthy(os.getenv("REMOTE_REFERENCE_MATCHING", "false")),
            max_reference_images=int(os.getenv("MAX_REFERENCE_IMAGES", "8")),
            max_research_per_cycle=int(os.getenv("MAX_RESEARCH_PER_CYCLE", "2")),
            code_revision=os.getenv("LIFEAI_CODE_REVISION", "lifeai-3.3.0"),
        )

    def validate(self) -> None:
        if not self.admin_user.strip():
            raise ValueError("ADMIN_USER ne peut pas être vide")
        if len(self.admin_password) < 12 or any(s in self.admin_password.upper() for s in ("CHANGE_ME", "REPLACE_WITH", "CHANGEME")):
            raise ValueError("Configurer ADMIN_PASSWORD avec un secret d'au moins 12 caractères")
        if len(self.robot_api_key) < 24 or any(s in self.robot_api_key.upper() for s in ("CHANGE_ME", "REPLACE_WITH", "CHANGEME")):
            raise ValueError("Configurer ROBOT_API_KEY avec un secret aléatoire d'au moins 24 caractères")
        if not 0 <= self.max_ai_calls_per_day <= 500:
            raise ValueError("MAX_AI_CALLS_PER_DAY doit être entre 0 et 500")
        if not 0 <= self.max_reference_images <= 16:
            raise ValueError("MAX_REFERENCE_IMAGES doit être entre 0 et 16")
        if not 4 <= len(self.code_revision) <= 80 or not all(c.isalnum() or c in ".-_" for c in self.code_revision):
            raise ValueError("LIFEAI_CODE_REVISION invalide")
        if not 0 <= self.max_research_per_cycle <= 5:
            raise ValueError("MAX_RESEARCH_PER_CYCLE doit être entre 0 et 5")
