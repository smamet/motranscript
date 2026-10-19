"""Optional LLM pass for out-of-lexicon Kreol spelling (spelling only, no word changes)."""

import os

import httpx


def llm_normalize_spelling(text: str) -> str | None:
    """
    Call OpenAI-compatible API to fix Kreol spelling per Lortograf rules.
    Returns None if no API key or on failure.
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LORTOGRAF_LLM_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("LORTOGRAF_LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LORTOGRAF_LLM_MODEL", "gpt-4o-mini")

    prompt = (
        "You normalize Mauritian Creole (Kreol Morisien) spelling to official Lortograf orthography.\n"
        "Rules:\n"
        "- Change spelling ONLY. Do not add, remove, or replace words.\n"
        "- Do not translate French or English words.\n"
        "- Keep code-switching exactly as written.\n"
        "- Output only the normalized text, nothing else.\n\n"
        f"Text: {text}"
    )

    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content if content else None
    except Exception:
        return None
