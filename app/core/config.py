from typing import Optional
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Servidor
    PORT: int = 8087
    HOST: str = "0.0.0.0"

    # Identificador del servicio en el Autenticador Central
    SERVICE_KEY: str = "conmijuegos"

    # Base de datos MongoDB (soporta MONGO_URI completo con base lógica o MONGODB_URL + MONGODB_DB_NAME)
    MONGO_URI: Optional[str] = None
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "conmijuegos_db"

    # JWT & Seguridad (Obligatorio desde .env, debe coincidir con Autenticador)
    JWT_SECRET: str
    JWT_EXPIRATION_DAYS: int = 180
    FRONTEND_URL: str = "https://cognijuegos.asistodo.com.ar"

    # Microservicio Autenticador Central (SSOT)
    AUTH_SERVICE_URL: str = "https://autenticacion.asistodo.com.ar"

    # RAE API (Wordle / Desafíos)
    RAE_API_KEY: Optional[str] = None

    # Correo SMTP / Brevo (Opcional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_FROM_NAME: str = "CogniJuegos"

    # Administrador por defecto para seed inicial
    ADMIN_DEFAULT_EMAIL: str = "admin@sistemas.com"
    ADMIN_DEFAULT_PASSWORD: str = "admin123"
    ADMIN_DEFAULT_NAME: str = "Operador Sistemas"

    @property
    def effective_mongo_uri(self) -> str:
        if self.MONGO_URI and self.MONGO_URI.strip():
            return self.MONGO_URI.strip()
        return self.MONGODB_URL.strip()

    @property
    def effective_db_name(self) -> str:
        uri = self.effective_mongo_uri
        try:
            parsed = urlparse(uri)
            path_db = (parsed.path or "").lstrip("/").split("/")[0].strip()
            if path_db:
                return path_db
        except Exception:
            pass
        return self.MONGODB_DB_NAME

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

