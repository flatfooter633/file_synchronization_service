import os
from sys import stdout
import asyncio
from dotenv import load_dotenv, find_dotenv
from loguru import logger
from api.api import YandexDiskAPI

# Загрузка переменных окружения из файла .env
# Если файла .env нет, окружение не загружается и приложение завершается с сообщением об ошибке.
if not find_dotenv():
    exit("Переменные окружения не загружены, потому что файл .env отсутствует")
else:
    load_dotenv()

LOCAL_FOLDER = os.getenv("SYNC_FOLDER")
YANDEX_FOLDER = os.getenv("YANDEX_FOLDER")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", 60))
LOG_FILE = os.path.join("log", os.getenv("LOG_FILE", "sync.log"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE_LEVEL = os.getenv("LOG_FILE_LEVEL", "DEBUG")
LOG_ROTATION = os.getenv("LOG_ROTATION", "1 MB")
LOG_COMPRESSION = os.getenv("LOG_COMPRESSION", "zip")

# Настраиваем логирование
logger.remove()
logger.add(stdout, level=LOG_LEVEL, colorize=True)
logger.add(
    LOG_FILE, level=LOG_FILE_LEVEL, rotation=LOG_ROTATION, compression=LOG_COMPRESSION
)


async def sync_files():
    """Основная функция синхронизации."""
    if not os.path.exists(LOCAL_FOLDER):
        logger.error(f"Локальная папка {LOCAL_FOLDER} не найдена!")
        return

    api = YandexDiskAPI(YANDEX_TOKEN, YANDEX_FOLDER)

    logger.info("Начало рекурсивной синхронизации вложенных каталогов")
    await asyncio.gather(api.sync_folder(LOCAL_FOLDER))


async def main():
    logger.info("Запуск службы синхронизации")
    while True:
        await sync_files()
        await asyncio.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Служба синхронизации остановлена")
