"""
FastAPI application factory and initialization.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .regex_manager import RegexPatternManager
from .model_manager import ModelManager
from .service import SecretDetectionService
from .routes import router, set_detection_service


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI app instance
    """
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION
    )
    
    # Add CORS middleware FIRST - must be before routes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allow all methods
        allow_headers=["*"],  # Allow all headers
    )
    
    # Include routes BEFORE event handlers
    app.include_router(router)
    
    # Register event handlers
    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup."""
        print("="*70)
        print(f"Starting {settings.APP_NAME}")
        print("="*70)
        
        try:
            # Validate configuration
            settings.validate()
            
            # Initialize regex manager
            print("\nInitializing regex pattern manager...")
            regex_manager = RegexPatternManager(settings.REGEX_FILE)
            
            # Initialize model manager
            print("\nInitializing model manager...")
            model_manager = ModelManager(
                model_path=settings.MODEL_PATH,
                device=settings.DEVICE,
                use_quantization=settings.USE_QUANTIZATION,
                max_length=settings.MAX_LENGTH,
                window_size=settings.WINDOW_SIZE
            )
            
            # Initialize detection service
            print("\nInitializing detection service...")
            service = SecretDetectionService(
                regex_manager, 
                model_manager,
                cache_size=settings.CACHE_SIZE
            )
            
            # Set service in routes
            set_detection_service(service)
            
            print("\n" + "="*70)
            print("✓ Server initialized successfully")
            print(f"✓ Device: {model_manager.get_device()}")
            print(f"✓ Patterns loaded: {regex_manager.get_pattern_count()}")
            cache_status = f"enabled (size: {settings.CACHE_SIZE})" if settings.ENABLE_CACHE else "disabled"
            print(f"✓ Cache: {cache_status}")
            print("="*70 + "\n")
            
        except Exception as e:
            print(f"\n✗ Error initializing server: {e}")
            raise
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown."""
        print("\nShutting down server...")
        from .routes import detection_service
        if detection_service:
            detection_service.shutdown()
    
    return app
