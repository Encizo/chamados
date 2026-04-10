from app import create_app
import threading
import time


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
    app.run(debug=True)
