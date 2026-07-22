"""Sotuvchi ekranlari: lid voronkasi, lid detali, qo'ng'iroq qo'shish,
bosqich o'tkazish/yopish. Ruxsat: Role.SELLER."""

from aiohttp import web

from core.database import async_session
from db.repositories import ClientRepository, LeadRepository
from miniapp.util import err
from services import sales_service
from utils.enums import LeadBrand

routes = web.RouteTableDef()


@routes.get("/leads")
async def list_leads(request: web.Request) -> web.Response:
    employee = request["employee"]
    brand_value = request.query.get("brand")

    async with async_session() as session:
        leads = await LeadRepository(session).list_by_seller(employee.id, open_only=True)
        client_repo = ClientRepository(session)

        items = []
        for lead in leads:
            if brand_value and lead.brand.value != brand_value:
                continue
            client = await client_repo.get_by_id(lead.client_id)
            items.append(
                {
                    "id": lead.id,
                    "brand": lead.brand.value,
                    "stage": lead.stage.value,
                    "client_name": client.full_name if client else None,
                    "client_phone": client.phone_number if client else None,
                    "last_contacted_at": lead.last_contacted_at.isoformat(),
                }
            )
    return web.json_response(items)


@routes.get("/leads/{lead_id}")
async def lead_detail(request: web.Request) -> web.Response:
    lead_id = int(request.match_info["lead_id"])
    async with async_session() as session:
        lead = await LeadRepository(session).get_by_id(lead_id)
        if lead is None:
            return err("not_found", 404)
        client = await ClientRepository(session).get_by_id(lead.client_id)

    return web.json_response(
        {
            "id": lead.id,
            "brand": lead.brand.value,
            "stage": lead.stage.value,
            "client_name": client.full_name if client else None,
            "client_phone": client.phone_number if client else None,
            "last_contacted_at": lead.last_contacted_at.isoformat(),
        }
    )


@routes.post("/leads/{lead_id}/advance")
async def advance_lead(request: web.Request) -> web.Response:
    lead_id = int(request.match_info["lead_id"])
    try:
        lead = await sales_service.advance_lead_stage(lead_id)
    except sales_service.LeadNotFoundError:
        return err("not_found", 404)
    except sales_service.InvalidLeadStateError as exc:
        return err(str(exc), 409)
    except sales_service.SalesBoardNotConfiguredError as exc:
        return err(str(exc), 409)
    return web.json_response({"id": lead.id, "stage": lead.stage.value})


@routes.post("/leads/{lead_id}/close")
async def close_lead(request: web.Request) -> web.Response:
    lead_id = int(request.match_info["lead_id"])
    body = await request.json()
    won = bool(body.get("won"))
    try:
        lead = await sales_service.close_lead(lead_id, won=won)
    except sales_service.LeadNotFoundError:
        return err("not_found", 404)
    except sales_service.InvalidLeadStateError as exc:
        return err(str(exc), 409)
    except sales_service.SalesBoardNotConfiguredError as exc:
        return err(str(exc), 409)
    return web.json_response({"id": lead.id, "stage": lead.stage.value})


@routes.post("/leads/{lead_id}/calls")
async def add_call(request: web.Request) -> web.Response:
    employee = request["employee"]
    lead_id = int(request.match_info["lead_id"])
    body = await request.json()
    content = (body.get("content") or "").strip() or None

    try:
        call_log = await sales_service.add_call_log(
            lead_id, employee.id, content=content, audio_file_id=None
        )
    except sales_service.LeadNotFoundError:
        return err("not_found", 404)
    except ValueError as exc:
        return err(str(exc))

    return web.json_response({"id": call_log.id}, status=201)


@routes.get("/brands")
async def list_brands(request: web.Request) -> web.Response:
    return web.json_response([b.value for b in LeadBrand])
