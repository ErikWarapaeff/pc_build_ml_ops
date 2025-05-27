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

## CI/CD Пайплайн

Этот проект использует комплексный CI/CD пайплайн, управляемый с помощью GitHub Actions. Пайплайн автоматизирует различные задачи разработки и развертывания, обеспечивая качество кода, согласованность и эффективную доставку артефактов.

Пайплайн запускается при следующих событиях:
*   **Push** в ветку `main`.
*   **Push** тегов, соответствующих шаблону `v*` (например, `v1.0.0`, `v0.1.2`).
*   **Pull Request**, нацеленный на ветку `main`.

Пайплайн состоит из следующих основных задач (jobs):

### 1. Проверка Кода (`lint`)
Эта задача отвечает за поддержание качества и согласованности кода.
*   **Триггеры:** Запускается при каждом push в `main`, pull request в `main` и для тегов `v*`.
*   **Шаги:**
    1.  **Checkout code (Клонирование кода):** Получает последнюю версию репозитория.
    2.  **Set up Python (Настройка Python):** Инициализирует окружение Python 3.12.
    3.  **Install Poetry (Установка Poetry):** Устанавливает менеджер зависимостей Poetry.
    4.  **Configure Poetry (Конфигурация Poetry):** Настраивает Poetry для создания виртуальных окружений внутри проекта.
    5.  **Install dependencies (Установка зависимостей):** Устанавливает зависимости проекта, включая инструменты для разработки и `types-PyYAML` для проверки типов.
    6.  **Run black (Запуск black):** Проверяет форматирование кода Python с использованием Black.
    7.  **Run isort (Запуск isort):** Проверяет и сортирует импорты с использованием isort.
    8.  **Run ruff (Запуск ruff):** Выполняет линтинг с использованием Ruff для широкого спектра проверок стиля кода Python и поиска ошибок.
    9.  **Run mypy (Запуск mypy):** Проводит статическую проверку типов с использованием Mypy для выявления ошибок типизации. Конфигурация Mypy настроена на менее строгий режим, игнорируя некоторые распространенные ошибки типизации для облегчения интеграции и позволяя постепенно улучшать аннотации типов.

### 2. Выполнение Тестов (`test`)
Эта задача выполняет автоматизированные тесты для обеспечения корректности и стабильности приложения.
*   **Триггеры:** Запускается после успешного завершения задачи `lint`, при push в `main`, pull request в `main` и для тегов `v*`.
*   **Шаги:**
    1.  **Checkout code.**
    2.  **Set up Python 3.12.**
    3.  **Install Poetry.**
    4.  **Configure Poetry.**
    5.  **Install dependencies** (включая зависимости для разработки).
    6.  **Run tests (Запуск тестов):** Выполняет тесты с использованием `pytest` и генерирует отчет о покрытии кода (`coverage.xml`).
    7.  **Upload coverage to Codecov (Загрузка покрытия в Codecov):** Отправляет отчет о покрытии в Codecov для анализа и отслеживания (требуется секрет `CODECOV_TOKEN`).

### 3. Сборка Python Пакета (`build-package`)
Эта задача собирает дистрибутивный пакет Python (wheel и sdist).
*   **Триггеры:** Запускается **только для тегов `v*`** после успешного завершения задачи `test`. Это гарантирует, что пакеты собираются только для официальных релизов.
*   **Шаги:**
    1.  **Checkout code.**
    2.  **Set up Python 3.12.**
    3.  **Install Poetry.**
    4.  **Build package (Сборка пакета):** Создает дистрибутивные файлы с помощью `poetry build`.
    5.  **Store version (Сохранение версии):** Извлекает версию из Git-тега (например, `v1.0.0` становится `1.0.0`) и сохраняет ее в переменной окружения.
    6.  **Upload package artifact (Загрузка артефакта пакета):** Архивирует директорию `dist/` (содержащую собранный пакет) как артефакт GitHub с именем `dist`. Артефакты хранятся 3 дня.

### 4. Сборка Docker Образа (`build-docker`)
Эта задача собирает Docker-образ для приложения.
*   **Триггеры:** Запускается после успешного завершения задачи `test`, при push в `main`, pull request в `main` и для тегов `v*`.
*   **Шаги:**
    1.  **Checkout code.**
    2.  **Set up Docker Buildx (Настройка Docker Buildx):** Инициализирует Docker Buildx для расширенной сборки образов.
    3.  **Set Docker metadata (Установка метаданных Docker):** Генерирует теги и метки для Docker-образа на основе Git-веток, тегов и SHA коммитов (например, `main`, `v1.0.0`, `sha-abcdef`).
    4.  **Build and export Docker image (Сборка и экспорт Docker-образа):** Собирает Docker-образ с использованием `Dockerfile` и загружает его локально. Образ тегируется метаданными, сгенерированными на предыдущем шаге. Собранный образ экспортируется в файл `.tar`.
    5.  **Upload Docker image artifact (Загрузка артефакта Docker-образа):** Архивирует экспортированный Docker-образ (файл `.tar`) как артефакт GitHub с именем `docker-image`. Артефакты хранятся 1 день.

### 5. Публикация Python Пакета (`publish-package`)
Эта задача публикует пакет Python на PyPI и создает Релиз на GitHub.
*   **Триггеры:** Запускается **только для тегов `v*`** после успешного завершения задачи `build-package`.
*   **Шаги:**
    1.  **Download artifact (Скачивание артефакта):** Получает артефакт `dist` (собранный пакет) из задачи `build-package`.
    2.  **Publish to PyPI (Публикация на PyPI):** Публикует пакет в Python Package Index (PyPI) с использованием действия `pypa/gh-action-pypi-publish`. Требуется секрет `PYPI_API_TOKEN` для аутентификации. Пропускает, если версия уже существует.
    3.  **Create GitHub Release (Создание Релиза GitHub):** Создает новый релиз на GitHub, используя Git-тег в качестве версии релиза. Файлы собранного пакета из `dist/` прикрепляются к релизу. Заметки к релизу ссылаются на `CHANGELOG.md`.

