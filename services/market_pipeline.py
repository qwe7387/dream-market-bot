from __future__ import annotations

from dataclasses import dataclass

from core.config import Settings
from domain.models import EconomySnapshot, MarketAnalysis, MarketScan
from services.history import PriceHistoryService
from services.market import analyze_market
from services.resolver import ItemResolver


@dataclass(frozen=True)
class ProcessedMarketScan:
    scan: MarketScan
    economy: EconomySnapshot
    analysis: MarketAnalysis


class MarketPipeline:
    """Resolve, analyze, and persist one market scan without Discord concerns."""

    def __init__(
        self,
        *,
        settings: Settings,
        resolver: ItemResolver,
        history_service: PriceHistoryService,
    ) -> None:
        self.settings = settings
        self.resolver = resolver
        self.history_service = history_service

    async def process(self, scan: MarketScan, *, period: int = 7) -> ProcessedMarketScan:
        resolved = await self.resolver.resolve_economy(
            item_id=scan.item_id,
            ocr_item_name=scan.item_name,
            period=period,
        )
        normalized_scan = scan.with_item_name(resolved.item_name)
        cheapest = normalized_scan.cheapest
        analysis = analyze_market(
            cheapest.price,
            resolved.economy.average_price,
            self.settings,
        )
        await self.history_service.add_record(
            item_id=normalized_scan.item_id,
            item_name=normalized_scan.item_name,
            listing_price=cheapest.price,
            net_after_tax=analysis.net_after_tax,
            average_price=resolved.economy.average_price,
            seller=cheapest.seller,
            shop_quantity=cheapest.quantity,
            recommendation=analysis.recommendation,
        )
        return ProcessedMarketScan(
            scan=normalized_scan,
            economy=resolved.economy,
            analysis=analysis,
        )
