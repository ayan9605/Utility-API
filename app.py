import io
import warnings
from typing import List, Optional
import pymupdf
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import DecompressionBombError, DecompressionBombWarning

app = FastAPI(title="Lightweight AI Image & PDF Utility API", version="2.3")

# Security and validation constraints
MAX_UPLOAD_SIZE_MB = 25
MAX_IMAGE_DIMENSION = 10000
MAX_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_IMAGES_IN_PDF = 50
MAX_TOTAL_IMAGES_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 100

Image.MAX_IMAGE_PIXELS = 40_000_000

def validate_image_bytes(image_bytes: bytes):
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")
    if len(image_bytes) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_MB}MB.")
    try:
        img_check = Image.open(io.BytesIO(image_bytes))
        if getattr(img_check, "is_animated", False):
            # Documented behavior: Animated images process first frame only
            pass
        if img_check.width > MAX_IMAGE_DIMENSION or img_check.height > MAX_IMAGE_DIMENSION:
            raise HTTPException(status_code=400, detail=f"Image dimensions exceed max limit of {MAX_IMAGE_DIMENSION}px.")
        
        # Localized warning checking for decompression bombs
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always", DecompressionBombWarning)
            img_check.verify()
            for warning in w:
                if issubclass(warning.category, DecompressionBombWarning):
                    raise HTTPException(status_code=400, detail="Image exceeds maximum allowable pixel limits (Decompression Bomb detected).")
    except DecompressionBombError:
        raise HTTPException(status_code=400, detail="Image exceeds maximum allowable pixel limits.")
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Invalid or unsupported image file format.")


# ==========================================
# 1. IMAGE UTILITIES MODULE
# ==========================================

@app.post("/v1/image/resize")
async def resize_image(
    file: UploadFile = File(...),
    width: Optional[int] = Form(None, gt=0, le=MAX_IMAGE_DIMENSION),
    height: Optional[int] = Form(None, gt=0, le=MAX_IMAGE_DIMENSION),
    fit: str = Form("contain", description="Fit mode: contain (fixed canvas), cover (fill & crop), fill (stretch), inside (fit without enlarging), outside (cover without cropping)"),
    pixel_format: str = Form("RGB", description="Internal channel mode: RGB, RGBA, L"),
    output_format: str = Form("JPEG", description="Output container format: JPEG, PNG, WEBP"),
    quality: int = Form(85, ge=1, le=100),
    max_file_size_kb: Optional[int] = Form(None, gt=0)
):
    try:
        image_bytes = await file.read(MAX_BYTES + 1)
        validate_image_bytes(image_bytes)
        
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        
        orig_w, orig_h = img.size
        orig_mode = img.mode

        fit_mode = fit.lower()
        if fit_mode not in ["contain", "cover", "fill", "inside", "outside"]:
            raise HTTPException(status_code=422, detail="Invalid fit mode. Choose from contain, cover, fill, inside, outside.")

        # Resizing execution with explicit fit semantics and dimension clamping
        if width and height:
            if fit_mode == "fill":
                target_w, target_h = width, height
            elif fit_mode == "contain":
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                new_w, new_h = img.size
                canvas = Image.new(img.mode if img.mode in ["RGB", "RGBA"] else "RGB", (width, height), (255, 255, 255) if img.mode != "RGBA" else (255, 255, 255, 0))
                paste_x = (width - new_w) // 2
                paste_y = (height - new_h) // 2
                canvas.paste(img, (paste_x, paste_y))
                img = canvas
                target_w, target_h = width, height
            elif fit_mode == "cover":
                img = ImageOps.fit(img, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                target_w, target_h = width, height
            elif fit_mode == "inside":
                target_w = min(width, orig_w)
                target_h = min(height, orig_h)
                img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            elif fit_mode == "outside":
                ratio = max(width / orig_w, height / orig_h)
                target_w = int(orig_w * ratio)
                target_h = int(orig_h * ratio)
                if target_w > MAX_IMAGE_DIMENSION or target_h > MAX_IMAGE_DIMENSION:
                    raise HTTPException(status_code=400, detail=f"Calculated outside dimensions exceed max limit of {MAX_IMAGE_DIMENSION}px.")
                img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        elif width:
            aspect_ratio = int(width * (orig_h / orig_w))
            if width > MAX_IMAGE_DIMENSION or aspect_ratio > MAX_IMAGE_DIMENSION:
                raise HTTPException(status_code=400, detail=f"Dimensions exceed max limit of {MAX_IMAGE_DIMENSION}px.")
            img = img.resize((width, aspect_ratio), Image.Resampling.LANCZOS)
        elif height:
            aspect_ratio = int(height * (orig_w / orig_h))
            if aspect_ratio > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise HTTPException(status_code=400, detail=f"Dimensions exceed max limit of {MAX_IMAGE_DIMENSION}px.")
            img = img.resize((aspect_ratio, height), Image.Resampling.LANCZOS)

        target_px_fmt = pixel_format.upper()
        if target_px_fmt not in ["RGB", "RGBA", "L"]:
            raise HTTPException(status_code=422, detail="Invalid pixel_format. Must be RGB, RGBA, or L.")

        if target_px_fmt == "RGB":
            if img.mode in ["RGBA", "LA"]:
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode == "P":
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            else:
                img = img.convert("RGB")
        elif target_px_fmt == "RGBA":
            if img.mode == "P":
                img = img.convert("RGBA")
            else:
                img = img.convert("RGBA")
        elif target_px_fmt == "L":
            img = img.convert("L")

        out_fmt = output_format.upper()
        if out_fmt not in ["JPEG", "PNG", "WEBP"]:
            raise HTTPException(status_code=422, detail="Invalid output_format. Must be JPEG, PNG, or WEBP.")

        media_map = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
        media_type = media_map.get(out_fmt, "image/jpeg")

        output_buffer = io.BytesIO()
        current_quality = quality
        
        while True:
            output_buffer.seek(0)
            output_buffer.truncate(0)
            
            if out_fmt == "JPEG":
                img.convert("RGB").save(output_buffer, format=out_fmt, quality=current_quality, optimize=True)
            elif out_fmt == "WEBP":
                img.save(output_buffer, format=out_fmt, quality=current_quality)
            elif out_fmt == "PNG":
                png_compression_level = max(0, min(9, int(9 - (current_quality / 100 * 9))))
                img.save(output_buffer, format=out_fmt, optimize=True, compress_level=png_compression_level)
                
            file_size_kb = output_buffer.tell() / 1024
            
            if not max_file_size_kb or file_size_kb <= max_file_size_kb or current_quality <= 10 or out_fmt == "PNG":
                break
            current_quality -= 5

        output_buffer.seek(0)
        
        return StreamingResponse(
            output_buffer, 
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=resized_image.{out_fmt.lower()}",
                "X-Original-Width": str(orig_w),
                "X-Original-Height": str(orig_h),
                "X-Final-Size-KB": f"{file_size_kb:.2f}"
            }
        )
    except HTTPException as he:
        raise he
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error during image processing.")


