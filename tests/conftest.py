"""
Конфигурационный файл для pytest с общими фикстурами.
"""

import os
import sys
import pytest
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH для импорта модулей
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def test_config():
    """
    Фикстура с тестовой конфигурацией.
    """
    return {
        "test_mode": True,
        "db_path": ":memory:",
    }
