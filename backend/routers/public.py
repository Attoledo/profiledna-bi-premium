from __future__ import annotations

import re
import unicodedata

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.database import get_session
from backend.repositories import attempt as repo_attempt
from backend.repositories import cliente as repo_cliente
from backend.repositories import invite as repo_invite
from backend.services.autosave import get_attempt_by_token, recompute_progress, upsert_answer
from backend.services.invite_flow import start_attempt_from_invite
from backend.services.public_views import (
    PublicFlowNotFound,
    build_report_context,
    build_review_context,
    ensure_report_pdf,
)
from backend.services.submit import SubmitIncompleteError, submit_attempt
from backend.services.token import token_hash
from backend.ssot.loader import load_json

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


def _load_questions():
    return load_json("data/ssot/profiledna/v1/questions_100.json")


def _load_gabarito_map():
    data = load_json("data/ssot/profiledna/v1/gabarito_100.json")
    result = {}
    for item in data:
        result[int(item["number"])] = (
            str(item["letter_if_A"]),
            str(item["letter_if_B"]),
        )
    return result


def _build_download_name_slug(
    nome: str | None,
    sobrenome: str | None,
    fallback: str,
    *,
    max_length: int = 80,
) -> str:
    raw = " ".join(
        part.strip()
        for part in [str(nome or ""), str(sobrenome or "")]
        if str(part or "").strip()
    ).strip()

    if not raw:
        raw = str(fallback or "").strip()

    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    ascii_text = re.sub(r"-{2,}", "-", ascii_text).strip("-")

    if not ascii_text:
        ascii_text = str(fallback or "").strip().lower()

    if max_length > 0:
        ascii_text = ascii_text[:max_length].strip("-")

    return ascii_text or str(fallback or "arquivo").strip().lower()


async def _get_question_payload(token: str, number: int):
    if number < 1 or number > 100:
        return None, RedirectResponse(url=f"/t/{token}/revisao", status_code=303)

    questions = _load_questions()
    question = None
    for item in questions:
        if int(item["number"]) == int(number):
            question = item
            break

    if not question:
        return None, HTMLResponse("Question not found in SSOT", status_code=500)

    async with get_session() as session:
        attempt = await get_attempt_by_token(session, token)
        if not attempt:
            return None, HTMLResponse("Invalid token", status_code=404)

        progress = int(attempt.progress or 0)

        if str(attempt.status or "").upper() == "SUBMITTED":
            return None, RedirectResponse(url=f"/t/{token}/finalizado", status_code=303)

    payload = {
        "token": token,
        "number": int(number),
        "option_a": question["option_a"],
        "option_b": question["option_b"],
        "progress": progress,
    }
    return payload, None


async def _render_question(request: Request, token: str, number: int):
    payload, error_response = await _get_question_payload(token, number)
    if error_response is not None:
        return error_response

    route_mode = "t" if request.url.path.startswith("/t/") else "p"
    current_choice = None

    async with get_session() as session:
        attempt = await get_attempt_by_token(session, token)
        if attempt:
            answers = await repo_attempt.list_answers_by_attempt_id(session, attempt.id)
            for answer in answers:
                try:
                    answer_number = int(getattr(answer, "question_number", 0) or 0)
                except Exception:
                    answer_number = 0

                if answer_number == int(number):
                    raw_choice = str(getattr(answer, "choice", "") or "").strip().upper()
                    if raw_choice in ("A", "B"):
                        current_choice = raw_choice
                    break

    can_go_back = int(number) > 1
    can_advance = current_choice in ("A", "B")

    previous_href = f"/{route_mode}/{token}/q/{int(number) - 1}" if can_go_back else None
    next_nav_href = f"/{route_mode}/{token}/revisao" if int(number) >= 100 else f"/{route_mode}/{token}/q/{int(number) + 1}"

    return templates.TemplateResponse(
        "public/question.html",
        {
            "request": request,
            "route_mode": route_mode,
            "current_choice": current_choice,
            "can_go_back": can_go_back,
            "can_advance": can_advance,
            "previous_href": previous_href,
            "next_nav_href": next_nav_href,
            "brand_logo_src": "/static/img/dna-logo.png",
            **payload,
        },
    )


