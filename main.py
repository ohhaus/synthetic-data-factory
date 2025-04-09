import logging
import os
import time
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from core.archiver import DataArchiver
from core.generator import SyntheticDataGenerator
# Ну не в мейне же все писать/ сделай нормально ну
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Идея использовать класс - хорошо, но не масштабируемо/ расширяемо, попробуй использовать набор классов
data_archiver = DataArchiver()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# В отдельный файл
class GenerateRequest(BaseModel):
    """Модель запроса для генерации данных"""
    num_rows: int = Field(default=None, gt=0)
    output_file: str = Field(default=None, min_length=1)
    chunk_size: int = Field(default=50_000, gt=0)
    num_workers: int = Field(default=4, gt=0)
    records_per_file: Optional[int] = Field(default=None, gt=0)

# выглядит как датакласс
class GenerationStatus:
    """Класс для отслеживания статуса генерации файла"""

    def __init__(self):
        self.is_generating: bool = False
        self.current_file: Optional[str] = None
        self.start_time: Optional[float] = None


generation_status = GenerationStatus()


@app.get("/")
async def home(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})

# Почему функция? + слишком большая - нужно разбить
def generate_and_archive(request: GenerateRequest):
    """Генерация и архивация данных с отслеживанием статуса"""
    # Все ли нужно в try?
    try:
        generation_status.is_generating = True
        generation_status.current_file = request.output_file
        start_time = time.time()
        generation_status.start_time = start_time

        records_info = (
            f"Starting data generation: {request.num_rows} rows, "
            f"{request.chunk_size} chunk size, {request.num_workers} workers, "
        )
        logging.info(records_info)

        csv_filename = request.output_file
        if csv_filename.endswith('.csv'):
            csv_filename = csv_filename[:-4]
        if csv_filename.endswith('.zip'):
            csv_filename = csv_filename[:-4]

        archive_name = f"{csv_filename}.zip"

        generator = SyntheticDataGenerator(
            request.num_rows, request.chunk_size, request.num_workers)

        csv_paths = generator.generate_to_csv(
            csv_filename, request.records_per_file)

        # Проверяем, что пути к файлам вернулись
        if not csv_paths:
            logging.error("File generation failed!")
            raise HTTPException(
                status_code=500, detail="File generation failed")

        logging.info(f"Data successfully generated: {len(csv_paths)} files")

        logging.info(f"Starting archiving {len(csv_paths)} files")
        data_archiver.create_zip(csv_paths, archive_name=archive_name)
        logging.info(
            f"Files archived successfully: {data_archiver.get_archive_path()}")

        end_time = time.time()
        elapsed_time = end_time - start_time
        logging.info(f"The operation has taken: {elapsed_time:.2f} seconds")

    except Exception as e:
        logging.error(f"Error during generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        generation_status.is_generating = False
        generation_status.current_file = None
        generation_status.start_time = None


@app.post("/generate")
async def generate_data(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Обработчик POST-запроса для запуска генерации и архивации данных в фоновом режиме"""
    if generation_status.is_generating:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Another file '{generation_status.current_file}' "
                "is currently being generated"
            )
        )

    logging.info("Received request to generate and archive data")
    background_tasks.add_task(generate_and_archive, request)
    return {"message": "Data generation and archiving started"}


@app.post("/generate-form")
async def generate_from_form(
    background_tasks: BackgroundTasks,
    num_rows: int = Form(...),
    output_file: str = Form(...),
    chunk_size: int = Form(...),
    num_workers: int = Form(...),
    records_per_file: Optional[str] = Form(None),
):
    """Обработчик POST-запроса для запуска генерации через форму"""
    if generation_status.is_generating:
        raise HTTPException(
            # Магическое число используй статусы
            status_code=409,
            detail=(
                f"Another file '{generation_status.current_file}' "
                "is currently being generated"
            )
        )

    try:
        # Преобразование records_per_file в int или None
        records_per_file_int = None
        if records_per_file and records_per_file.strip():
            try:
                records_per_file_int = int(records_per_file)
                if records_per_file_int <= 0:
                    records_per_file_int = None
            except ValueError:
                records_per_file_int = None

        request_data = GenerateRequest(
            num_rows=num_rows,
            output_file=output_file,
            chunk_size=chunk_size,
            num_workers=num_workers,
            records_per_file=records_per_file_int
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(generate_and_archive, request_data)
    return RedirectResponse(url="/", status_code=303)


@app.get("/download")
async def download_file():
    """Обработчик для скачивания архива с данными"""
    archive_path = data_archiver.get_archive_path()

    if archive_path is None:
        raise HTTPException(
            status_code=404,
            detail="No archive has been generated yet"
        )

    if not os.path.exists(archive_path):
        raise HTTPException(
            status_code=404,
            detail=f"Archive file not found at {archive_path}"
        )

    return FileResponse(
        archive_path,
        filename=os.path.basename(archive_path),
        media_type='application/zip'
    )


@app.get("/status")
async def get_generation_status():
    """Получение текущего статуса генерации"""
    # Лучше сделать 1 ретерн
    if not generation_status.is_generating:
        return {
            "status": "idle",
            "current_file": None,
            "elapsed_time": None
        }

    elapsed_time = time.time() - generation_status.start_time
    return {
        "status": "generating",
        "current_file": generation_status.current_file,
        "elapsed_time": f"{elapsed_time:.2f} seconds"
    }
