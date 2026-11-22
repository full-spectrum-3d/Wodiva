from fastapi import APIRouter

from app.assistant import kolba
from app.report.api import load

router = APIRouter()


@router.get("/assistant/questions")
async def assistant_questions() -> list[str]:
    return list(kolba.QUICK_QUESTIONS.values())


@router.post("/assistant", response_model=kolba.AssistantAnswer)
async def assistant(body: kolba.AssistantRequest) -> kolba.AssistantAnswer:
    result = await kolba.answer(load(body.report_id), body.question, body.history)
    result.signature = kolba.sign(body.report_id, result.answer)
    return result


@router.post("/assistant/prepare")
async def assistant_prepare(body: kolba.PrepareRequest) -> dict:
    return {"ready": await kolba.prepare(load(body.report_id))}
