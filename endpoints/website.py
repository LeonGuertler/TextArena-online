# import base64, uuid, os
# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel

# class UploadPayload(BaseModel):
#     image: str  # dataURL string

# router = APIRouter()

# @router.post("/upload")
# def upload_image(payload: UploadPayload):
#     print("trying to upload")
#     data_url = payload.image  # e.g. "data:image/jpeg;base64,abc..."
    
#     if not data_url.startswith("data:image/"):
#         raise HTTPException(status_code=400, detail="Invalid image data.")
    
#     # Parse out the header vs the actual base64
#     header, encoded = data_url.split(",", 1)
#     # Example: header = "data:image/jpeg;base64"
    
#     # Determine file extension
#     file_ext = "png"  # default
#     if "image/jpeg" in header:
#         file_ext = "jpg"
#     elif "image/png" in header:
#         file_ext = "png"

#     # Decode the actual bytes
#     image_data = base64.b64decode(encoded)

#     # Create a unique filename
#     filename = f"{uuid.uuid4()}.{file_ext}"
#     output_path = os.path.join("/uploads", filename)

#     # Write to disk
#     with open(output_path, "wb") as f:
#         f.write(image_data)

#     # Return a route that the frontend can use (like "/uploads/filename.jpg")
#     return {"url": f"/uploads/{filename}"}

# website.py
import os
import uuid
import base64

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
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
    # The request.image is assumed to be a data URL or just the Base64 image string
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

    # In this example, we expose the uploads as static files.
    # In production, you'd likely have a different URL or use a cloud storage service.
    image_url = f"/uploads/{filename}"
    return JSONResponse(content={"url": image_url})
