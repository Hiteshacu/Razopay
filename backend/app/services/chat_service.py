from __future__ import annotations

from typing import Any

import httpx

from ..config import settings
from ..schemas import ChatRequest, ChatResponse, ChatSource


LANGUAGE_NAMES = {
    "en": "English",
    "kn": "Kannada",
    "hi": "Hindi",
}


class ChatService:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(connect=8.0, read=35.0, write=10.0, pool=8.0)

    async def answer(self, request: ChatRequest) -> ChatResponse:
        if not settings.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is not configured in backend/.env.")
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured in backend/.env.")

        language_name = LANGUAGE_NAMES.get(request.language, "English")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            search_payload = await self._search_web(client, request.message)
            sources = self._extract_sources(search_payload)
            answer = await self._summarize_with_groq(
                client,
                question=request.message,
                language_name=language_name,
                tavily_answer=str(search_payload.get("answer") or ""),
                sources=sources,
            )

        return ChatResponse(
            success=True,
            answer=answer,
            language=request.language,
            sources=sources,
        )

    async def _search_web(self, client: httpx.AsyncClient, query: str) -> dict[str, Any]:
        response = await client.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {settings.tavily_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "search_depth": "basic",
                "topic": "general",
                "country": "india",
                "include_answer": "basic",
                "include_raw_content": False,
                "max_results": 5,
            },
        )
        response.raise_for_status()
        return response.json()

    def _extract_sources(self, search_payload: dict[str, Any]) -> list[ChatSource]:
        sources: list[ChatSource] = []
        for item in search_payload.get("results", [])[:5]:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or url or "Source").strip()
            if not url:
                continue
            sources.append(
                ChatSource(
                    title=title,
                    url=url,
                    content=str(item.get("content") or "")[:700],
                )
            )
        return sources

    async def _summarize_with_groq(
        self,
        client: httpx.AsyncClient,
        *,
        question: str,
        language_name: str,
        tavily_answer: str,
        sources: list[ChatSource],
    ) -> str:
        source_context = "\n\n".join(
            f"[{index}] {source.title}\nURL: {source.url}\nSnippet: {source.content or ''}"
            for index, source in enumerate(sources, start=1)
        )
        system_prompt = (
            "You are Digital Trust Shield Sahayak, a concise public-safety assistant for Indian users. "
            "Use the web search context first, then your general knowledge only to clarify. "
            "If the web context is insufficient, say what is uncertain. "
            "Answer in the requested language. Keep the answer practical and easy to understand. "
            "For legal, medical, financial, or government-scheme questions, avoid pretending certainty; "
            "recommend checking the official source."
        )
        user_prompt = (
            f"Language: {language_name}\n"
            f"User question: {question}\n\n"
            f"Tavily quick answer:\n{tavily_answer}\n\n"
            f"Search sources:\n{source_context}\n\n"
            "Give a helpful answer. End with a short 'Sources checked' line using the source numbers."
        )
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.groq_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 700,
            },
        )
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()
