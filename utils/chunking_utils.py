"""
Text chunking utilities for translation.
Splits documents into optimal chunks for LLM processing while preserving context.
"""

import re
from typing import List, Tuple, Optional
from pathlib import Path
import hashlib

from models.document_models import DocumentElement, ElementType, TranslationChunk, ProcessingStatus


def generate_chunk_id(elements: List[DocumentElement]) -> str:
    """Generate a unique ID for a chunk based on its content."""
    content = "".join([e.content for e in elements])
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]


def smart_chunk_elements(
    elements: List[DocumentElement],
    max_chars: int = 2000,
    overlap_chars: int = 200,
    respect_structure: bool = True
) -> List[TranslationChunk]:
    """
    Split document elements into translation-optimized chunks.
    
    Args:
        elements: List of document elements to chunk
        max_chars: Maximum characters per chunk
        overlap_chars: Number of overlapping characters between chunks
        respect_structure: Whether to avoid splitting tables/headers
    
    Returns:
        List of TranslationChunk objects
    """
    if not elements:
        return []
    
    chunks = []
    current_chunk_elements = []
    current_text_length = 0
    
    # Separate structural elements from regular text
    structural_types = {ElementType.TABLE, ElementType.IMAGE, ElementType.HEADER}
    
    i = 0
    while i < len(elements):
        element = elements[i]
        
        # Handle structural elements separately
        if element.element_type in structural_types and respect_structure:
            # Flush current chunk if it has content
            if current_chunk_elements:
                chunk = create_chunk(current_chunk_elements, overlap_chars)
                chunks.append(chunk)
                current_chunk_elements = []
                current_text_length = 0
            
            # Create individual chunk for structural element
            if element.element_type == ElementType.TABLE and element.table_data:
                # Tables get their own chunk with markdown representation
                table_markdown = element.table_data.to_markdown()
                table_element = element.model_copy()
                table_element.content = table_markdown
                table_chunk = TranslationChunk(
                    chunk_id=generate_chunk_id([table_element]),
                    elements=[table_element],
                    source_text=table_markdown,
                    status=ProcessingStatus.PENDING
                )
                chunks.append(table_chunk)
            else:
                # Images and other elements - keep metadata but minimal text
                chunk = TranslationChunk(
                    chunk_id=generate_chunk_id([element]),
                    elements=[element],
                    source_text=element.content,
                    status=ProcessingStatus.PENDING
                )
                chunks.append(chunk)
            
            i += 1
            continue
        
        # Regular text element
        element_text = element.content.strip()
        element_length = len(element_text)
        
        # If single element exceeds max, split it
        if element_length > max_chars:
            # Flush current chunk first
            if current_chunk_elements:
                chunk = create_chunk(current_chunk_elements, overlap_chars)
                chunks.append(chunk)
                current_chunk_elements = []
                current_text_length = 0
            
            # Split the large element
            sub_chunks = split_large_text(element, max_chars, overlap_chars)
            chunks.extend(sub_chunks)
            i += 1
            continue
        
        # Check if adding this element would exceed limit
        if current_text_length + element_length > max_chars:
            # Create chunk with overlap
            if current_chunk_elements:
                chunk = create_chunk(current_chunk_elements, overlap_chars)
                chunks.append(chunk)
                
                # Keep some overlap for context
                if overlap_chars > 0 and current_chunk_elements:
                    # Start new chunk with last few elements for continuity
                    overlap_elements = get_overlap_elements(
                        current_chunk_elements, 
                        overlap_chars
                    )
                    current_chunk_elements = overlap_elements
                    current_text_length = sum(len(e.content) for e in overlap_elements)
                else:
                    current_chunk_elements = []
                    current_text_length = 0
        
        # Add element to current chunk
        current_chunk_elements.append(element)
        current_text_length += element_length
        i += 1
    
    # Don't forget the last chunk
    if current_chunk_elements:
        chunk = create_chunk(current_chunk_elements, overlap_chars)
        chunks.append(chunk)
    
    return chunks


