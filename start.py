"""
Railway startup script — single-process launcher for backend + Telegram bot.

Replaces railway_start.sh to avoid bash/subprocess issues on Railway.
Runs uvicorn in the main thread and the Telegram bot in a monitored
background subprocess with auto-restart on crash.
"""

import os
import sys
import logging
import threading
import time
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("launcher")


def _wait_for_backend(port: int, timeout: int = 90) -> bool:
    """Wait for backend health endpoint to respond."""
    import urllib.request
    for i in range(timeout):
        try:
            resp = urllib.request.urlopen(
                f"http://localhost:{port}/health", timeout=3
            )
            if resp.status == 200:
                logger.info("Backend health check passed (attempt %d).", i + 1)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_telegram_bot(port: int):
    """Start and monitor the Telegram bot subprocess with auto-restart."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set, skipping bot.")
        return

    bot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot")
    bot_env = {
        **os.environ,
        "API_BASE_URL": f"http://localhost:{port}/api/v1",
        "PYTHONPATH": bot_dir,
    }

    def _monitor_bot():
        """Monitor the bot subprocess and auto-restart on crash."""
        # Wait for backend to be ready before first launch
        if not _wait_for_backend(port):
            logger.error(
                "Backend never became ready after 90s. Starting bot anyway."
            )

        max_restarts = 20
        restart_count = 0
        min_uptime_for_reset = 300  # 5 minutes of stable uptime resets counter
        backoff_base = 5

        while restart_count < max_restarts:
            logger.info(
                "Launching Telegram bot subprocess (attempt %d/%d)...",
                restart_count + 1, max_restarts,
            )
            start_time = time.time()

            try:
                proc = subprocess.Popen(
                    [sys.executable, os.path.join(bot_dir, "telegram_bot.py")],
                    env=bot_env,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                logger.info(
                    "Telegram bot subprocess launched (PID %d).", proc.pid
                )

                # Wait for process to complete (blocks until crash or exit)
                exit_code = proc.wait()
                uptime = time.time() - start_time

                logger.warning(
                    "Telegram bot exited with code %d after %.0fs.",
                    exit_code, uptime,
                )

                # If bot ran for a while, reset restart counter
                if uptime >= min_uptime_for_reset:
                    restart_count = 0
                    logger.info(
                        "Bot was stable for %.0fs, resetting restart counter.",
                        uptime,
                    )
                else:
                    restart_count += 1

                # Backoff before restart (exponential with cap)
                backoff = min(backoff_base * (2 ** min(restart_count, 5)), 120)
                logger.info(
                    "Restarting bot in %ds (restart %d/%d)...",
                    backoff, restart_count, max_restarts,
                )
                time.sleep(backoff)

                # Re-check backend health before restarting
                if not _wait_for_backend(port, timeout=30):
                    logger.warning(
                        "Backend not healthy before bot restart. "
                        "Waiting additional 30s..."
                    )
                    time.sleep(30)

            except Exception as e:
                logger.error("Error managing bot subprocess: %s", e)
                restart_count += 1
                time.sleep(10)

        logger.error(
            "Telegram bot exceeded max restarts (%d). Giving up.",
            max_restarts,
        )

    thread = threading.Thread(target=_monitor_bot, daemon=True, name="bot-monitor")
    thread.start()


def main():
    port = int(os.environ.get("PORT", 8000))

    logger.info("=" * 60)
    logger.info("  ADM Platform Launcher")
    logger.info("  Port: %d", port)
    logger.info("=" * 60)

    # Change to backend directory so imports work
    backend_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "backend"
    )
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)

    # Start Telegram bot monitor in background (will wait for backend)
    start_telegram_bot(port)

    # Start uvicorn in the main thread (this blocks and serves requests)
    import uvicorn
    logger.info("Starting uvicorn on 0.0.0.0:%d...", port)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
