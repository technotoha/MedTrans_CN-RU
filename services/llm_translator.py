"""
LLM translation service.
Handles asynchronous translation using OpenAI-compatible APIs with retry logic and rate limiting.
"""

import asyncio
import time
from typing import List, Dict, Optional, Any, Callable
from openai import AsyncOpenAI
from httpx import Timeout

from models.document_models import (
    TranslationChunk, TranslationResult, ProcessingStatus, DocumentElement, ElementType
)
from config.settings import settings
from utils.logging_utils import get_logger, timer


logger = get_logger(__name__)


class LLMTranslationService:
    """
    Asynchronous LLM-based translation service.
    
    Provides reliable translation with:
    - Automatic retry on failures
    - Rate limit handling
    - Context-aware prompts for Chinese→Russian translation
    - Structure preservation
    """
    
    def __init__(self):
        """Initialize the LLM translation service."""
        self.logger = logger
        
        # Initialize async client
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY or "not-needed",
            base_url=settings.LLM_BASE_URL,
            timeout=Timeout(timeout=settings.LLM_TIMEOUT),
            max_retries=settings.LLM_MAX_RETRIES
        )
        
        # Rate limiting
        self._last_request_time = 0.0
        self._request_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
        
        # Translation prompt template
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for translation."""
        return """Ты — профессиональный переводчик с китайского на русский язык.

ТВОИ ЗАДАЧИ:
1. Переводи текст точно и естественно, сохраняя смысл оригинала
2. Сохраняй структуру документа (заголовки, списки, абзацы)
3. Для таблиц переводи только содержимое ячеек, сохраняя формат Markdown
4. Специальные термины и имена собственные транслитерируй или оставляй как есть
5. Не добавляй пояснений, комментариев или мета-текста
6. Если встречаешь непонятные символы или артефакты OCR, пометь их как [?]

ФОРМАТ ОТВЕТА:
- Верни ТОЛЬКО переведённый текст
- Никаких преамбул вроде "Вот перевод:"
- Никаких постскриптумов
- Сохраняй исходное форматирование (переносы строк, отступы)

КАЧЕСТВО ПЕРЕВОДА:
- Избегай калькирования с китайского
- Используй естественный русский синтаксис
- Сохраняй регистр и стиль оригинала (формальный/неформальный)
"""

    @timer(logger, "Translation batch")
    async def translate_chunks(
        self,
        chunks: List[TranslationChunk],
        progress_callback: Optional[Callable] = None
    ) -> List[TranslationChunk]:
        """
        Translate multiple chunks asynchronously.
        
        Args:
            chunks: List of chunks to translate
            progress_callback: Optional callback(chunk, result) for progress
        
        Returns:
            Updated chunks with translations
        """
        tasks = []
        for chunk in chunks:
            task = self._translate_single(chunk, progress_callback)
            tasks.append(task)
        
        # Execute with concurrency limit
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update chunks with results
        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                self.logger.error(f"Translation failed for chunk {chunk.chunk_id}: {result}")
                chunk.status = ProcessingStatus.FAILED
                chunk.translation_notes = str(result)
            else:
                chunk.translated_text = result.translated_text
                chunk.status = ProcessingStatus.COMPLETED
                
                # Update elements
                for elem in chunk.elements:
                    elem.translated_content = result.translated_text
                    elem.translation_status = ProcessingStatus.COMPLETED
        
        return chunks
    
    async def _translate_single(
        self,
        chunk: TranslationChunk,
        progress_callback: Optional[Callable] = None
    ) -> TranslationResult:
        """Translate a single chunk with retry logic."""
        start_time = time.time()
        
        async with self._request_semaphore:
            # Rate limiting
            await self._apply_rate_limit()
            
            # Prepare messages
            user_prompt = self._build_user_prompt(chunk)
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            retries = 0
            last_error = None
            
            while retries <= settings.LLM_MAX_RETRIES:
                try:
                    response = await self.client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=messages,
                        temperature=settings.LLM_TEMPERATURE,
                        max_tokens=settings.LLM_MAX_TOKENS
                    )
                    
                    translated_text = response.choices[0].message.content.strip()
                    
                    # Validate translation
                    warnings = self._validate_translation(
                        chunk.source_text,
                        translated_text
                    )
                    
                    processing_time = int((time.time() - start_time) * 1000)
                    
                    result = TranslationResult(
                        chunk_id=chunk.chunk_id,
                        original_text=chunk.source_text,
                        translated_text=translated_text,
                        source_lang=settings.SOURCE_LANG,
                        target_lang=settings.TARGET_LANG,
                        processing_time_ms=processing_time,
                        model_used=settings.LLM_MODEL,
                        warnings=warnings
                    )
                    
                    if progress_callback:
                        await progress_callback(chunk, result)
                    
                    return result
                    
                except Exception as e:
                    last_error = e
                    retries += 1
                    
                    if retries <= settings.LLM_MAX_RETRIES:
                        wait_time = settings.LLM_RETRY_DELAY * (2 ** (retries - 1))
                        self.logger.warning(
                            f"Translation attempt {retries} failed: {e}. "
                            f"Retrying in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        self.logger.error(
                            f"Translation failed after {retries} attempts: {e}"
                        )
                        raise
            
            raise last_error
    
    def _build_user_prompt(self, chunk: TranslationChunk) -> str:
        """Build user prompt for translation."""
        # Check if this is a table
        is_table = any(
            elem.element_type == ElementType.TABLE for elem in chunk.elements
        )
        
        if is_table:
            prompt = (
                "Переведи содержимое таблицы с китайского на русский. "
                "Сохраняй формат Markdown таблицы.\n\n"
                f"Таблица для перевода:\n{chunk.source_text}"
            )
        else:
            prompt = (
                "Переведи следующий текст с китайского на русский язык:\n\n"
                f"{chunk.source_text}"
            )
        
        return prompt
    
    def _validate_translation(
        self,
        source: str,
        translation: str
    ) -> List[str]:
        """Validate translation quality."""
        warnings = []
        
        # Check for empty translation
        if not translation.strip():
            warnings.append("Empty translation")
        
        # Check for significant length difference
        source_len = len(source)
        trans_len = len(translation)
        
        if trans_len < source_len * 0.3:
            warnings.append(
                f"Translation significantly shorter than source "
                f"({trans_len} vs {source_len} chars)"
            )
        
        # Check for untranslated Chinese characters
        import re
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', translation)
        if len(chinese_chars) > 10:
            warnings.append(
                f"Translation contains {len(chinese_chars)} untranslated Chinese characters"
            )
        
        # Check for common error patterns
        error_patterns = [
            r"I'm sorry",
            r"I cannot",
            r"As an AI",
            r"我不能",
            r"抱歉"
        ]
        for pattern in error_patterns:
            if re.search(pattern, translation, re.IGNORECASE):
                warnings.append(f"Translation contains refusal pattern")
                break
        
        return warnings
    
    async def _apply_rate_limit(self):
        """Apply rate limiting between requests."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        
        if elapsed < settings.LLM_RETRY_DELAY:
            wait_time = settings.LLM_RETRY_DELAY - elapsed
            await asyncio.sleep(wait_time)
        
        self._last_request_time = time.time()
    
    async def close(self):
        """Close the client session."""
        await self.client.close()
