from app import create_app
import threading
import time
import os


app = create_app()


def sync_background_loop() -> None:
    sync_service = app.extensions.get("sync_service")
    if not sync_service:
        return

    while True:
        try:
            sync_service.maybe_sync()
        except Exception:
            pass
        time.sleep(3)


if __name__ == "__main__":
    threading.Thread(target=sync_background_loop, daemon=True).start()
    debug = os.getenv("FLASK_DEBUG", "0").strip() in {"1", "true", "True"}
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=debug, host=host, port=port)
