from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Test API"
    admin_email: str = "admin@example.com"
    items_per_user: int = 50


model_config = SettingsConfigDict(env_file=".env")
