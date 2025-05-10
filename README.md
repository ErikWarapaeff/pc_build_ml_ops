# PC-Build.AI
Advanced multi-agent application designed to automate and optimize the process of custom PC building

## Системные требования

- Python 3.12 или выше
- Poetry для управления зависимостями
- Docker (опционально, для контейнеризации)

## Инструкции для запуска:
1. **Склонируйте репозиторий:**
   ```bash
   git clone https://github.com/ErikWarapaeff/PC-Build.AI
   ```

2. **Установите Poetry:**
   - **Windows (PowerShell):**
     ```powershell
     (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
     ```
   - **macOS/Linux:**
     ```bash
     curl -sSL https://install.python-poetry.org | python3 -
     ```

3. **Установите зависимости и активируйте виртуальное окружение:**
   ```bash
   poetry install
   poetry shell
   ```

4. **Введите все API ключи:**
   Введите все ключи в  `.env`:
   ```
   OPEN_AI_API_KEY=...
   LANGCHAIN_API_KEY=...
   ```

5. **Запустите приложение на градио:**
   ```bash
   poetry run python src/app.py
   ```

6. **Пользовательские настройки:**
   Измените `config/config.yml` если нужно.




7. **Примеры запросов**

- Привет, что ты умеешь?
- А какая средняя цена на видеокарты с поддержкой 4к?
- Мне нужен игровой ПК чтобы видеокарта поддерживала 4к, мой бюджет 200к
- А насколько в данной системе процессор раскрывает видеокарту?
- Хорошо, а пойдет ли на данной системе игра Cyberpunk 2077?
- Хорошо, найди мне тогда актуальные цены на данную систему.

   


**Агентный граф:**

!['граф'](image.png)

## Инструкции для разработчиков

### Управление зависимостями с Poetry

Проект использует [Poetry](https://python-poetry.org/) для управления зависимостями и создания воспроизводимых сборок.

1. **Добавление новой зависимости:**
   ```bash
   poetry add package-name
   ```

2. **Добавление dev-зависимости:**
   ```bash
   poetry add --group dev package-name
   ```

3. **Обновление зависимостей:**
   ```bash
   poetry update
   ```

4. **Экспорт зависимостей в requirements.txt (если необходимо):**
   ```bash
   poetry export -f requirements.txt --output requirements.txt
   ```

5. **Создание сборки проекта:**
   ```bash
   poetry build
   ```

### Настройка линтеров и форматеров

1. **Установите инструменты для разработки:**
   ```bash
   poetry install --with dev
   ```

2. **Настройте pre-commit хуки:**
   ```bash
   poetry run pre-commit install
   ```

3. **Запуск проверок вручную:**
   ```bash
   # Запуск всех pre-commit хуков
   poetry run pre-commit run --all-files
   
   # Запуск Black форматирования
   poetry run black .
   
   # Запуск Ruff линтера
   poetry run ruff check .
   
   # Запуск isort для сортировки импортов
   poetry run isort .
   
   # Запуск mypy для проверки типов
   poetry run mypy src/ app.py
   ```

### Автоматические проверки

При создании Pull Request или push в ветку `main` автоматически запускаются линтеры и тесты через GitHub Actions.
Результаты проверок можно увидеть на странице Pull Request или во вкладке Actions в репозитории.