def create_chunk(
    elements: List[DocumentElement], 
    overlap_chars: int = 0
) -> TranslationChunk:
    """Create a translation chunk from a list of elements."""
    # Combine text from all elements, preserving structure
    texts = []
    for elem in elements:
        if elem.element_type == ElementType.PARAGRAPH:
            texts.append(elem.content.strip())
        elif elem.element_type == ElementType.HEADER:
            texts.append(f"\n## {elem.content.strip()}\n")
        elif elem.element_type == ElementType.LIST_ITEM:
            texts.append(f"• {elem.content.strip()}")
        else:
            texts.append(elem.content.strip())
    
    combined_text = "\n\n".join(texts)
    
    return TranslationChunk(
        chunk_id=generate_chunk_id(elements),
        elements=elements,
        source_text=combined_text,
        status=ProcessingStatus.PENDING
    )


def get_overlap_elements(
    elements: List[DocumentElement], 
    target_chars: int
) -> List[DocumentElement]:
    """Get the last elements that fit within target character count."""
    if not elements:
        return []
    
    overlap = []
    char_count = 0
    
    # Go backwards through elements
    for elem in reversed(elements):
        elem_len = len(elem.content)
        if char_count + elem_len > target_chars:
            break
        overlap.insert(0, elem)
        char_count += elem_len
    
    return overlap


def split_large_text(
    element: DocumentElement, 
    max_chars: int, 
    overlap_chars: int
) -> List[TranslationChunk]:
    """Split a large text element into multiple chunks."""
    text = element.content
    chunks = []
    
    # Try to split at sentence boundaries
    sentences = re.split(r'(?<=[。！？!?\.])\s*', text)
    
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sentence_len = len(sentence)
        
        if current_length + sentence_len > max_chars:
            # Create chunk
            chunk_text = " ".join(current_chunk)
            chunk = TranslationChunk(
                chunk_id=hashlib.md5(chunk_text.encode()).hexdigest()[:12],
                elements=[element.model_copy()],
                source_text=chunk_text,
                status=ProcessingStatus.PENDING
            )
            chunks.append(chunk)
            
            # Overlap
            if overlap_chars > 0 and current_chunk:
                # Keep last sentences for overlap
                overlap_text = " ".join(current_chunk[-3:])  # Last 3 sentences
                current_chunk = [overlap_text]
                current_length = len(overlap_text)
            else:
                current_chunk = []
                current_length = 0
        
        current_chunk.append(sentence)
        current_length += sentence_len
    
    # Last chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunk_elem = element.model_copy()
        chunk_elem.content = chunk_text
        chunk = TranslationChunk(
            chunk_id=hashlib.md5(chunk_text.encode()).hexdigest()[:12],
            elements=[chunk_elem],
            source_text=chunk_text,
            status=ProcessingStatus.PENDING
        )
        chunks.append(chunk)
    
    return chunks


def merge_chunks_by_page(chunks: List[TranslationChunk]) -> dict:
    """Group chunks by page number for ordered processing."""
    pages = {}
    for chunk in chunks:
        for elem in chunk.elements:
            page_num = elem.page_number
            if page_num not in pages:
                pages[page_num] = []
            if chunk not in pages[page_num]:
                pages[page_num].append(chunk)
            break
    
    return dict(sorted(pages.items()))


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Estimate token count for a text string.
    Rough approximation: 1 token ≈ 4 characters for Chinese, 1 token ≈ 1.3 words for English
    """
    # Count Chinese characters
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # Count other characters
    other_text = re.sub(r'[\u4e00-\u9fff]', '', text)
    other_chars = len(other_text)
    
    # Approximate token count
    # Chinese: ~1.5 chars per token
    # Other: ~4 chars per token average
    tokens = (chinese_chars / 1.5) + (other_chars / 4)
    
    return int(tokens)
