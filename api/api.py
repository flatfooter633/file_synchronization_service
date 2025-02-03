import aiohttp
import asyncio
import os
import hashlib
from loguru import logger


def get_file_hash(filepath: str) -> hash:
    """Возвращает хеш файла для отслеживания изменений."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Ошибка при вычислении хеша {filepath}: {e}")
        return None


def sanitize_path(path) -> str:
    """Удаляет точки и нормализует путь."""
    return str(os.path.normpath(path).replace("\\", "/"))

def validate_path(path) -> bool:
    """Возвращает True, если папка удовлетворяет критериям синхронизации."""
    return True \
        if (
            not any(part.startswith(('.', '_', 'venv')) for part in path.split('/'))
            and "&" not in path) \
        else False


class YandexDiskAPI:
    first_run = True
    def __init__(self, token, folder, max_concurrent_requests=55):
        """Инициализация API, получение токена и папки"""
        self.BASE_URL = "https://cloud-api.yandex.net/v1/disk/resources"
        self.token = token
        self.folder = sanitize_path(folder.rstrip("/"))
        self.headers = {"Authorization": f"OAuth {self.token}", "Accept": "application/json"}
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

    def get_full_path(self, remote_path: str = None, filename: str = None) -> str:
        """Возвращает полный путь до файла или папки в облаке."""
        if remote_path and filename:
            return sanitize_path(f"{self.folder}/{remote_path}/{filename}".strip("/"))
        elif filename:
            return sanitize_path(f"{self.folder}/{filename}".strip("/"))
        elif remote_path:
            return sanitize_path(f"{self.folder}/{remote_path}".strip("/"))
        else:
            return self.folder

    async def create_folder(self, session, path: str = None):
        """Создает папку в облаке, если её нет"""
        full_path = self.get_full_path(remote_path=path)
        params = {
            "path": f"{full_path}",
            "fields": "name,_embedded.items.path",
        }
        async with session.put(self.BASE_URL, headers=self.headers, params=params) as response:
            if response.status in (201, 409):
                logger.debug(f"Каталог [{full_path}] {'создан' if response.status == 201 else 'уже существует'}")
                return True
            logger.error(f"Ошибка [{response.status}] при создании каталога {full_path}: {await response.text()}")
        return False

    async def create_folders_first(self, session, local_folder):
        """Создаёт все папки перед загрузкой файлов"""
        for root, dirs, _ in os.walk(local_folder):
            remote_path = sanitize_path(os.path.relpath(root, local_folder))
            full_path = self.get_full_path(remote_path=remote_path)
            if validate_path(remote_path):
                created = await self.create_folder(session, remote_path)
                logger.info(f"Синхронизация каталога [{full_path}] успешно завершена") if created \
                    else logger.error(f"Не удалось создать каталог [{full_path}]")


    async def sync_folder(self, local_folder: str):
        """Синхронизирует файлы и удаляет отсутствующие"""
        async with aiohttp.ClientSession() as session:
            # Создание очередей и синхронизация корневого каталога
            upload_tasks = []
            sync_tasks = []
            await self.sync_directory(session, local_folder, remote_path=None, upload_tasks=upload_tasks)

            # Проверка первого запуска, если первый запуск, то создаём каталоги
            if YandexDiskAPI.first_run:
                # Создаёт все каталоги перед загрузкой файлов
                await self.create_folders_first(session, local_folder)
            else:
                # Если это не первый запуск, то синхронизируем файлы
                # Рекурсивный обход подкаталогов
                for root, dirs, files in os.walk(local_folder):
                    if root != local_folder:  # Пропускаем корневой каталог, так как он уже обработан
                        remote_path = sanitize_path(os.path.relpath(root, local_folder))
                        if validate_path(remote_path):
                            sync_tasks.append(self.sync_directory(session, root, remote_path, upload_tasks))

                # Выполняем все задачи синхронизации одновременно
                await asyncio.gather(*sync_tasks)

            # Выполняем все задачи загрузки одновременно
            if upload_tasks:
                await asyncio.gather(*upload_tasks)

            # Отмечаем, что мы уже синхронизировали корневой каталог
            YandexDiskAPI.first_run = False


    async def sync_directory(self, session, local_dir, remote_path, upload_tasks):
        """Синхронизирует отдельный каталог"""
        await self.create_folder(session, remote_path)
        # Получаем информацию о файлах в текущей облачной директории
        cur_path = self.get_full_path(remote_path=remote_path)
        try:
            logger.debug(f"Проверяем локальный каталог: [{cur_path}]")
            cloud_files = await self.get_info(session, cur_path)
            logger.debug(f"- облачные файлы: {cloud_files.keys()}")
            local_files = [f for f in os.listdir(local_dir)
                           if
                           validate_path(f)
                           and
                           os.path.isfile(os.path.join(local_dir, f))
                           ]
            logger.debug(f"- локальные файлы: {local_files}")

            # Сравниваем локальные и облачные файлы и выставляем их в очередь на загрузку или удаление
            for file in local_files:
                local_file_path = os.path.join(local_dir, file)
                remote_file_path = self.get_full_path(remote_path=remote_path, filename=file)
                local_hash = get_file_hash(local_file_path)
                cloud_hash = cloud_files.get(file)

                if local_hash != cloud_hash:
                    logger.info(f"Файл [{file}] поставлен в очередь на загрузку. ")
                    logger.info(f"  Локальный хеш: [{local_hash}]")
                    logger.info(f"   Облачный хеш: [{cloud_hash}]")
                    upload_tasks.append(asyncio.create_task(self.upload(session, local_file_path, remote_file_path)))
                else:
                    logger.debug(f"Файл [{file}] уже синхронизирован")

            # Удаляем лишние файлы из облака
            await self.cleanup(session, remote_path, cloud_files, os.listdir(local_dir))
        except FileNotFoundError as e:
            logger.error(f"Ошибка при обработке каталога [{local_dir}]: {e}")

    async def get_info(self, session, remote_dir_path: str):
        """Получает список файлов и их хеши в облаке"""
        params = {
            "path": remote_dir_path,
            "fields": "_embedded.items.name,_embedded.items.md5,_embedded.items.type",
            "limit": 1000
        }
        async with session.get(self.BASE_URL, headers=self.headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"HTTP ответ [{remote_dir_path}] -- {data}")
                return {str(item["name"]): item.get("md5") for item in data.get("_embedded", {}).get("items", [])
                        if item.get("type") == "file"}
            logger.warning(f"HTTP ответ [{remote_dir_path}]: {await response.text()}")
            raise FileNotFoundError(f"Ресурс не найден: [{remote_dir_path}]")

    async def get_upload_url(self, session, remote_path):
        """Получает URL для загрузки"""
        full_path = sanitize_path(remote_path)
        url = f"{self.BASE_URL}/upload?path={full_path}&overwrite=true"
        logger.debug(f"URL загрузки: {url}")
        async with session.get(url, headers=self.headers) as response:
            if response.status == 200:
                return (await response.json()).get("href")
            logger.error(f"Ошибка получения ссылки загрузки: {await response.text()}")
        return None

    async def upload(self, session, file_path, remote_path):
        """Загружает файл"""
        async with self.semaphore:
            upload_url = await self.get_upload_url(session, remote_path)
            if upload_url:
                with open(file_path, "rb") as f:
                    async with session.put(upload_url, data=f) as response:
                        if response.status in [200, 201, 202]:
                            logger.warning(f"Файл [{remote_path}] загружен")
                            return True
                        else:
                            logger.error(
                                f"Ошибка загрузки [{file_path}]: статус [{response.status}], {await response.text()}")
            else:
                logger.error(f"Не удалось получить URL для загрузки файла [{file_path}]")
        return False

    async def delete(self, session, remote_path_to_file):
        """Удаляет файл в облаке"""
        async with self.semaphore:
            url = f"{self.BASE_URL}?path={remote_path_to_file}"
            async with session.delete(url, headers=self.headers) as response:
                if response.status in [200, 202, 204]:
                    logger.debug(f"Файл {remote_path_to_file} удалён")
                    return True
                logger.error(f"Ошибка удаления [{remote_path_to_file}]: {await response.text()}")
        return False

    async def cleanup(self, session, remote_path, cloud_files, local_files):
        """Удаляет файлы из облака, которых нет локально"""
        remote_set = set(cloud_files.keys())
        local_set = set(local_files)
        files_to_delete = remote_set - local_set

        for remote_file in files_to_delete:
            logger.debug(f"Файл [{remote_file}] отсутствует локально")
            if await self.delete(session, self.get_full_path(remote_path=remote_path, filename=remote_file)):
                logger.warning(f"Файл [{remote_file}] удалён из облака, так как отсутствует локально")
