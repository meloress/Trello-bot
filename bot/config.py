from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bot_token: str
    trello_api_key: str
    trello_token: str
    database_url: str
    web_port: int = 3000
    # Mini App HTTP serveri (bot jarayoni ichida, aiohttp). Railway public
    # domain yoqilganda $PORT'ni beradi — shu o'zgaruvchi nomi bilan mos keladi.
    port: int = 8080
    miniapp_base_url: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def async_database_url(self) -> str:
        """DATABASE_URL Railway'ning standart postgresql:// sxemasida keladi;
        SQLAlchemy asyncio kengaytmasi esa asyncpg drayverini talab qiladi."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


settings = Settings()
