from __future__ import annotations

import logging
import sys
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

    uvicorn.run(
        "src.api.server:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
