"""Audio transcription service using OpenAI Whisper."""
from typing import Optional
import httpx
from openai import OpenAI
from src.config import settings
from src.utils.logger import log


class TranscriptionService:
    """Handle audio transcription using Whisper API."""

    def __init__(self):
        """Initialize transcription service."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.whisper_model
        self.target_language = settings.transcription_target_language
        log.info("Transcription service initialized")

    async def download_audio(self, url: str) -> Optional[bytes]:
        """Download audio file from URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.content
        except Exception as e:
            log.error(f"Error downloading audio: {e}")
            return None

    async def transcribe_audio(
        self,
        audio_url: str,
        translate_to_french: bool = True,
    ) -> Optional[str]:
        """Transcribe audio from URL to text."""
        try:
            # Download audio file
            audio_data = await self.download_audio(audio_url)
            if not audio_data:
                return None

            # Save temporarily
            temp_file_path = "/tmp/audio_temp.ogg"
            with open(temp_file_path, "wb") as f:
                f.write(audio_data)

            # Transcribe using Whisper
            with open(temp_file_path, "rb") as audio_file:
                if translate_to_french:
                    # Transcribe and translate to French
                    transcript = self.client.audio.translations.create(
                        model=self.model,
                        file=audio_file,
                        response_format="text"
                    )
                else:
                    # Just transcribe in original language
                    transcript = self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        response_format="text"
                    )

            log.info("Audio transcription completed")
            return transcript if isinstance(transcript, str) else transcript.text

        except Exception as e:
            log.error(f"Error transcribing audio: {e}")
            return None


# Global instance
transcription_service = TranscriptionService()
