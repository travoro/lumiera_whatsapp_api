"""Twilio webhook handlers for FastAPI."""
from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import Response
from typing import Optional
from src.handlers.message import process_inbound_message
from src.integrations.twilio import twilio_client
from src.utils.logger import log
from slowapi import Limiter
from slowapi.util import get_remote_address


router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/webhook/whatsapp")
@limiter.limit("10/minute")  # Rate limit from config
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    MessageSid: str = Form(...),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    ButtonPayload: Optional[str] = Form(None),  # Interactive list selection ID
    ButtonText: Optional[str] = Form(None),     # Interactive list selection text
):
    """Handle incoming WhatsApp messages from Twilio.

    Rate limited to 10 requests/minute to prevent DoS attacks and API cost exhaustion.

    Args:
        request: FastAPI request object
        From: Sender's WhatsApp number
        Body: Message text
        MessageSid: Twilio message SID
        MediaUrl0: Optional first media URL
        MediaContentType0: Optional first media content type
        ButtonPayload: Optional interactive list selection ID (e.g., "view_sites")
        ButtonText: Optional interactive list selection display text

    Returns:
        Empty response with 200 status
    """
    try:
        # Log all form parameters for debugging
        form_data = dict(await request.form())
        log.info(f"📥 Webhook received all params: {list(form_data.keys())}")

        # Validate webhook signature (ALWAYS enforced for security)
        url = str(request.url)
        params = form_data
        signature = request.headers.get("X-Twilio-Signature", "")

        if not twilio_client.validate_webhook(url, params, signature):
            log.warning(f"🚫 Invalid webhook signature from {From}")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Check if this is an interactive list response
        is_interactive_response = ButtonPayload is not None

        if is_interactive_response:
            log.info(f"Received interactive list selection from {From}: {ButtonPayload}")
        else:
            log.info(f"Received webhook from {From}")

        # Process message asynchronously (fire and forget)
        # In production, consider using a task queue like Celery or background tasks
        await process_inbound_message(
            from_number=From,
            message_body=Body,
            message_sid=MessageSid,
            media_url=MediaUrl0,
            media_content_type=MediaContentType0,
            button_payload=ButtonPayload,
            button_text=ButtonText,
        )

        # Return empty response (Twilio expects empty or TwiML, not JSON)
        return Response(content="", status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error in webhook handler: {e}")
        # Don't expose internal errors to Twilio
        return Response(content="", status_code=200)


@router.get("/webhook/whatsapp")
async def whatsapp_webhook_get():
    """Handle GET requests to webhook (for testing)."""
    return {"message": "Lumiera WhatsApp webhook is running"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "lumiera-whatsapp-api"}
