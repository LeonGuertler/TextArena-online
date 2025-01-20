# main.py
import logging, time
import uvicorn
from pyngrok import ngrok
from threading import Thread

from app import app
from background import start_background_tasks

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # 1. Start your background matchmaking (daemon) thread
    start_background_tasks()

    # 2. Run the server. 
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(2)

    # 3. Connect ngrok tunnel
    public_url = ngrok.connect(addr=8000, hostname="api.textarena.ai", bind_tls=True)
    print(f"Public URL: {public_url}")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
