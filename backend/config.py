from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str = "dev-secret-key"
    allowed_origins: str = "http://localhost:5173"
    max_upload_rows: int = 5000
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "hr"
    mysql_database: str = "treasury_db"

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def sqlalchemy_database_url(self):
        if self.database_url_override:
            return self.database_url_override

        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


settings = Settings()
