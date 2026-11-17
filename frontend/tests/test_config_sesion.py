"""Dónde se guarda la sesión según REDIS_URL (no se conecta a Redis ni a AWS)."""
import pytest

from config import Config


def test_sin_redis_url_usa_archivos(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    c = Config()
    assert c.SESSION_TYPE == "cachelib"


def test_con_redis_url_usa_redis(monkeypatch):
    # redis.from_url no abre la conexión hasta el primer comando.
    monkeypatch.setenv("REDIS_URL", "rediss://default:clave@redis-simulado.invalid:6379")
    c = Config()
    assert c.SESSION_TYPE == "redis"
    assert c.SESSION_REDIS.connection_pool.connection_kwargs["host"] == "redis-simulado.invalid"


def test_redis_sin_cifrar_se_rechaza(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://default:clave@redis-simulado.invalid:6379")
    with pytest.raises(RuntimeError, match="rediss://"):
        Config()
