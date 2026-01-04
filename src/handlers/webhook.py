"""Twilio webhook handlers for FastAPI."""
from fastapi import APIRouter, Form, Request, HTTPException
from typing import Optional
from src.handlers.message import process_inbound_message
from src.integrations.twilio import twilio_client
from src.utils.logger import log


router = APIRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    MessageSid: str = Form(...),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
):
    """Handle incoming WhatsApp messages from Twilio.

    Args:
        request: FastAPI request object
        From: Sender's WhatsApp number
        Body: Message text
        MessageSid: Twilio message SID
        MediaUrl0: Optional first media URL
        MediaContentType0: Optional first media content type

    Returns:
        Empty response with 200 status
    """
    try:
        # Validate webhook signature if enabled
        if request.app.state.config.verify_webhook_signature:
            url = str(request.url)
            params = dict(await request.form())
            signature = request.headers.get("X-Twilio-Signature", "")

            if not twilio_client.validate_webhook(url, params, signature):
                log.warning(f"Invalid webhook signature from {From}")
                raise HTTPException(status_code=403, detail="Invalid signature")

        log.info(f"Received webhook from {From}")

        # Process message asynchronously (fire and forget)
        # In production, consider using a task queue like Celery or background tasks
        await process_inbound_message(
            from_number=From,
            message_body=Body,
            message_sid=MessageSid,
            media_url=MediaUrl0,
            media_content_type=MediaContentType0,
        )

        # Return empty TwiML response
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error in webhook handler: {e}")
        # Don't expose internal errors to Twilio
        return {"status": "error"}


@router.get("/webhook/whatsapp")
async def whatsapp_webhook_get():
    """Handle GET requests to webhook (for testing)."""
    return {"message": "Lumiera WhatsApp webhook is running"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "lumiera-whatsapp-api"}