async def _handle_answer(token: str, number: int, choice: str, next_base: str):
    if choice not in ("A", "B"):
        return HTMLResponse("Invalid choice", status_code=400)

    gmap = _load_gabarito_map()
    if int(number) not in gmap:
        return HTMLResponse("Invalid question_number", status_code=400)

    letter_a, letter_b = gmap[int(number)]
    letter_scored = letter_a if choice == "A" else letter_b

    async with get_session() as session:
        async with session.begin():
            attempt = await get_attempt_by_token(session, token)
            if not attempt:
                return HTMLResponse("Invalid token", status_code=404)

            if str(attempt.status or "").upper() == "SUBMITTED":
                return HTMLResponse("Attempt already submitted (immutable)", status_code=409)

            await upsert_answer(session, attempt.id, int(number), choice, letter_scored)
            await recompute_progress(session, attempt)

    next_number = int(number) + 1
    if next_number > 100:
        return RedirectResponse(url=f"{next_base}/{token}/revisao", status_code=303)

    return RedirectResponse(url=f"{next_base}/{token}/q/{next_number}", status_code=303)


async def _render_review(request: Request, token: str, route_mode: str):
    async with get_session() as session:
        try:
            ctx = await build_review_context(session, token)
        except PublicFlowNotFound as exc:
            msg = str(exc) or "Invalid token"
            if "Invalid token" in msg:
                return HTMLResponse("Invalid token", status_code=404)
            return HTMLResponse(msg, status_code=400)

    if ctx.is_submitted:
        if route_mode == "t":
            return RedirectResponse(url=f"/t/{token}/finalizado", status_code=303)
        return RedirectResponse(url=f"/p/{token}/report", status_code=303)

    confirm_href = f"/{route_mode}/{token}/confirmar" if route_mode == "t" else f"/p/{token}/confirm"
    continue_href = f"/{route_mode}/{token}/q/{ctx.next_question}"

    return templates.TemplateResponse(
        "public/review.html",
        {
            "request": request,
            "token": token,
            "answered_count": ctx.answered_count,
            "progress": ctx.progress,
            "next_question": ctx.next_question,
            "continue_href": continue_href,
            "confirm_href": confirm_href,
            "route_mode": route_mode,
        },
    )


async def _render_confirm(request: Request, token: str, route_mode: str):
    async with get_session() as session:
        attempt = await get_attempt_by_token(session, token)
        if not attempt:
            return HTMLResponse("Invalid token", status_code=404)

        if str(attempt.status or "").upper() == "SUBMITTED":
            if route_mode == "t":
                return RedirectResponse(url=f"/t/{token}/finalizado", status_code=303)
            return RedirectResponse(url=f"/p/{token}/report", status_code=303)

        answers = await repo_attempt.list_answers_by_attempt_id(session, attempt.id)
        if len(answers) < 100:
            review_url = f"/{route_mode}/{token}/revisao" if route_mode == "t" else f"/p/{token}/review"
            return RedirectResponse(url=review_url, status_code=303)

    submit_action = f"/{route_mode}/{token}/submit"
    back_href = f"/{route_mode}/{token}/revisao" if route_mode == "t" else f"/p/{token}/review"

    return templates.TemplateResponse(
        "public/confirm.html",
        {
            "request": request,
            "token": token,
            "submit_action": submit_action,
            "back_href": back_href,
            "route_mode": route_mode,
        },
    )


async def _render_report(request: Request, token: str, route_mode: str):
    async with get_session() as session:
        try:
            ctx = await build_report_context(session, token)
        except PublicFlowNotFound as exc:
            msg = str(exc) or "No computed result yet"
            if "Invalid token" in msg:
                return HTMLResponse("Invalid token", status_code=404)
            return HTMLResponse(msg, status_code=400)

    template_name = getattr(ctx, "report_template", None) or "reports/report_full.html"

    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "token": token,
            "participant": ctx.participant,
            "attempt": ctx.attempt_payload,
            "scores": ctx.scores,
            "bands": ctx.bands,
            "ranking": ctx.ranking,
            "interpretations": ctx.interpretations,
            "sintese_executiva": ctx.sintese_executiva,
            "paineis_area": ctx.paineis_area,
            "pdi_competencias": ctx.pdi_competencias,
            "gestor_rh": ctx.gestor_rh,
            "nota_tecnica": ctx.nota_tecnica,
            "route_mode": route_mode,
        },
    )


