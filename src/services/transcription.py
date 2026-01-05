"""Audio transcription service using OpenAI Whisper."""
from typing import Optional, Tuple
import httpx
import os
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
        """Download audio file from URL.

        Args:
            url: URL of audio file (Twilio or other source)

        Returns:
            Audio file bytes or None if download fails
        """
        try:
            # Check if this is a Twilio URL and add authentication
            auth = None
            if "api.twilio.com" in url:
                # Twilio media URLs require basic auth
                from src.config import settings
                auth = (settings.twilio_account_sid, settings.twilio_auth_token)
                log.info("Downloading audio from Twilio with authentication")

            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, auth=auth, timeout=30.0)
                response.raise_for_status()
                log.info(f"Downloaded audio file: {len(response.content)} bytes")
                return response.content
        except Exception as e:
            log.error(f"Error downloading audio: {e}")
            return None

    async def upload_audio_to_storage(
        self,
        audio_data: bytes,
        user_id: str,
        message_sid: str,
        content_type: str = "audio/ogg"
    ) -> Optional[str]:
        """Upload audio file to Supabase storage.

        Args:
            audio_data: Audio file bytes
            user_id: User ID for organizing storage
            message_sid: Message SID for unique filename
            content_type: MIME type of audio file

        Returns:
            Public URL of stored audio or None if upload fails
        """
        try:
            from src.integrations.supabase import supabase_client

            # Generate unique filename
            file_extension = "ogg" if "ogg" in content_type else "mp3"
            file_name = f"audio/{user_id}/{message_sid}.{file_extension}"

            # Upload to Supabase storage
            public_url = await supabase_client.upload_media(
                file_data=audio_data,
                file_name=file_name,
                content_type=content_type
            )

            if public_url:
                log.info(f"Audio uploaded to storage: {file_name}")

            return public_url

        except Exception as e:
            log.error(f"Error uploading audio to storage: {e}")
            return None

    async def transcribe_audio(
        self,
        audio_url: str,
        target_language: Optional[str] = None,
    ) -> Optional[str]:
        """Transcribe audio from URL to text in original language.

        Args:
            audio_url: URL of audio file to transcribe
            target_language: Target language code (used for logging only)

        Returns:
            Transcribed text in original language or None if transcription fails

        Note:
            This transcribes in the ORIGINAL language. Translation to French
            happens later in the pipeline (Stage 5).
        """
        try:
            # Download audio file
            audio_data = await self.download_audio(audio_url)
            if not audio_data:
                return None

            # Save temporarily
            temp_file_path = "/tmp/audio_temp.ogg"
            with open(temp_file_path, "wb") as f:
                f.write(audio_data)

            # Transcribe using Whisper (original language only)
            with open(temp_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="text"
                    # language parameter removed - let Whisper auto-detect the language
                )

            # Clean up temp file
            try:
                os.remove(temp_file_path)
            except:
                pass

            transcribed_text = transcript if isinstance(transcript, str) else transcript.text
            log.info(f"Audio transcription completed: {transcribed_text[:50]}...")
            return transcribed_text

        except Exception as e:
            log.error(f"Error transcribing audio: {e}")
            return None

    async def transcribe_and_store_audio(
        self,
        audio_url: str,
        user_id: str,
        message_sid: str,
        target_language: Optional[str] = None,
        content_type: str = "audio/ogg"
    ) -> Tuple[Optional[str], Optional[str]]:
        """Download, store, and transcribe audio file.

        Args:
            audio_url: URL of audio file (e.g., from Twilio)
            user_id: User ID for storage organization
            message_sid: Message SID for unique filename
            target_language: Language code for transcription hint
            content_type: MIME type of audio

        Returns:
            Tuple of (transcribed_text, storage_url)
            Either can be None if that step fails
        """
        try:
            # Download audio
            audio_data = await self.download_audio(audio_url)
            if not audio_data:
                return None, None

            # Upload to permanent storage
            storage_url = await self.upload_audio_to_storage(
                audio_data,
                user_id,
                message_sid,
                content_type
            )

            # Transcribe (we already have the audio data)
            temp_file_path = "/tmp/audio_temp.ogg"
            with open(temp_file_path, "wb") as f:
                f.write(audio_data)

            with open(temp_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="text"
                    # language parameter removed - let Whisper auto-detect the language
                )

            # Clean up
            try:
                os.remove(temp_file_path)
            except:
                pass

            transcribed_text = transcript if isinstance(transcript, str) else transcript.text
            log.info(f"✅ Audio processed: transcribed and stored")

            return transcribed_text, storage_url

        except Exception as e:
            log.error(f"Error in transcribe_and_store_audio: {e}")
            return None, None


# Global instance
transcription_service = TranscriptionService()
