#!/bin/bash

# Инициализация БД (если ещё не инициализирована)
airflow db init

# Создание административного пользователя
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com || true