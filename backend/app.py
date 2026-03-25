"""Translate API: multi-language text, auth, saved notes (DynamoDB)."""

import logging
import re
import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from translate import translate_to_multiple_languages, DEFAULT_TARGET_LANGUAGES
from store import get as store_get, put as store_put, delete as store_delete, list_by_user as store_list_by_user
from auth_utils import generate_token, get_user_id_from_token
from user_store import create_user, get_user_by_email, get_user, check_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Text to Multiple Languages API",
    description="Translates input text into multiple target languages.",
    version="1.0.0",
)

# CORS — browser calls from another host
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to translate")
    source_lang: str = Field(default="en", description="Source language code (e.g. en)")
    target_languages: Optional[List[str]] = Field(
        default=None,
        description="Target language codes (e.g. ['es','fr']). Default: es, fr, de, it, pt",
    )
    save: bool = Field(default=False, description="If True, store after translate. Default False: translate only; use POST /translations to save.")


class TranslateResponse(BaseModel):
    original_text: str
    source_lang: str
    translations: Dict[str, str]
    id: Optional[str] = None
    created_at: Optional[str] = None


class TranslateUpdateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_lang: str = Field(default="en")
    target_languages: Optional[List[str]] = Field(default=None)


class TranslationSummary(BaseModel):
    id: str
    original_text: str
    source_lang: str
    created_at: str


class SaveNoteRequest(BaseModel):
    original_text: str = Field(default="")
    source_lang: str = Field(default="en")
    translations: Dict[str, str] = Field(default_factory=dict)


class NotePatchRequest(BaseModel):
    """Update note body (and optionally translations) without re-calling the translation API."""

    original_text: str = Field(default="")
    source_lang: str = Field(default="en")
    translations: Optional[Dict[str, str]] = None


async def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.replace("Bearer ", "").strip()
    try:
        uid = get_user_id_from_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not get_user(uid):
        raise HTTPException(status_code=401, detail="User not found")
    return uid


