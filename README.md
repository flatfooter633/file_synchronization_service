# API Documentation for the File Synchronization Service

## Description

The file synchronization service is designed for automatic file synchronization between a local folder and the Yandex.Disk cloud storage. The application monitors changes in the local folder and updates the corresponding files in the cloud storage.

## Installation

To work, you will need a Yandex Disk access token. To get it, register or log in to your Yandex account, and then go to the [site](https://yandex.ru/dev/disk/poligon/) to generate a token. Here you can also try various methods of working with the Yandex Disk public API. Authorization is carried out using the AOuth 2.0 protocol. When composing a request, the `Authorization: OAuth <YOUR-YANDEX-DISK-TOKEN>` header is used.

To run the service, install the dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Service parameters are set in the `.env` file:

```dotenv
# Path to the local folder to be synchronized
SYNC_FOLDER=D:\test

# Path to the Yandex.Disk folder where files will be uploaded
YANDEX_FOLDER=backup

# Token for accessing the Yandex.Disk API
YANDEX_TOKEN=<YOUR-YANDEX-DISK-TOKEN>

# Synchronization interval in seconds
SYNC_INTERVAL=10

# Path to the log file
LOG_FILE=sync.log

# Logging level for console output
LOG_LEVEL="INFO"

# Logging level for file recording
LOG_FILE_LEVEL="DEBUG"

# Maximum log file size before rotation
LOG_ROTATION="1 MB"

# Compression method for archiving old log files
LOG_COMPRESSION="zip"
```

## Key Features

- **Linking a specified local folder with cloud storage.**
- **Monitoring file changes in the local folder and updating them in the cloud.**
- **Automatic upload of new or modified files.**
- **Deleting files from the cloud if they are deleted locally.**
- **Logging operations and errors.**
- **Full synchronization of all nested directories and files.**

## Project Structure

```
/
|-- api/api.py          # Yandex.Disk API logic
|-- log/                # Logs directory
|-- main.py             # Main synchronization script
|-- .env                # Configuration file
|-- requirements.txt    # Project dependencies
|-- README.md           # Additional documentation
```

## Usage

### Starting the Service

To start the service, run:

```bash
python main.py
```

### Main Workflow

1. Environment variables are loaded from `.env`.
2. The existence of the local folder is checked.
3. Files and nested directories are synchronized between the local folder and Yandex.Disk.
4. Resynchronization occurs every `SYNC_INTERVAL` seconds.

### File and Folder Synchronization Algorithm

1. Retrieve the list of all files and directories in the local folder.
2. Retrieve the list of files and directories in the corresponding Yandex.Disk folder.
3. Calculate the hash (MD5) of each local file and compare it with the corresponding cloud file.
4. If a file does not exist in the cloud or its hash differs, it is queued for upload.
5. If files exist in the cloud but not locally, they are queued for deletion.
6. All files are uploaded asynchronously with a limit on the number of concurrent requests.
7. The current cycle completes and a new one starts after `SYNC_INTERVAL`.

## `YandexDiskAPI` Class

### `__init__(self, token, folder)`

Creates an object for working with the Yandex.Disk API.

- **token** (str) — OAuth token for access.
- **folder** (str) — Root folder in cloud storage.

### `sync_folder(self, local_folder)`

Synchronizes a local folder with the cloud.

- **local_folder** (str) — Path to the local folder.

### `upload(self, session, file_path, remote_path)`

Uploads a file to the cloud.

- **file_path** (str) — Local path.
- **remote_path** (str) — Cloud path.

### `delete(self, session, remote_path_to_file)`

Deletes a file from the cloud.

- **remote_path_to_file** (str) — Path of the file to delete.

### `get_info(self, session, remote_dir_path)`

Retrieves information about files in the cloud.

- **remote_dir_path** (str) — Path to the cloud folder.

## File Comparison Before Synchronization

Before uploading files, the program compares the local and cloud versions using their hash (MD5). If the hashes match, the upload is skipped, saving bandwidth and reducing server load. If the hashes differ, the file is queued for upload.

## Logging

Logs are recorded in the file specified in `LOG_FILE`. Example log:

```log
2025-02-02 03:45:58.675 | INFO     | __main__:main:44 - Synchronization service started
2025-02-02 03:45:58.675 | INFO     | __main__:sync_files:39 - Beginning recursive synchronization of nested directories
2025-02-02 03:47:10.328 | INFO     | api.api:create_folders_first:75 - Folder backup/module_16_db3 successfully created and verified
...
2025-02-02 03:48:17.655 | WARNING  | api.api:upload:173 - File backup/async/log/sync.log uploaded
```

## Pros and Cons

### Pros:

- **Asynchronous Uploading** — Uses `asyncio` to perform multiple uploads concurrently, speeding up synchronization.
- **File Hashing** — Only modified files are uploaded.
- **Flexibility** — Configurable via `.env`.
- **Fault Tolerance** — Errors are logged but do not interrupt execution.
- **Nested Directory Support** — Synchronization of all files and folders.
- **Filename Validation** — Handles invalid character errors.

### Cons:

- **Dependency on Yandex.Disk** — The service does not support other cloud storage providers.
- **Uncovered Edge Cases** — Possible issues with long filenames or special characters.

## Error Handling and Exceptions

The program does not terminate on network or file access errors. Errors are logged, and other tasks continue to execute.

## Conclusion

The program efficiently synchronizes files with Yandex.Disk, ensuring automatic updates and deletions in the cloud.


