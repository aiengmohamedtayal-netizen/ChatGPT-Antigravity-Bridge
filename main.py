"""Preview and container entrypoint launching the FastAPI Bridge on port 3000."""

import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
