"""Settings API endpoints.

v1.0.0 - Initial implementation with Telegram test endpoint
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

router = APIRouter()


class TelegramTestRequest(BaseModel):
    """Request model for Telegram test."""
    bot_token: str
    chat_id: str


class TelegramTestResponse(BaseModel):
    """Response model for Telegram test."""
    success: bool
    message: str
    details: Optional[str] = None


class SettingsModel(BaseModel):
    """Settings model."""
    discovery_interval: int = 15
    history_retention_days: int = 90
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_new_mac: bool = True
    alert_mac_move: bool = True
    alert_mac_disappear: bool = True
    alert_disappear_hours: int = 24
    alert_port_threshold: int = 10


# In-memory settings storage (in production, use database)
_settings = SettingsModel()


@router.get("")
async def get_settings() -> SettingsModel:
    """Get all settings."""
    return _settings


@router.put("")
async def update_settings(settings: SettingsModel) -> SettingsModel:
    """Update settings."""
    global _settings
    _settings = settings
    return _settings


@router.post("/telegram/test", response_model=TelegramTestResponse)
async def test_telegram(request: TelegramTestRequest) -> TelegramTestResponse:
    """
    Test Telegram notification by sending a test message.

    This endpoint validates the bot token and chat ID by attempting
    to send a test message to the specified Telegram chat.
    """
    if not request.bot_token:
        return TelegramTestResponse(
            success=False,
            message="Bot token non configurato",
            details="Inserire un token bot valido"
        )

    if not request.chat_id:
        return TelegramTestResponse(
            success=False,
            message="Chat ID non configurato",
            details="Inserire un chat ID valido"
        )

    # Validate token format (basic check)
    if ":" not in request.bot_token:
        return TelegramTestResponse(
            success=False,
            message="Formato token non valido",
            details="Il token deve contenere ':' (formato: 123456789:ABCdefGHI...)"
        )

    # Try to send a test message via Telegram API
    telegram_url = f"https://api.telegram.org/bot{request.bot_token}/sendMessage"

    test_message = (
        "🔔 *Mac-Traker Test*\n\n"
        "✅ Connessione Telegram configurata correttamente!\n\n"
        "Questo messaggio conferma che le notifiche "
        "funzioneranno per gli alert del sistema."
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                telegram_url,
                json={
                    "chat_id": request.chat_id,
                    "text": test_message,
                    "parse_mode": "Markdown"
                }
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    return TelegramTestResponse(
                        success=True,
                        message="Messaggio di test inviato con successo!",
                        details=f"Message ID: {result.get('result', {}).get('message_id', 'N/A')}"
                    )
                else:
                    return TelegramTestResponse(
                        success=False,
                        message="Errore Telegram API",
                        details=result.get("description", "Errore sconosciuto")
                    )
            elif response.status_code == 401:
                return TelegramTestResponse(
                    success=False,
                    message="Token bot non valido",
                    details="Verifica che il token sia corretto"
                )
            elif response.status_code == 400:
                result = response.json()
                error_desc = result.get("description", "Errore nella richiesta")
                if "chat not found" in error_desc.lower():
                    return TelegramTestResponse(
                        success=False,
                        message="Chat ID non valido",
                        details="Verifica che il chat ID sia corretto e che il bot sia stato aggiunto al gruppo/chat"
                    )
                return TelegramTestResponse(
                    success=False,
                    message="Errore nella richiesta",
                    details=error_desc
                )
            else:
                return TelegramTestResponse(
                    success=False,
                    message=f"Errore HTTP {response.status_code}",
                    details=response.text[:200] if response.text else None
                )

    except httpx.TimeoutException:
        return TelegramTestResponse(
            success=False,
            message="Timeout connessione",
            details="Impossibile raggiungere i server Telegram. Verifica la connessione internet."
        )
    except httpx.RequestError as e:
        return TelegramTestResponse(
            success=False,
            message="Errore di connessione",
            details=str(e)
        )
    except Exception as e:
        return TelegramTestResponse(
            success=False,
            message="Errore imprevisto",
            details=str(e)
        )
