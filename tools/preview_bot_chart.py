"""使用与 AstrBot 相同的服务生成真实 PNG，供本地预览。"""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from local_core.bot_commands import ChartSettings, parse_request
from local_core.bot_service import ChartService
from local_core.resources import DATA_DIR


async def preview(args):
    service = ChartService(DATA_DIR)
    try:
        settings = ChartSettings(default_time=args.default_time)
        png = await service.generate(
            parse_request(args.input), settings, datetime.now(timezone.utc)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(png)
        print(args.output.resolve())
    finally:
        await service.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="time 2026-10-10 20:30:00")
    parser.add_argument("--default-time", default="08:00:00")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "bot-validation" / "beijing.png")
    asyncio.run(preview(parser.parse_args()))


if __name__ == "__main__":
    main()