async def _serve_report_pdf(token: str, filename_prefix: str = "report"):
    async with get_session() as session:
        async with session.begin():
            try:
                attempt_id_str, pdf_path = await ensure_report_pdf(session, token)
            except PublicFlowNotFound as exc:
                msg = str(exc) or "No report snapshot yet"
                if "Invalid token" in msg:
                    return HTMLResponse("Invalid token", status_code=404)
                return HTMLResponse(msg, status_code=400)

            attempt = await get_attempt_by_token(session, token)
            participant = getattr(attempt, "participant", None) if attempt is not None else None
            filename_slug = _build_download_name_slug(
                getattr(participant, "nome", None) if participant is not None else None,
                getattr(participant, "sobrenome", None) if participant is not None else None,
                attempt_id_str,
            )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{filename_prefix}_{filename_slug}.pdf",
    )


async def _invite_token_is_valid(token: str) -> bool:
    token_text = str(token or "").strip()
    if not token_text:
        return False

    async with get_session() as session:
        invite = await repo_invite.get_invite_by_token_hash(session, token_hash(token_text))
        return invite is not None


async def _require_valid_invite_token_response(token: str):
    if await _invite_token_is_valid(token):
        return None
    return HTMLResponse("Invalid token", status_code=404)


# =========================
# Landing institucional / fluxo default legado
# =========================


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("/start", response_class=HTMLResponse)
async def start_get(request: Request):
    return HTMLResponse("Not Found", status_code=404)


@router.post("/start")
async def start_post(
    request: Request,
    nome: str = Form(...),
    sobrenome: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    empresa_nome: Optional[str] = Form(None),
    tipo_aplicacao: str = Form(...),
):
    return HTMLResponse("Not Found", status_code=404)


# =========================
# Compat legado /p/*
# =========================


@router.get("/p/{token}/q/{number}", response_class=HTMLResponse)
async def question_legacy(request: Request, token: str, number: int):
    return await _render_question(request, token, number)


@router.post("/p/{token}/autosave")
async def autosave_legacy(token: str, question_number: int = Form(...), choice: str = Form(...)):
    return await _handle_answer(token, question_number, choice, next_base="/p")


@router.get("/p/{token}/review", response_class=HTMLResponse)
async def review_legacy(request: Request, token: str):
    return await _render_review(request, token, route_mode="p")


@router.get("/p/{token}/confirm", response_class=HTMLResponse)
async def confirm_legacy(request: Request, token: str):
    return await _render_confirm(request, token, route_mode="p")


@router.post("/p/{token}/submit")
async def submit_legacy(token: str):
    async with get_session() as session:
        async with session.begin():
            attempt = await get_attempt_by_token(session, token)
            if not attempt:
                return HTMLResponse("Invalid token", status_code=404)

            try:
                await submit_attempt(session, attempt)
            except SubmitIncompleteError:
                return RedirectResponse(url=f"/p/{token}/review", status_code=303)

    return RedirectResponse(url=f"/p/{token}/report", status_code=303)


@router.get("/p/{token}/report", response_class=HTMLResponse)
async def report_legacy(request: Request, token: str):
    return await _render_report(request, token, route_mode="p")


@router.get("/p/{token}/report/pdf")
async def report_pdf_legacy(token: str):
    return await _serve_report_pdf(token, filename_prefix="report")


@router.head("/p/{token}/report/pdf")
async def report_pdf_legacy_head(token: str):
    return await _serve_report_pdf(token, filename_prefix="report")


# =========================
# Fluxo canônico SSOT /t/*
# =========================


@router.get("/t/{token}", response_class=HTMLResponse)
async def invite_landing(request: Request, token: str):
    invalid_response = await _require_valid_invite_token_response(token)
    if invalid_response is not None:
        return invalid_response

    return templates.TemplateResponse(
        "public/landing.html",
        {
            "request": request,
            "title": "ProfileDNA",
            "subtitle": "Convite",
            "token": token,
            "cta_href": f"/t/{token}/identificacao",
            "is_invite_flow": True,
        },
    )


@router.post("/t/{token}")
async def invite_landing_post(token: str):
    return RedirectResponse(url=f"/t/{token}/identificacao", status_code=303)


@router.get("/t/{token}/identificacao", response_class=HTMLResponse)
async def identificacao_get(request: Request, token: str):
    invalid_response = await _require_valid_invite_token_response(token)
    if invalid_response is not None:
        return invalid_response

    empresa_nome = ""
    async with get_session() as session:
        invite = await repo_invite.get_invite_by_token_hash(session, token_hash(token))
        if invite and getattr(invite, "cliente_id", None):
            cliente = await repo_cliente.get_cliente_by_id(session, invite.cliente_id)
            if cliente:
                empresa_nome = str(getattr(cliente, "nome", "") or "").strip()

    return templates.TemplateResponse(
        "public/identification.html",
        {
            "request": request,
            "token": token,
            "error": None,
            "empresa_nome": empresa_nome,
            "form_action": f"/t/{token}/identificacao",
            "route_mode": "t",
            "form_values": {
                "nome": "",
                "sobrenome": "",
                "email": "",
            },
        },
    )


