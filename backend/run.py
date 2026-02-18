"""
Convenience script to run the application.
Usage: python run.py
"""

import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║     Telkom Paper Research API - Development Server       ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🚀 Starting server at: http://{settings.HOST}:{settings.PORT}                    ║
║  📚 API Docs: http://{settings.HOST}:{settings.PORT}/docs                        ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info"
    )