# ==========================================
# 2. PDF UTILITIES MODULE
# ==========================================

@app.post("/v1/pdf/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    image_quality: int = Form(65, ge=1, le=100),
    target_dpi: int = Form(100, gt=0, le=600)
):
    doc = None
    try:
        pdf_bytes = await file.read(MAX_BYTES + 1)
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded PDF file is empty.")
        if len(pdf_bytes) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="PDF file exceeds maximum allowed size limit.")

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        if doc.is_encrypted:
            raise HTTPException(status_code=400, detail="Encrypted or password-protected PDFs cannot be compressed.")
        
        if len(doc) > MAX_PDF_PAGES:
            raise HTTPException(status_code=400, detail=f"PDF page count exceeds maximum limit of {MAX_PDF_PAGES} pages.")

        original_size = len(pdf_bytes)

        doc.rewrite_images(
            dpi_threshold=target_dpi + 20, 
            dpi_target=target_dpi, 
            quality=image_quality, 
            lossy=True
        )
        
        output_pdf_stream = io.BytesIO()
        doc.save(
            output_pdf_stream, 
            garbage=4, 
            deflate=True, 
            deflate_images=True, 
            deflate_fonts=True,
            use_objstms=True
        )
        
        compressed_size = output_pdf_stream.getbuffer().nbytes
        compression_applied = True

        if compressed_size >= original_size:
            output_pdf_stream = io.BytesIO(pdf_bytes)
            compressed_size = original_size
            compression_applied = False

        compression_pct = round(((original_size - compressed_size) / original_size) * 100, 2) if original_size > 0 else 0.0
        output_pdf_stream.seek(0)
        file_size_kb = compressed_size / 1024

        return StreamingResponse(
            output_pdf_stream,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=compressed_{file.filename}",
                "X-Original-Size": str(original_size),
                "X-Final-Size": str(compressed_size),
                "X-Compression-Applied": str(compression_applied).lower(),
                "X-Compression-Percentage": f"{compression_pct}%",
                "X-Final-PDF-Size-KB": f"{file_size_kb:.2f}"
            }
        )
    except HTTPException as he:
        raise he
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error during PDF compression.")
    finally:
        if doc:
            doc.close()