@router.post("/t/{token}/identificacao")
async def identificacao_post(
    request: Request,
    token: str,
    nome: str = Form(...),
    sobrenome: str = Form(...),
    email: str = Form(...),
):
    nome = str(nome or "").strip()
    sobrenome = str(sobrenome or "").strip()
    email = str(email or "").strip()

    empresa_nome = ""
    async with get_session() as session:
        invite = await repo_invite.get_invite_by_token_hash(session, token_hash(token))
        if invite and getattr(invite, "cliente_id", None):
            cliente = await repo_cliente.get_cliente_by_id(session, invite.cliente_id)
            if cliente:
                empresa_nome = str(getattr(cliente, "nome", "") or "").strip()

    if not nome or not sobrenome or not email:
        return templates.TemplateResponse(
            "public/identification.html",
            {
                "request": request,
                "token": token,
                "error": "Preencha obrigatoriamente nome, sobrenome e e-mail.",
                "empresa_nome": empresa_nome,
                "form_action": f"/t/{token}/identificacao",
                "route_mode": "t",
                "form_values": {
                    "nome": nome,
                    "sobrenome": sobrenome,
                    "email": email,
                },
            },
            status_code=400,
        )

    async with get_session() as session:
        try:
            await start_attempt_from_invite(
                session,
                token=token,
                nome=nome,
                sobrenome=sobrenome,
                email=email,
            )
        except Exception:
            return templates.TemplateResponse(
                "public/identification.html",
                {
                    "request": request,
                    "token": token,
                    "error": "Invite inválido, expirado ou sem cliente vinculado.",
                    "empresa_nome": empresa_nome,
                    "form_action": f"/t/{token}/identificacao",
                    "route_mode": "t",
                    "form_values": {
                        "nome": nome,
                        "sobrenome": sobrenome,
                        "email": email,
                    },
                },
                status_code=400,
            )

    response = RedirectResponse(url=f"/t/{token}/q/1", status_code=303)
    response.set_cookie(
        key="attempt_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/t/",
    )
    return response


@router.get("/t/{token}/q/{number}", response_class=HTMLResponse)
async def question_canonical(request: Request, token: str, number: int):
    return await _render_question(request, token, number)


@router.post("/t/{token}/q/{number}/answer")
async def answer_canonical(token: str, number: int, choice: str = Form(...)):
    return await _handle_answer(token, number, choice, next_base="/t")


@router.get("/t/{token}/revisao", response_class=HTMLResponse)
async def review_canonical(request: Request, token: str):
    return await _render_review(request, token, route_mode="t")


@router.get("/t/{token}/confirmar", response_class=HTMLResponse)
async def confirm_canonical(request: Request, token: str):
    return await _render_confirm(request, token, route_mode="t")


@router.post("/t/{token}/submit")
async def submit_canonical(token: str):
    async with get_session() as session:
        async with session.begin():
            attempt = await get_attempt_by_token(session, token)
            if not attempt:
                return HTMLResponse("Invalid token", status_code=404)

            try:
                await submit_attempt(session, attempt)
            except SubmitIncompleteError:
                return RedirectResponse(url=f"/t/{token}/revisao", status_code=303)

    return RedirectResponse(url=f"/t/{token}/finalizado", status_code=303)


@router.get("/t/{token}/finalizado", response_class=HTMLResponse)
async def finished_canonical(request: Request, token: str):
    return templates.TemplateResponse(
        "public/finished.html",
        {
            "request": request,
            "token": token,
            "result_href": f"/t/{token}/resultado",
            "pdf_href": f"/t/{token}/resultado/pdf",
            "route_mode": "t",
        },
    )


@router.get("/t/{token}/resultado", response_class=HTMLResponse)
async def report_canonical(request: Request, token: str):
    return await _render_report(request, token, route_mode="t")


@router.get("/t/{token}/resultado/pdf")
async def report_pdf_canonical(token: str):
    return await _serve_report_pdf(token, filename_prefix="report")


@router.head("/t/{token}/resultado/pdf")
async def report_pdf_canonical_head(token: str):
    return await _serve_report_pdf(token, filename_prefix="report")
