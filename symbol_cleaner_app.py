import io
import os
import sys
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse


BASE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)) if getattr(sys, "frozen", False) else BASE_DIR
INDEX_HTML = RESOURCE_DIR / "webapp" / "symbol_cleaner.html"
SERVER_HOST = os.getenv("SYMBOL_CLEANER_HOST", "127.0.0.1").strip() or "127.0.0.1"
SERVER_PORT = int(os.getenv("SYMBOL_CLEANER_PORT", "8877"))
OPEN_BROWSER_ON_START = os.getenv("SYMBOL_CLEANER_OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no"}

app = FastAPI(title="Symbol Cleaner")


def detect_text_encoding(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def build_output_name(filename: str | None) -> str:
    source = Path(filename or "result.txt")
    stem = source.stem or "result"
    suffix = source.suffix or ".txt"
    return f"{stem}_cleaned{suffix}"


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not INDEX_HTML.exists():
        return HTMLResponse("<h1>Missing webapp/symbol_cleaner.html</h1>", status_code=500)
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.post("/api/remove-symbol")
async def remove_symbol(
    text_file: UploadFile = File(...),
    symbol: str = Form(...),
) -> StreamingResponse:
    target = symbol or ""
    if not target:
        raise HTTPException(status_code=400, detail="제거할 기호를 입력해주세요.")

    raw = await text_file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="비어 있는 파일입니다.")

    encoding = detect_text_encoding(raw)
    content = raw.decode(encoding)
    cleaned = content.replace(target, "")
    output_bytes = cleaned.encode("utf-8-sig")
    output_name = build_output_name(text_file.filename)

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )


if __name__ == "__main__":
    import uvicorn

    if OPEN_BROWSER_ON_START:
        webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}")

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_config=None, access_log=False)
