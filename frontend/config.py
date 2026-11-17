"""Configuración leída de variables de entorno (archivo .env, fuera de Git).

Flask no necesita ni debe tener JWT_SECRET, credenciales de BD ni de AWS.
"""
import os
from datetime import timedelta
from pathlib import Path

from cachelib import FileSystemCache
from dotenv import load_dotenv

from constantes import SESION_HORAS

CARPETA = Path(__file__).resolve().parent
load_dotenv(CARPETA / ".env")


def _obligatoria(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (ver .env.example)")
    return valor


def _booleana(nombre, por_defecto):
    valor = os.environ.get(nombre)
    if valor is None or not valor.strip():
        return por_defecto
    return valor.strip().lower() in ("1", "true", "si", "sí")


class Config:
    def __init__(self):
        self.SECRET_KEY = _obligatoria("SECRET_KEY")
        if len(self.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY debe tener 32 caracteres o más")

        url = _obligatoria("API_BASE_URL").rstrip("/")
        if not url.startswith("https://"):
            raise RuntimeError("API_BASE_URL debe empezar con https://")
        self.API_BASE_URL = url

        # Flask-Session: la sesión vive del lado del servidor; la cookie solo
        # lleva un id firmado. El JWT nunca viaja al navegador.
        # Con REDIS_URL (Vercel + Upstash) se guarda en Redis, porque en Vercel
        # el disco es de solo lectura y no se comparte entre instancias.
        # Sin REDIS_URL (ejecución local) se guarda en archivos.
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if redis_url:
            if not redis_url.startswith("rediss://"):
                raise RuntimeError("REDIS_URL debe empezar con rediss:// (conexión cifrada)")
            import redis
            self.SESSION_TYPE = "redis"
            self.SESSION_REDIS = redis.from_url(
                redis_url, socket_timeout=5, socket_connect_timeout=5,
                health_check_interval=30)
        else:
            self.SESSION_TYPE = "cachelib"
            self.SESSION_CACHELIB = FileSystemCache(
                cache_dir=str(CARPETA / "flask_session"), threshold=500, mode=0o600)
        self.SESSION_USE_SIGNER = True
        self.SESSION_PERMANENT = True
        self.PERMANENT_SESSION_LIFETIME = timedelta(hours=SESION_HORAS)

        self.SESSION_COOKIE_NAME = "smavib_sesion"
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = "Lax"
        # Secure siempre, salvo que se apague a propósito para pruebas locales.
        self.SESSION_COOKIE_SECURE = _booleana("COOKIE_SECURE", True)

        # CSRF (Flask-WTF): el token dura lo mismo que la sesión.
        self.WTF_CSRF_TIME_LIMIT = SESION_HORAS * 3600

        self.MAX_CONTENT_LENGTH = 1024 * 1024   # 1 MB por petición
