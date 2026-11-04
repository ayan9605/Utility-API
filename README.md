# Lightweight AI Image & PDF Utility API

A high-performance, lightweight utility API built with **FastAPI**, **Pillow**, and **PyMuPDF**. It provides lightning-fast image resizing, format conversions, size optimization, and robust PDF manipulation capabilities.

---

## Features

### Image Utilities (`/v1/image/`)
* **Smart Resizing & Fit Modes**: Supports `contain`, `cover`, `fill`, `inside`, and `outside` scaling strategies.
* **EXIF Correction**: Automatically detects and corrects image orientation based on EXIF metadata.
* **Target File Size Compression**: Iteratively compresses images to approach a target file size (KB) constraint.
* **Pixel Format Controls**: Separates internal channel management (`RGB`, `RGBA`, `L`) from output container formats (`JPEG`, `PNG`, `WEBP`).
* **Security Guardrails**: Built-in protection against decompression bombs and oversized uploads.

### PDF Utilities (`/v1/pdf/`)
* **Advanced PDF Compression**: Resamples and recompresses embedded raster graphics using configurable DPI and quality thresholds.
* **Images to PDF**: Combines multiple images (`JPG`, `PNG`, `WEBP`) into a clean multi-page PDF with support for auto-oriented `A4`, `Letter`, or native `fit` page layouts.
* **Validation & Safety**: Handles encrypted PDFs securely, enforces page limits, and prevents returning bloated files.

---

## Tech Stack & Dependencies

* **Python** 3.10+
* **FastAPI**: Modern asynchronous web framework for building APIs.
* **Uvicorn**: Lightning-fast ASGI server.
* **Pillow**: Python Imaging Library for robust pixel-level manipulations.
* **PyMuPDF**: High-speed wrapper around MuPDF for document rendering and PDF optimization.

---

## Installation & Setup

1. **Clone the repository and navigate into the project folder:**
   ```bash
   git clone <repository-url>
   cd resizer
Install the required dependencies:

Bash
pip install -r requirements.txt
Run the development server:

Bash
uvicorn app:app --reload
Access Interactive Documentation:
Open your browser and navigate to:

Swagger UI: http://127.0.0.1:8000/docs

ReDoc: http://127.0.0.1:8000/redoc

API Endpoints Overview
1. Resize & Optimize Image
Endpoint: POST /v1/image/resize

Parameters (Form Data):

file: Image file (multipart/form-data)

width: Target width in pixels (optional)

height: Target height in pixels (optional)

fit: Layout strategy (contain, cover, fill, inside, outside)

pixel_format: Internal mode (RGB, RGBA, L)

output_format: Container format (JPEG, PNG, WEBP)

quality: Compression quality level (1–100)

max_file_size_kb: Target maximum size limit in KB (optional)

2. Compress PDF
Endpoint: POST /v1/pdf/compress

Parameters (Form Data):

file: PDF document file

image_quality: Target JPEG quality for embedded document rasters (1–100)

target_dpi: Maximum target DPI threshold for downsampling

3. Images to PDF
Endpoint: POST /v1/pdf/images-to-pdf

Parameters (Form Data):

files: List of image files (JPG, PNG, WEBP)

page_size: Layout specification (fit, A4, Letter)

Production Deployment
For production environments, run the application using a process manager like Gunicorn with Uvicorn worker workers:

Bash
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
