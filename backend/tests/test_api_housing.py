from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_hostel


async def test_search_hostels_endpoint_filters(app_client: AsyncClient, db_session: AsyncSession):
    await make_hostel(db_session, name="Affordable Boma", area="Boma", price_ksh=5000)
    await make_hostel(db_session, name="Expensive Boma", area="Boma", price_ksh=20000)

    response = await app_client.get("/api/housing/hostels", params={"max_budget_ksh": 8000})
    assert response.status_code == 200
    names = [h["name"] for h in response.json()]
    assert names == ["Affordable Boma"]


async def test_get_hostel_by_id(app_client: AsyncClient, db_session: AsyncSession):
    hostel = await make_hostel(db_session)
    response = await app_client.get(f"/api/housing/hostels/{hostel.id}")
    assert response.status_code == 200
    assert response.json()["id"] == hostel.id


async def test_get_hostel_not_found(app_client: AsyncClient):
    response = await app_client.get("/api/housing/hostels/does-not-exist")
    assert response.status_code == 404
