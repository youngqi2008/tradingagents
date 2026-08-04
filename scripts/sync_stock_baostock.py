#!/usr/bin/env python3
"""通过 BaoStock 同步单只股票历史数据到 MongoDB（Docker 内 AKShare 不可用时的应急方案）"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def sync_stock(symbol: str, days: int = 365) -> int:
    from app.core.database import init_db
    from app.services.historical_data_service import get_historical_data_service
    from tradingagents.dataflows.providers.china.baostock import get_baostock_provider

    await init_db()
    provider = get_baostock_provider()
    hist_service = await get_historical_data_service()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    print(f"同步 {symbol}: {start_date} ~ {end_date} (BaoStock)")

    if not await provider.test_connection():
        print("BaoStock 连接失败")
        return 1

    hist = await provider.get_historical_data(symbol, start_date, end_date)
    if hist is None or hist.empty:
        print(f"未获取到 {symbol} 的历史数据")
        return 1

    saved = await hist_service.save_historical_data(
        symbol=symbol,
        data=hist,
        data_source="baostock",
        market="CN",
        period="daily",
    )
    print(f"已写入 MongoDB: {saved} 条记录")

    info = await provider.get_stock_basic_info(symbol)
    if info:
        print(f"股票名称: {info.get('name', '未知')}")

    return 0


def main():
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "002281").zfill(6)
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 365
    raise SystemExit(asyncio.run(sync_stock(symbol, days)))


if __name__ == "__main__":
    main()