@app.post("/v1/pdf/images-to-pdf")
async def images_to_pdf(
    files: List[UploadFile] = File(...),
    page_size: str = Form("fit", description="Page format: fit, A4, Letter")
):
    pdf_doc = None
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided for conversion.")
        if len(files) > MAX_IMAGES_IN_PDF:
            raise HTTPException(status_code=400, detail=f"Too many files. Maximum allowed is {MAX_IMAGES_IN_PDF}.")
            
        p_size = page_size.upper()
        if p_size not in ["FIT", "A4", "LETTER"]:
            raise HTTPException(status_code=422, detail="Invalid page_size. Must be fit, A4, or Letter.")

        pdf_doc = pymupdf.open()
        total_batch_size = 0
        valid_images_count = 0
        
        PAGE_SIZES = {
            "A4": (595.27, 841.89),
            "LETTER": (612.00, 792.00)
        }

        for file in files:
            image_bytes = await file.read(MAX_BYTES + 1)
            if not image_bytes:
                continue
            if len(image_bytes) > MAX_BYTES:
                raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds maximum upload size.")
            
            total_batch_size += len(image_bytes)
            if total_batch_size > MAX_TOTAL_IMAGES_BYTES:
                raise HTTPException(status_code=400, detail="Total batch upload size exceeds maximum allowed limit.")

            try:
                img_check = Image.open(io.BytesIO(image_bytes))
                if img_check.width > MAX_IMAGE_DIMENSION or img_check.height > MAX_IMAGE_DIMENSION:
                    raise HTTPException(status_code=400, detail=f"Image {file.filename} exceeds max dimensions.")
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always", DecompressionBombWarning)
                    img_check.verify()
                    for warning in w:
                        if issubclass(warning.category, DecompressionBombWarning):
                            raise HTTPException(status_code=400, detail="Image exceeds maximum allowable pixel limits.")
            except DecompressionBombError:
                raise HTTPException(status_code=400, detail="Image exceeds maximum allowable pixel limits.")
            except UnidentifiedImageError:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is not a valid image format.")
            
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)

            if img.mode in ["RGBA", "LA"]:
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode == "P":
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
                
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="JPEG", quality=90)
            img_bytes_final = img_buffer.getvalue()
            
            if p_size in PAGE_SIZES:
                base_pw, base_ph = PAGE_SIZES[p_size]
                if img.width > img.height:
                    pw, ph = max(base_pw, base_ph), min(base_pw, base_ph)
                else:
                    pw, ph = min(base_pw, base_ph), max(base_pw, base_ph)

                page = pdf_doc.new_page(width=pw, height=ph)
                
                img_ratio = img.width / img.height
                page_ratio = pw / ph
                
                if img_ratio > page_ratio:
                    w = pw
                    h = pw / img_ratio
                    x = 0
                    y = (ph - h) / 2
                else:
                    h = ph
                    w = ph * img_ratio
                    x = (pw - w) / 2
                    y = 0
                rect = pymupdf.Rect(x, y, x + w, y + h)
                page.insert_image(rect, stream=img_bytes_final)
            else:
                page = pdf_doc.new_page(width=img.width, height=img.height)
                rect = pymupdf.Rect(0, 0, img.width, img.height)
                page.insert_image(rect, stream=img_bytes_final)
            
            valid_images_count += 1

        if valid_images_count == 0:
            raise HTTPException(status_code=400, detail="No valid images found to generate a PDF.")

        output_pdf_stream = io.BytesIO()
        pdf_doc.save(output_pdf_stream, garbage=4, deflate=True)
        
        output_pdf_stream.seek(0)
        file_size_kb = output_pdf_stream.getbuffer().nbytes / 1024

        return StreamingResponse(
            output_pdf_stream,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=images_document.pdf",
                "X-Final-PDF-Size-KB": f"{file_size_kb:.2f}"
            }
        )
    except HTTPException as he:
        raise he
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error during PDF generation.")
    finally:
        if pdf_doc:
            pdf_doc.close()