### 6. Публикация Docker Образа (`publish-docker`)
Эта задача публикует Docker-образ в GitHub Container Registry (ghcr.io).
*   **Триггеры:** Запускается после успешного завершения задачи `build-docker`. Выполняется при:
    *   Push в ветку `main`.
    *   Push тегов `v*`.
*   **Шаги:**
    1.  **Download artifact (Скачивание артефакта):** Получает артефакт `docker-image` (файл `.tar`) из задачи `build-docker`.
    2.  **Load Docker image (Загрузка Docker-образа):** Загружает образ из файла `.tar` в локальный Docker демон.
    3.  **Login to GitHub Container Registry (Вход в GitHub Container Registry):** Аутентифицируется в `ghcr.io` с использованием `GITHUB_TOKEN`.
    4.  **Extract Docker metadata (Извлечение метаданных Docker):** Генерирует целевые теги для `ghcr.io` (например, `ghcr.io/OWNER/REPO:main`, `ghcr.io/OWNER/REPO:v1.0.0`).
    5.  **Push Docker image (Отправка Docker-образа):** Тегирует загруженный локальный образ (используя его имя в нижнем регистре и тег версии, например, `owner/repo:main`) целевыми тегами `ghcr.io` и отправляет их в GitHub Container Registry.

### 7. Развертывание Документации (`deploy-docs`)
Эта задача собирает и развертывает документацию проекта на GitHub Pages.
*   **Триггеры:** Запускается после успешного завершения обеих задач `test` и `build-package`. Выполняется при:
    *   Push в ветку `main`.
    *   Push тегов `v*`.
*   **Шаги:**
    1.  **Checkout code.**
    2.  **Set up Python 3.12.**
    3.  **Install Poetry.**
    4.  **Install dependencies (Установка зависимостей):** Устанавливает зависимости проекта и добавляет `mkdocs-material` и `mike` (для версионированной документации).
    5.  **Build documentation (Сборка документации):** Генерирует статический сайт документации с помощью `mkdocs build`.
    6.  **Deploy to GitHub Pages (Развертывание на GitHub Pages):** Отправляет содержимое директории `site/` в ветку `gh-pages`, делая его доступным через GitHub Pages.

# Система версионирования данных для проекта PC Build ML Ops

## Описание

Этот проект использует DVC (Data Version Control) для версионирования данных. DVC позволяет отслеживать изменения в больших файлах данных, не храня их в Git.

## Структура данных

Данные хранятся в директории `data/` и включают:
- CSV-файлы с информацией о компьютерных комплектующих (CPU, GPU)
- Дополнительные CSV-файлы в директориях `csv_files/` и `csv_perifi/`
- Базы данных в директории `databases/`

## Работа с DVC

### Инициализация

Проект уже инициализирован с помощью DVC:
```bash
dvc init
```

### Локальное хранилище

Данные хранятся локально в директории `.dvc_storage/`:
```bash
dvc remote add -d local .dvc_storage
```

### Основные команды

Получить данные:
```bash
dvc pull
```

Отправить данные в хранилище:
```bash
dvc push
```

Проверить статус:
```bash
dvc status
```

### Добавление новых данных

Для добавления новых файлов данных:
```bash
dvc add data/новый_файл.csv
git add data/новый_файл.csv.dvc
git commit -m "Добавлен новый файл данных"
dvc push
```

## Airflow

### Запуск
#### Вариативность 
Есть 2 основных способа развернуть apache airflow(не учитывая многочисленных настроек):
С помощью рекомендованного docker-compose файла или же через pip.
Опробовав оба, пришли к выводу, что для проекта удобнее использовать docker-compose.

#### Шаги 

1. Скачать curl -LfO 'https://airflow.apache.org/docs/apache-airflow/3.0.1/docker-compose.yaml'
2. Создать папку - dags, поместить туда даг с задачами тестирования.
3. Для выполняния тестирования модели были необходимы библиотеки, которых нет в образе airflow по умолчанию , поэтому необходимо было создать свой образ - pc_build_ml_ops/airflow/airflow-compose/Dockerfile.
4. Запустить docker-compose
![alt text](airflow/airflow-compose/image_2025-05-26_23-29-08.png)
5. По адресу доступен интерфейс airflow
http://localhost:8080/dags
![alt text](image-1.png)


#### Альтернативный путь:
1. Создать env для airflow
2. Установка переменных окружения:
```bash
export AIRFLOW_HOME=/opt/airflow
export AIRFLOW__CORE__EXECUTOR=LocalExecutor
export AIRFLOW__CORE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW_VERSION = 2.7.3
```
3. Установить библиотеки:
```bash
sudo apt-get install -y --no-install-recommends \
        freetds-bin \
        krb5-user \
        ldap-utils \
        libffi6 \
        libsasl2-2 \
        libsasl2-modules \
        libssl1.1 \
        locales  \
        lsb-release \
        sasl2-bin \
        psycopg2 \
        unixodbc
```
4.  Установка airflow
```bash
pip install "apache-airflow==${AIRFLOW_VERSION}"
```
5. Инциализировать бд, сервер, планировщик 
``` bash
airflow db init
airflow webserver --port 8080
airflow scheduler
```
### Cоздание дага:
1. Для выполнения кода проекта , код проекта был скопирован в dags
2. В образ было добавлено копирование конфигов
3. Был создан dag_test - c запуском тестов.
4. В airflow были добавлены переменые 
![alt text](image-2.png)

