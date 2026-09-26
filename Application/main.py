from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

import uvicorn
from src.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("miles_main")


def main():
    logger.info("=================================================================")
    logger.info("  MILES — Adversarial Verbal Sparring Partner")
    logger.info("  AssemblyAI Voice Agent x DataForge Pathway Rime Hackathons")
    logger.info("=================================================================")
    logger.info(f"  Active STT Engine: {config.active_stt_provider}")
    logger.info(f"  Active TTS Engine: {config.active_tts_provider} (Speaker: {config.rime_speaker})")
    logger.info(f"  Active LLM Engine: {config.active_llm_provider}")
    logger.info(f"  Barge-in Cut-off Target: <{config.barge_in_threshold_ms:.0f} ms")
    logger.info(f"  Server listening on: http://{config.host}:{config.port}")
    logger.info(f"  Interactive API Docs: http://localhost:{config.port}/docs")
    logger.info(f"  WebSocket Endpoint: ws://localhost:{config.port}/ws/debate")
    logger.info("=================================================================")

    primary_port = config.port

    # If running on Railway/cloud, start a daemon thread on alternate common ports
    # (e.g. if primary is 8080, also listen on 8000 so Railway proxy never 502s)
    def _run_secondary(port_to_bind: int):
        try:
            logger.info(f"  [Secondary Listener] Binding also to port {port_to_bind}...")
            uvicorn.run("src.api.server:app", host=config.host, port=port_to_bind, reload=False, log_level="warning")
        except Exception as e:
            logger.info(f"  [Secondary Listener] Port {port_to_bind} not bound (normal if primary already bound): {e}")

    import threading
    for alt_port in [8000, 8080]:
        if alt_port != primary_port:
            t = threading.Thread(target=_run_secondary, args=(alt_port,), daemon=True)
            t.start()

    uvicorn.run(
        "src.api.server:app",
        host=config.host,
        port=primary_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
