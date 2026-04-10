"""
Image preprocessing utilities for OCR.
Enhances image quality to improve OCR accuracy.
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from pathlib import Path
from typing import Tuple, Optional
import cv2


def preprocess_image(
    image_path: str,
    dpi: int = 300,
    denoise: bool = True,
    binarize: bool = True,
    deskew: bool = True
) -> Tuple[np.ndarray, dict]:
    """
    Preprocess an image for better OCR results.
    
    Args:
        image_path: Path to the input image
        dpi: Target DPI for resizing
        denoise: Apply noise reduction
        binarize: Convert to binary (black and white)
        deskew: Correct image skew
    
    Returns:
        Tuple of (processed image as numpy array, metadata dict)
    """
    # Load image
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    metadata = {
        "original_shape": img.shape,
        "dpi": dpi,
        "operations": []
    }
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    metadata["operations"].append("grayscale")
    
    # Resize if necessary (for low-resolution images)
    height, width = gray.shape[:2]
    scale_factor = 1.0
    
    # Calculate current DPI estimate (assuming standard page size)
    estimated_dpi = (height / 11.0) * 72  # Assuming 11 inch height
    
    if estimated_dpi < dpi:
        scale_factor = dpi / estimated_dpi
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        metadata["operations"].append(f"resize_{scale_factor:.2f}x")
        metadata["new_shape"] = gray.shape
    
    # Denoise
    if denoise:
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        metadata["operations"].append("denoise")
    
    # Deskew
    if deskew:
        gray, angle = correct_skew(gray)
        if abs(angle) > 0.1:
            metadata["operations"].append(f"deskew_{angle:.2f}deg")
    
    # Binarize
    if binarize:
        gray = adaptive_threshold(gray)
        metadata["operations"].append("binarize")
    
    # Sharpen
    kernel = np.array([[-1, -1, -1],
                       [-1,  9, -1],
                       [-1, -1, -1]])
    gray = cv2.filter2D(gray, -1, kernel)
    metadata["operations"].append("sharpen")
    
    return gray, metadata


def correct_skew(image: np.ndarray, delta: float = 1.0, limit: int = 5) -> Tuple[np.ndarray, float]:
    """
    Detect and correct image skew.
    
    Args:
        image: Grayscale image
        delta: Angle increment for search
        limit: Maximum angle to search
    
    Returns:
        Tuple of (deskewed image, rotation angle)
    """
    def determine_score(arr: np.ndarray, angle: float) -> float:
        """Calculate focus score for an angle."""
        rotated = rotate_image(arr, angle)
        # Use Laplacian variance as focus measure
        laplacian = cv2.Laplacian(rotated, cv2.CV_64F)
        return laplacian.var()
    
    # Search for best angle
    scores = []
    angles = np.arange(-limit, limit + delta, delta)
    
    for angle in angles:
        score = determine_score(image, angle)
        scores.append(score)
    
    best_angle = angles[scores.index(max(scores))]
    
    # Rotate to correct skew
    corrected = rotate_image(image, best_angle)
    
    return corrected, best_angle


def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotate an image by a given angle.
    
    Args:
        image: Input image
        angle: Rotation angle in degrees
    
    Returns:
        Rotated image
    """
    image_center = tuple(np.array(image.shape[1::-1]) / 2.0)
    rot_mat = cv2.getRotationMatrix2D(image_center, -angle, 1.0)
    result = cv2.warpAffine(
        image, 
        rot_mat, 
        image.shape[1::-1],
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )
    return result


def adaptive_threshold(image: np.ndarray) -> np.ndarray:
    """
    Apply adaptive thresholding to an image.
    
    Args:
        image: Grayscale image
    
    Returns:
        Binarized image
    """
    # Use adaptive Gaussian thresholding
    binary = cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2
    )
    return binary


def enhance_contrast(image: np.ndarray, factor: float = 1.5) -> np.ndarray:
    """
    Enhance image contrast using CLAHE.
    
    Args:
        image: Grayscale image
        factor: Contrast enhancement factor
    
    Returns:
        Contrast-enhanced image
    """
    clahe = cv2.createCLAHE(clipLimit=factor, tileGridSize=(8, 8))
    enhanced = clahe.apply(image)
    return enhanced


def remove_borders(image: np.ndarray) -> np.ndarray:
    """
    Remove dark borders from scanned images.
    
    Args:
        image: Input image
    
    Returns:
        Image with borders removed
    """
    # Find contours
    thresh = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = cv2.findNonZero(thresh)
    
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        cropped = image[y:y+h, x:x+w]
        return cropped
    
    return image


def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    """Convert PIL image to OpenCV format."""
    import numpy as np
    cv2_image = np.array(pil_image)
    # Convert RGB to BGR if needed
    if len(cv2_image.shape) == 3 and cv2_image.shape[2] == 3:
        cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_RGB2BGR)
    return cv2_image


def cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
    """Convert OpenCV image to PIL format."""
    # Convert BGR to RGB if needed
    if len(cv2_image.shape) == 3 and cv2_image.shape[2] == 3:
        cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(cv2_image)
