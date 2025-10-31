from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from bot.models.types import Ticker, OrderRequest, Order, Balance


class ExchangeAdapter(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> Order:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Order:
        raise NotImplementedError

    @abstractmethod
    async def fetch_balances(self) -> List[Balance]:
        raise NotImplementedError
