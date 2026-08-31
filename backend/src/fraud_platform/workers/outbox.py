from __future__ import annotations

import argparse
import asyncio
import logging

from fraud_platform.api.service import FraudScoringService
from fraud_platform.config import get_settings
from fraud_platform.observability.logging import configure_structured_logging

logger = logging.getLogger("sentinelflow.outbox")


async def run(poll_seconds: float, once: bool) -> None:
    settings = get_settings()
    configure_structured_logging(settings.log_level)
    service = FraudScoringService.from_settings(settings)
    await service.start()
    try:
        while True:
            processed = await service.process_outbox()
            logger.info("outbox_cycle_complete", extra={"processed": processed})
            if once:
                return
            await asyncio.sleep(poll_seconds if processed == 0 else 0)
    finally:
        await service.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process SentinelFlow durable outbox events")
    parser.add_argument("--once", action="store_true", help="Drain one bounded batch and exit")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    asyncio.run(run(args.poll_seconds, args.once))


if __name__ == "__main__":
    main()
