import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# Auto-reload is opt-in (RELOAD=true) — off by default so production runs don't
# spawn the watchdog/reloader process.
uvicorn.run(
    "poligrapher_app.api.main:app",
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8000")),
    reload=os.getenv("RELOAD", "false").lower() in ("1", "true", "yes"),
)
