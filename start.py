"""
Railway startup script — single-process launcher for backend + Telegram bot.

Replaces railway_start.sh to avoid bash/subprocess issues on Railway.
Runs uvicorn in the main thread and the Telegram bot in a monitored
background subprocess with auto-restart on crash.

IMPORTANT: Handles SIGTERM gracefully so Railway deploys don't leave
ghost bot processes polling Telegram (which causes duplicate responses).
"""

import os
import sys
import logging
import threading
import time
import signal
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("launcher")

# Global reference to bot subprocess so signal handler can kill it
_bot_process = None
_shutting_down = False


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT from Railway during redeploys.

    Immediately kills the bot subprocess so it stops polling Telegram.
    This prevents the old instance from competing with the new instance.
    """
    global _shutting_down
    _shutting_down = True
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down bot subprocess...", sig_name)

    for name, proc in [("ADM bot", _bot_process), ("Agent bot", _agent_bot_process)]:
        if proc and proc.poll() is None:
            logger.info("Killing %s subprocess (PID %d)...", name, proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
                logger.info("%s terminated cleanly.", name)
            except subprocess.TimeoutExpired:
                logger.warning("%s didn't terminate in 5s, force killing...", name)
                proc.kill()

    logger.info("Exiting launcher.")
    sys.exit(0)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _wait_for_backend(port: int, timeout: int = 90) -> bool:
    """Wait for backend health endpoint to respond."""
    import urllib.request
    for i in range(timeout):
        if _shutting_down:
            return False
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


_agent_bot_process = None


def start_telegram_bot(port: int):
    """Start and monitor the Telegram bot subprocess with auto-restart."""
    global _bot_process

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set, skipping ADM bot.")
        return

    bot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot")
    bot_env = {
        **os.environ,
        "API_BASE_URL": f"http://localhost:{port}/api/v1",
        "PYTHONPATH": bot_dir,
    }

    def _monitor_bot():
        """Monitor the bot subprocess and auto-restart on crash."""
        global _bot_process

        # Wait for backend to be ready before first launch
        if not _wait_for_backend(port):
            if _shutting_down:
                return
            logger.error(
                "Backend never became ready after 90s. Starting bot anyway."
            )

        max_restarts = 20
        restart_count = 0
        min_uptime_for_reset = 300  # 5 minutes of stable uptime resets counter
        backoff_base = 5

        while restart_count < max_restarts and not _shutting_down:
            logger.info(
                "Launching Telegram bot subprocess (attempt %d/%d)...",
                restart_count + 1, max_restarts,
            )
            start_time = time.time()

            try:
                _bot_process = subprocess.Popen(
                    [sys.executable, os.path.join(bot_dir, "telegram_bot.py")],
                    env=bot_env,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                logger.info(
                    "Telegram bot subprocess launched (PID %d).", _bot_process.pid
                )

                # Wait for process to complete (blocks until crash or exit)
                exit_code = _bot_process.wait()
                uptime = time.time() - start_time

                if _shutting_down:
                    logger.info("Bot exited during shutdown (expected).")
                    return

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

                # Sleep with shutdown check
                for _ in range(backoff):
                    if _shutting_down:
                        return
                    time.sleep(1)

                # Re-check backend health before restarting
                if not _wait_for_backend(port, timeout=30):
                    if _shutting_down:
                        return
                    logger.warning(
                        "Backend not healthy before bot restart. "
                        "Waiting additional 30s..."
                    )
                    for _ in range(30):
                        if _shutting_down:
                            return
                        time.sleep(1)

            except Exception as e:
                if _shutting_down:
                    return
                logger.error("Error managing bot subprocess: %s", e)
                restart_count += 1
                time.sleep(10)

        if not _shutting_down:
            logger.error(
                "Telegram bot exceeded max restarts (%d). Giving up.",
                max_restarts,
            )

    thread = threading.Thread(target=_monitor_bot, daemon=True, name="bot-monitor")
    thread.start()


def start_agent_bot(port: int):
    """Start and monitor the Agent Telegram bot subprocess."""
    global _agent_bot_process

    token = os.environ.get("AGENT_TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("AGENT_TELEGRAM_BOT_TOKEN not set, skipping Agent bot.")
        return

    project_root = os.path.dirname(os.path.abspath(__file__))
    bot_env = {
        **os.environ,
        "API_BASE_URL": f"http://localhost:{port}/api/v1",
        "PYTHONPATH": project_root,
    }

    def _monitor_agent_bot():
        global _agent_bot_process

        if not _wait_for_backend(port):
            if _shutting_down:
                return
            logger.error("Backend not ready for agent bot. Starting anyway.")

        max_restarts = 20
        restart_count = 0
        min_uptime_for_reset = 300
        backoff_base = 5

        while restart_count < max_restarts and not _shutting_down:
            logger.info("Launching Agent bot subprocess (attempt %d/%d)...", restart_count + 1, max_restarts)
            start_time = time.time()

            try:
                _agent_bot_process = subprocess.Popen(
                    [sys.executable, os.path.join(project_root, "agent_bot", "telegram_bot.py")],
                    env=bot_env,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                logger.info("Agent bot subprocess launched (PID %d).", _agent_bot_process.pid)

                exit_code = _agent_bot_process.wait()
                uptime = time.time() - start_time

                if _shutting_down:
                    return

                logger.warning("Agent bot exited with code %d after %.0fs.", exit_code, uptime)

                if uptime >= min_uptime_for_reset:
                    restart_count = 0
                else:
                    restart_count += 1

                backoff = min(backoff_base * (2 ** min(restart_count, 5)), 120)
                logger.info("Restarting agent bot in %ds...", backoff)
                for _ in range(backoff):
                    if _shutting_down:
                        return
                    time.sleep(1)

            except Exception as e:
                if _shutting_down:
                    return
                logger.error("Error managing agent bot: %s", e)
                restart_count += 1
                time.sleep(10)

    thread = threading.Thread(target=_monitor_agent_bot, daemon=True, name="agent-bot-monitor")
    thread.start()


def main():
    port = int(os.environ.get("PORT", 8000))

    logger.info("=" * 60)
    logger.info("  ADM Platform Launcher v2.7.2")
    logger.info("  Port: %d", port)
    logger.info("=" * 60)

    # Change to backend directory so imports work
    backend_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "backend"
    )
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)

    # ADM Telegram bot
    if os.environ.get("ENABLE_POLLING_BOT", "").lower() in ("true", "1", "yes"):
        logger.info("ENABLE_POLLING_BOT=true — starting ADM polling bot")
        start_telegram_bot(port)
    else:
        logger.info("ADM Telegram bot disabled (running on Vercel via webhook)")

    # Agent Telegram bot
    if os.environ.get("ENABLE_AGENT_BOT", "").lower() in ("true", "1", "yes"):
        logger.info("ENABLE_AGENT_BOT=true — starting Agent bot")
        start_agent_bot(port)
    else:
        logger.info("Agent Telegram bot disabled (set ENABLE_AGENT_BOT=true to enable)")

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
