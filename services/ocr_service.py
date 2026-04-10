"""
OCR service for processing scanned documents and images.
Uses Tesseract OCR with preprocessing for improved accuracy.
"""
import asyncio
import io
import logging
from typing import Optional, List
from PIL import Image
import pytesseract
from config.settings import settings
from utils.image_utils import preprocess_image, cv2_to_pil

logger = logging.getLogger(__name__)

class OCRService:
    def __init__(self):
        self.config_lang = settings.OCR_LANG  # Исправлено: было settings.ocr.lang
        self.psm_mode = settings.OCR_PSM_MODE # Исправлено: было settings.ocr.psm_mode
        logger.info(f"OCR Service initialized with languages: {self.config_lang}")

    async def recognize(self, image_data: bytes, lang: Optional[str] = None) -> str:
        """
        Распознавание текста с изображения.
        """
        loop = asyncio.get_event_loop()
        
        def _run_ocr():
            try:
                # Конвертация байтов в изображение
                image = Image.open(io.BytesIO(image_data))
                
                # Препроцессинг (улучшение качества)
                processed_img = preprocess_image_for_ocr(image)
                
                # Настройка языка
                current_lang = lang if lang else self.config_lang
                
                # Конфигурация Tesseract
                custom_config = f"--oem 3 --psm {self.psm_mode}"
                
                text = pytesseract.image_to_string(
                    processed_img, 
                    lang=current_lang, 
                    config=custom_config
                )
                return text.strip()
            except Exception as e:
                logger.error(f"OCR failed: {e}")
                raise e

        return await loop.run_in_executor(None, _run_ocr)

    async def recognize_to_data(self, image_data: bytes, lang: Optional[str] = None) -> dict:
        """
        Распознавание с возвратом детальных данных (bounding boxes, confidence).
        """
        loop = asyncio.get_event_loop()
        
        def _run_ocr_data():
            try:
                image = Image.open(io.BytesIO(image_data))
                processed_img = preprocess_image_for_ocr(image)
                current_lang = lang if lang else self.config_lang
                
                # Конфигурация Tesseract
                custom_config = f"--oem 3 --psm {self.psm_mode}"
                
                # Получаем детальные данные
                data = pytesseract.image_to_data(
                    processed_img, 
                    lang=current_lang, 
                    config=custom_config, 
                    output_type=pytesseract.Output.DICT
                )
                return data
            except Exception as e:
                logger.error(f"OCR data extraction failed: {e}")
                raise e

        return await loop.run_in_executor(None, _run_ocr_data)
