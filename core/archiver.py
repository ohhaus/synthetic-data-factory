import zipfile
import os
import logging
import glob


class DataArchiver:
    def __init__(self):
        self.data_dir = 'data'
        os.makedirs(self.data_dir, exist_ok=True)
        self.current_archive_path = None

    def _cleanup_old_archives(self):
        """Удаляет старые архивы из директории."""
        try:
            for file in os.listdir(self.data_dir):
                file_path = os.path.join(self.data_dir, file)
                if file.endswith('.zip'):
                    os.remove(file_path)
                    logging.info(f"Removed old archive: {file}")
        except Exception as e:
            logging.error(f"Error cleaning up old archives: {str(e)}")
            raise

    def create_zip(self, file_paths, archive_name):
        """Создает zip-архив из указанных файлов CSV."""
        try:
            if isinstance(file_paths, str):
                if "*" in file_paths or "?" in file_paths:
                    file_paths = glob.glob(file_paths)
                else:
                    file_paths = [file_paths]

            # Удаляем старые архивы
            self._cleanup_old_archives()

            # Добавляем .zip к имени архива, если его там нет
            if not archive_name.endswith('.zip'):
                archive_name += '.zip'

            self.current_archive_path = os.path.join(
                self.data_dir,
                archive_name
            )

            # Проверяем, что файлы существуют и не пусты
            valid_files = []
            for file_path in file_paths:
                if (os.path.exists(file_path) and
                        os.path.getsize(file_path) > 0):
                    valid_files.append(file_path)
                else:
                    logging.warning(
                        f"File does not exist or is empty: {file_path}"
                    )

            if not valid_files:
                logging.error("No valid files to archive!")
                raise Exception("No valid files to archive!")

            # Создаем zip-архив и добавляем все файлы
            with zipfile.ZipFile(
                self.current_archive_path,
                'w',
                zipfile.ZIP_DEFLATED
            ) as zipf:
                for file_path in valid_files:
                    file_name = os.path.basename(file_path)
                    zipf.write(file_path, file_name)
                    logging.info(f"Added file to archive: {file_path}")
                    # Удаляем исходный файл
                    os.remove(file_path)
                    logging.info(f"Removed source file: {file_path}")

            # Проверяем, что архив создан и не пуст
            if (not os.path.exists(self.current_archive_path) or
                    os.path.getsize(self.current_archive_path) == 0):
                logging.error("Created archive is empty or does not exist!")
                raise Exception("Archive creation failed!")

            logging.info(
                f"Archive created successfully: {self.current_archive_path}"
            )
            return self.current_archive_path

        except Exception as e:
            logging.error(f"Error creating archive: {str(e)}")
            raise

    def get_archive_path(self):
        """Возвращает путь к текущему архиву."""
        return self.current_archive_path
