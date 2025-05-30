"""
Базовые тесты для проверки настройки окружения.
"""

import sys

import pytest


def test_imports():
    """Проверка возможности импорта основных модулей."""
    try:
        # Проверяем, доступны ли модули, не используя их напрямую
        import importlib.util

        assert importlib.util.find_spec("app") is not None, "Модуль app недоступен"
        assert importlib.util.find_spec("src") is not None, "Модуль src недоступен"
    except ImportError as e:
        pytest.fail(f"Ошибка импорта: {e}")


def test_environment(test_config):
    """Проверка, что тестовая конфигурация загружена."""
    assert test_config["test_mode"] is True
    assert test_config["db_path"] == ":memory:"


def test_python_version():
    """Проверка версии Python."""
    assert sys.version_info >= (3, 12), "Требуется Python 3.12 или выше"
