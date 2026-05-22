from io import BytesIO

from fastapi import UploadFile
from pypdf import PdfReader

from app.logger import get_logger

logger = get_logger()


async def read_upload_text(file: UploadFile) -> str:
    raw = await file.read()
    filename = (file.filename or "").lower()
    logger.info(
        "Parser: reading uploaded file",
        extra={"uploaded_filename": file.filename, "size_bytes": len(raw)},
    )

    if filename.endswith(".txt"):
        return raw.decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        reader = PdfReader(BytesIO(raw))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(pages)

    return raw.decode("utf-8", errors="ignore")
