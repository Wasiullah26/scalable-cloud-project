import httpx
from typing import Dict, List, Optional

MYMEMORY_BASE = "https://api.mymemory.translated.net/get"
MAX_QUERY_CHARS = 450
DEFAULT_TARGET_LANGUAGES = ["es", "fr", "de", "it", "pt"]


def _chunk_text(text: str, max_chars: int = MAX_QUERY_CHARS) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    rest = text
    while rest:
        if len(rest) <= max_chars:
            chunks.append(rest.strip())
            break
        piece = rest[:max_chars]
        last_sent = max(piece.rfind(". "), piece.rfind("! "), piece.rfind("? "), piece.rfind(".\n"))
        if last_sent > max_chars // 2:
            split_at = last_sent + 1
        else:
            last_space = piece.rfind(" ")
            split_at = last_space + 1 if last_space > 0 else max_chars
        chunk = rest[:split_at].strip()
        rest = rest[split_at:].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


async def _translate_one_chunk(
    chunk: str,
    source_lang: str,
    target_lang: str,
    client: httpx.AsyncClient,
) -> str:
    if not chunk.strip():
        return chunk
    params = {
        "q": chunk,
        "langpair": f"{source_lang}|{target_lang}",
    }
    resp = await client.get(MYMEMORY_BASE, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("responseData", {}).get("translatedText") or chunk


async def translate_text(
    text: str,
    source_lang: str = "en",
    target_lang: str = "es",
) -> str:
    if not text or not text.strip():
        return text
    chunks = _chunk_text(text)
    if not chunks:
        return text
    async with httpx.AsyncClient(timeout=15.0) as client:
        translated_chunks: List[str] = []
        for chunk in chunks:
            try:
                t = await _translate_one_chunk(chunk, source_lang, target_lang, client)
                translated_chunks.append(t)
            except Exception:
                translated_chunks.append(chunk)
        return " ".join(translated_chunks)


async def translate_to_multiple_languages(
    text: str,
    source_lang: str = "en",
    target_languages: Optional[List[str]] = None,
) -> Dict[str, str]:
    if target_languages is None:
        target_languages = DEFAULT_TARGET_LANGUAGES
    result: Dict[str, str] = {}
    for lang in target_languages:
        if lang == source_lang:
            result[lang] = text
            continue
        try:
            result[lang] = await translate_text(text, source_lang, lang)
        except Exception:
            result[lang] = text
    return result
