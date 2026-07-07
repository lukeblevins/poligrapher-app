import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

uvicorn.run(
    "poligrapher_app.api.main:app",
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8000")),
    reload=True,
)