def _assert_note_owner(record: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
    if not record or record.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Translation not found")
    return record


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PASSWORD_SPECIAL_RE = re.compile(r'[!@#$%^&*()_+\-=[\]{};\':"|,.<>/?\\]')


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    name: str = Field(default="", max_length=100)
    password: str = Field(..., min_length=6)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        s = v.strip().lower()
        if not _EMAIL_RE.match(s):
            raise ValueError("Please enter a valid email address")
        return s

    @field_validator("password")
    @classmethod
    def password_rules(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one capital letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number")
        if not _PASSWORD_SPECIAL_RE.search(v):
            raise ValueError("Password must contain at least one special character")
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


@app.post("/auth/signup")
async def auth_signup(req: SignupRequest):
    try:
        user = create_user(req.email, req.name, req.password)
        return {
            "message": "User created successfully",
            "user_id": user["user_id"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login")
async def auth_login(req: LoginRequest):
    user = get_user_by_email(req.email.strip().lower())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not check_password(user, req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = generate_token(user["user_id"])
    return {
        "token": token,
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
        },
    }


@app.get("/auth/verify")
async def auth_verify(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")
    token = authorization.replace("Bearer ", "").strip()
    try:
        user_id = get_user_id_from_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
    }


@app.get("/")
async def root():
    return {"service": "text-to-languages-api", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "text-to-languages-api"}


@app.get("/languages")
async def supported_languages():
    return {
        "default_targets": DEFAULT_TARGET_LANGUAGES,
        "source_default": "en",
    }


def _make_record(
    user_id: str,
    original_text: str,
    source_lang: str,
    translations: Dict[str, str],
    record_id: Optional[str] = None,
) -> Dict[str, Any]:
    from datetime import datetime
    record_id = record_id or str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": record_id,
        "user_id": user_id,
        "original_text": original_text,
        "source_lang": source_lang,
        "translations": translations,
        "created_at": now,
        "updated_at": now,
    }


@app.post("/translate", response_model=TranslateResponse)
async def translate(
    user_id: Annotated[str, Depends(get_current_user_id)],
    req: TranslateRequest = ...,
):
    try:
        translations = await translate_to_multiple_languages(
            text=req.text,
            source_lang=req.source_lang,
            target_languages=req.target_languages,
        )
        if req.save:
            record = _make_record(user_id, req.text, req.source_lang, translations)
            rid = record["id"]
            store_put(record)
            return TranslateResponse(
                id=rid,
                original_text=record["original_text"],
                source_lang=record["source_lang"],
                translations=record["translations"],
                created_at=record["created_at"],
            )
        return TranslateResponse(
            original_text=req.text,
            source_lang=req.source_lang,
            translations=translations,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Translation failed: {str(e)}")


@app.get("/translate/{id}", response_model=TranslateResponse)
async def get_translation(
    user_id: Annotated[str, Depends(get_current_user_id)],
    id: str = Path(..., description="Translation record ID"),
):
    r = store_get(id)
    _assert_note_owner(r, user_id)
    return TranslateResponse(
        id=r["id"],
        original_text=r["original_text"],
        source_lang=r["source_lang"],
        translations=r["translations"],
        created_at=r["created_at"],
    )


@app.patch("/translate/{id}", response_model=TranslateResponse)
async def patch_note(
    user_id: Annotated[str, Depends(get_current_user_id)],
    id: str = Path(..., description="Translation record ID"),
    req: NotePatchRequest = ...,
):
    existing = store_get(id)
    _assert_note_owner(existing, user_id)
    from datetime import datetime

    now = datetime.utcnow().isoformat() + "Z"
    if req.translations is not None:
        translations = req.translations
    else:
        translations = dict(existing.get("translations") or {})
    record = {
        "id": id,
        "user_id": user_id,
        "original_text": req.original_text,
        "source_lang": req.source_lang,
        "translations": translations,
        "created_at": existing["created_at"],
        "updated_at": now,
    }
    store_put(record)
    return TranslateResponse(
        id=record["id"],
        original_text=record["original_text"],
        source_lang=record["source_lang"],
        translations=record["translations"],
        created_at=record["created_at"],
    )


@app.put("/translate/{id}", response_model=TranslateResponse)
async def update_translation(
    user_id: Annotated[str, Depends(get_current_user_id)],
    id: str = Path(..., description="Translation record ID"),
    req: TranslateUpdateRequest = ...,
):
    existing = store_get(id)
    _assert_note_owner(existing, user_id)
    try:
        translations = await translate_to_multiple_languages(
            text=req.text,
            source_lang=req.source_lang,
            target_languages=req.target_languages,
        )
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        record = {
            "id": id,
            "user_id": user_id,
            "original_text": req.text,
            "source_lang": req.source_lang,
            "translations": translations,
            "created_at": existing["created_at"],
            "updated_at": now,
        }
        store_put(record)
        r = record
        return TranslateResponse(
            id=r["id"],
            original_text=r["original_text"],
            source_lang=r["source_lang"],
            translations=r["translations"],
            created_at=r["created_at"],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Translation failed: {str(e)}")


@app.delete("/translate/{id}")
async def delete_translation(
    user_id: Annotated[str, Depends(get_current_user_id)],
    id: str = Path(..., description="Translation record ID"),
):
    existing = store_get(id)
    _assert_note_owner(existing, user_id)
    store_delete(id)
    return {"success": True}


@app.post("/translations", response_model=TranslateResponse)
async def save_note(
    user_id: Annotated[str, Depends(get_current_user_id)],
    req: SaveNoteRequest = ...,
):
    record = _make_record(user_id, req.original_text, req.source_lang, req.translations)
    rid = record["id"]
    store_put(record)
    return TranslateResponse(
        id=rid,
        original_text=record["original_text"],
        source_lang=record["source_lang"],
        translations=record["translations"],
        created_at=record["created_at"],
    )


@app.get("/translations", response_model=List[TranslationSummary])
async def list_translations(user_id: Annotated[str, Depends(get_current_user_id)]):
    items = store_list_by_user(user_id)
    out = [
        TranslationSummary(
            id=r["id"],
            original_text=(r["original_text"][:80] + "…") if len(r["original_text"]) > 80 else r["original_text"],
            source_lang=r["source_lang"],
            created_at=r["created_at"],
        )
        for r in items
    ]
    out.sort(key=lambda x: x.created_at, reverse=True)
    return out


from mangum import Mangum

# API Gateway may prefix paths with /default — strip for routing
_mangum = Mangum(app, lifespan="off", api_gateway_base_path="/default")


def handler(event, context):
    try:
        return _mangum(event, context)
    except Exception as e:
        logger.exception("Lambda handler error: %s", e)
        raise
