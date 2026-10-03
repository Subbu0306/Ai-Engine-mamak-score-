import asyncio

import pytest

from mamakscore.api import CapacityGate
from mamakscore.errors import ServiceError


def test_capacity_rejects_then_recovers():
    async def scenario():
        gate = CapacityGate(1, 0.01)
        await gate.acquire()
        with pytest.raises(ServiceError) as exc:
            await gate.acquire()
        assert exc.value.code == "OVER_CAPACITY"
        gate.release()
        await gate.acquire()
        gate.release()

    asyncio.run(scenario())
