import os
import uuid
import base64

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

router = APIRouter()

# Define a directory where uploaded images will be saved.
UPLOAD_DIR = "./uploads"
# Ensure the directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ImageUploadRequest(BaseModel):
    image: str  # expects a data URL or Base64-encoded string of the PNG


@router.post("/upload")
async def upload_image(request: ImageUploadRequest):
    """
    Accepts a Base64-encoded image (or a data URL) and saves it to disk with a unique filename.
    Returns the relative URL of the uploaded image.
    """
    image_data = request.image

    # If the string contains the data prefix, remove it.
    if image_data.startswith("data:image"):
        try:
            header, encoded = image_data.split(",", 1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid image data format.")
    else:
        encoded = image_data

    try:
        decoded = base64.b64decode(encoded)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to decode Base64 image.")

    # Generate a unique filename
    filename = f"{uuid.uuid4().hex}.png"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(file_path, "wb") as f:
            f.write(decoded)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save image.")

    # Expose the uploads as static files.
    image_url = f"/uploads/{filename}"
    image_url = f"/shared_img/{filename}".replace(".png", "")
    return JSONResponse(content={"url": image_url})


@router.get("/shared_img/{img}", response_class=HTMLResponse)
async def shared_img(img: str, request: Request):
    """
    Returns an HTML page with Twitter Card meta tags dynamically generated for the image.
    The {img} parameter should match the uploaded image's filename (without any directory traversal).
    """
    # Sanitize img to prevent directory traversal (allow only alphanumeric + hex, dash and dot)
    allowed_chars = "0123456789abcdefABCDEF-."
    if not all(c in allowed_chars for c in img):
        raise HTTPException(status_code=400, detail="Invalid image identifier.")

    # Construct the full image URL
    # Adjust the domain as necessary (for production, ensure you have HTTPS and proper domain).
    base_url = str(request.base_url).rstrip("/")
    image_url = f"{base_url}/uploads/{img}.png"

    # Define Twitter Card meta tag content. You could also pull these from a database.
    page_title = "I just got a great result in TextArena!"
    page_desc = "Check out my game result and see my screenshot!"
    page_url = f"{base_url}/shared_img/{img}"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <!-- Twitter Card meta tags -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@your_site_username">
  <meta name="twitter:title" content="{page_title}">
  <meta name="twitter:description" content="{page_desc}">
  <meta name="twitter:image" content="{image_url}">
  <meta name="twitter:url" content="{page_url}">
  <meta name="twitter:domain" content="{request.url.hostname}">
  <title>{page_title}</title>
  <style>
    body {{
      font-family: sans-serif;
      text-align: center;
      margin: 2em;
      background: #f9f9f9;
    }}
    img {{
      max-width: 100%;
      height: auto;
    }}
  </style>
</head>
<body>
  <h1>{page_title}</h1>
  <p>{page_desc}</p>
  <img src="{image_url}" alt="Game result screenshot">
</body>
</html>"""

    return HTMLResponse(content=html_content)
