"""
Text-to-Speech (TTS) handler: Converts text to audio using ElevenLabs with fallback.
"""

import logging
import os
import io
from typing import Optional, Tuple

log = logging.getLogger(__name__)


class TTSHandler:
    """Handles text-to-speech conversion."""

    def __init__(
        self,
        api_key: str = None,
        voice_id: str = "alistair",
        use_fallback: bool = False
    ):
        """
        Initialize TTS handler.

        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID to use (e.g., 'alistair', 'callum', 'ollie', 'grace')
            use_fallback: Force use of fallback TTS
        """
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        self.voice_id = voice_id
        self.use_fallback = use_fallback or not self.api_key
        self.client = None

        if self.api_key and not use_fallback:
            try:
                import elevenlabs
                self.client = elevenlabs
                log.info(f"Initialized ElevenLabs TTS with voice: {voice_id}")
            except ImportError:
                log.warning("elevenlabs library not installed; using fallback")
                self.use_fallback = True
            except Exception as e:
                log.warning(f"Failed to initialize ElevenLabs: {e}; using fallback")
                self.use_fallback = True

    def synthesize(
        self,
        text: str,
        output_format: str = "wav"
    ) -> Optional[bytes]:
        """
        Convert text to audio.

        Args:
            text: Text to synthesize
            output_format: Output format ('wav', 'mp3')

        Returns:
            Audio bytes or None if failed
        """
        if not text or len(text.strip()) == 0:
            return None

        if self.client and not self.use_fallback:
            return self._synthesize_elevenlabs(text, output_format)
        else:
            return self._synthesize_fallback(text)

    def _synthesize_elevenlabs(self, text: str, output_format: str) -> Optional[bytes]:
        """Synthesize using ElevenLabs API."""
        try:
            # Import inside method to handle missing library
            from elevenlabs.client import ElevenLabs
            from elevenlabs import stream

            client = ElevenLabs(api_key=self.api_key)

            # Generate audio
            audio = client.generate(
                text=text,
                voice=self.voice_id,
                model="eleven_monolingual_v1"  # or eleven_multilingual_v2
            )

            # Convert to bytes
            audio_bytes = b"".join(audio)
            log.info(f"ElevenLabs synthesized {len(text)} chars")
            return audio_bytes

        except Exception as e:
            log.error(f"ElevenLabs error: {e}")
            return None

    def _synthesize_fallback(self, text: str) -> Optional[bytes]:
        """Fallback TTS using pyttsx3 (offline)."""
        try:
            import pyttsx3
            import io

            # Create TTS engine
            engine = pyttsx3.init()

            # Set voice properties for British accent if available
            voices = engine.getProperty('voices')
            # Try to find a British voice
            for voice in voices:
                if 'english' in voice.name.lower() or 'british' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break

            # Set properties
            engine.setProperty('rate', 150)  # Slower for clarity
            engine.setProperty('volume', 1.0)

            # Save to bytes buffer (requires save method)
            # Note: pyttsx3 on Linux/headless might need special handling
            engine.save_to_file(text, "/tmp/jarvis_tts.wav")
            engine.runAndWait()

            # Read the file
            with open("/tmp/jarvis_tts.wav", "rb") as f:
                audio_bytes = f.read()

            log.info(f"pyttsx3 synthesized {len(text)} chars")
            return audio_bytes

        except Exception as e:
            log.error(f"pyttsx3 fallback error: {e}")
            return None

    def stream_synthesize(self, text: str):
        """
        Stream audio as it's being synthesized (for faster perceived response).

        Args:
            text: Text to synthesize

        Yields:
            Audio chunks
        """
        try:
            if self.client and not self.use_fallback:
                from elevenlabs.client import ElevenLabs

                client = ElevenLabs(api_key=self.api_key)

                # Generate and stream
                audio_stream = client.generate(
                    text=text,
                    voice=self.voice_id,
                    model="eleven_monolingual_v1",
                    stream=True
                )

                for chunk in audio_stream:
                    yield chunk

            else:
                # For fallback, synthesize all at once
                audio_bytes = self._synthesize_fallback(text)
                if audio_bytes:
                    yield audio_bytes

        except Exception as e:
            log.error(f"Stream synthesis error: {e}")

    def get_available_voices(self) -> list:
        """Get list of available voices."""
        if self.client and not self.use_fallback:
            try:
                from elevenlabs.client import ElevenLabs

                client = ElevenLabs(api_key=self.api_key)
                voices = client.voices.get_all()
                return [
                    {
                        "id": voice.voice_id,
                        "name": voice.name,
                        "category": voice.category
                    }
                    for voice in voices
                ]
            except Exception as e:
                log.error(f"Error fetching voices: {e}")
                return []
        else:
            # Return fallback voices
            return [
                {"id": "default", "name": "Default (pyttsx3)", "category": "fallback"}
            ]

    def set_voice(self, voice_id: str):
        """Change the voice to use."""
        self.voice_id = voice_id
        log.info(f"Set voice to: {voice_id}")

    def health_check(self) -> bool:
        """Check if TTS service is available."""
        try:
            # Try to synthesize a test phrase
            audio = self.synthesize("Jarvis ready.", output_format="wav")
            return audio is not None and len(audio) > 0
        except Exception as e:
            log.error(f"TTS health check failed: {e}")
            return False
