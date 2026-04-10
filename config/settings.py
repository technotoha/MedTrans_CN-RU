"""
Настройки приложения для PDF переводчика.
Все настройки через Pydantic Settings.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    """Основные настройки приложения."""
    
    # LLM настройки
    LLM_BASE_URL: str = Field(
        default="http://127.0.0.1:1234/v1",
        description="URL локального LLM сервера"
    )
    LLM_MODEL: str = Field(
        default="translategemma-12b-it",
        description="Модель для перевода"
    )
    LLM_API_KEY: str = Field(
        default="",
        description="API ключ для LLM (может быть пустым для локальных моделей)"
    )
    LLM_TIMEOUT: int = Field(
        default=120,
        description="Таймаут запроса к LLM в секундах"
    )
    LLM_MAX_RETRIES: int = Field(
        default=3,
        description="Максимальное количество попыток запроса"
    )
    LLM_RETRY_DELAY: float = Field(
        default=2.0,
        description="Задержка между попытками (секунды)"
    )
    LLM_TEMPERATURE: float = Field(
        default=0.3,
        description="Температура генерации LLM"
    )
    LLM_MAX_TOKENS: int = Field(
        default=4096,
        description="Максимум токенов в ответе LLM"
    )
    
    # OCR настройки
    OCR_LANGUAGES: str = Field(
        default="chi_sim",
        description="Языки для Tesseract (китайский)"
    )
    OCR_DPI: int = Field(
        default=300,
        description="DPI для рендеринга страниц перед OCR"
    )
    OCR_PSM: int = Field(
        default=6,
        description="Page segmentation mode для Tesseract"
    )
    OCR_OEM: int = Field(
        default=3,
        description="OCR Engine Mode для Tesseract"
    )
    
    # Настройки обработки
    ENABLE_OCR: bool = Field(
        default=True,
        description="Включить OCR для изображений и сканов"
    )
    ENABLE_TABLE_DETECTION: bool = Field(
        default=True,
        description="Включить детекцию таблиц через Camelot"
    )
    CHUNK_SIZE: int = Field(
        default=2000,
        description="Размер чанка для перевода (символы)"
    )
    CHUNK_OVERLAP: int = Field(
        default=200,
        description="Перекрытие чанков для сохранения контекста"
    )
    MAX_CONCURRENT_TASKS: int = Field(
        default=5,
        description="Максимум параллельных задач"
    )
    
    # Языки перевода
    SOURCE_LANG: str = Field(
        default="zh",
        description="Исходный язык"
    )
    TARGET_LANG: str = Field(
        default="ru",
        description="Целевой язык"
    )
    
    # Пути к директориям
    BASE_DIR: Path = Field(
        default=Path(__file__).parent.parent,
        description="Базовая директория проекта"
    )
    INPUT_DIR: Path = Field(
        default=Path(__file__).parent.parent / "input",
        description="Директория входных файлов"
    )
    OUTPUT_DIR: Path = Field(
        default=Path(__file__).parent.parent / "output",
        description="Директория выходных файлов"
    )
    TEMP_DIR: Path = Field(
        default=Path(__file__).parent.parent / "temp",
        description="Директория временных файлов"
    )
    LOGS_DIR: Path = Field(
        default=Path(__file__).parent.parent / "logs",
        description="Директория логов"
    )
    
    # Настройки логирования
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Уровень логирования"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    def create_directories(self):
        """Создать необходимые директории."""
        for dir_path in [self.INPUT_DIR, self.OUTPUT_DIR, self.TEMP_DIR, self.LOGS_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)


# Глобальный экземпляр настроек
settings = Settings()
settings.create_directories()
