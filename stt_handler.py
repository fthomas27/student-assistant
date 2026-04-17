"""
Speech-to-Text (STT) handler: Converts audio to text using Whisper API with fallback.
"""

import logging
import os
from typing import Tuple, Optional
import io

log = logging.getLogger(__name__)


class STTHandler:
    """Handles speech-to-text conversion."""

    def __init__(self, api_key: str = None, use_fallback: bool = False):
        """Initialize STT handler."""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = use_fallback or not self.api_key
        self.client = None

        if self.api_key and not use_fallback:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                log.info("Initialized Whisper API client")
            except ImportError:
                log.warning("OpenAI library not installed; using fallback")
                self.use_fallback = True
            except Exception as e:
                log.warning(f"Failed to initialize Whisper: {e}; using fallback")
                self.use_fallback = True

    def transcribe_audio(
        self,
        audio_data: bytes,
        language: str = "en"
    ) -> Tuple[str, float]:
        """
        Transcribe audio to text.

        Args:
            audio_data: Raw audio bytes (WAV or MP3)
            language: Language code (e.g., 'en' for English)

        Returns:
            Tuple of (transcription, confidence_score)
        """
        if self.client and not self.use_fallback:
            return self._transcribe_whisper(audio_data, language)
        else:
            return self._transcribe_fallback(audio_data)

    def _transcribe_whisper(self, audio_data: bytes, language: str) -> Tuple[str, float]:
        """Transcribe using OpenAI Whisper API."""
        try:
            # Create a file-like object from bytes
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.wav"

            # Call Whisper API
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="json"
            )

            text = transcript.text if hasattr(transcript, 'text') else str(transcript.get('text', ''))
            confidence = 0.95  # Whisper doesn't return confidence, assume high
            log.info(f"Transcribed: {text}")
            return text, confidence

        except Exception as e:
            log.error(f"Whisper API error: {e}")
            return "", 0.0

    def _transcribe_fallback(self, audio_data: bytes) -> Tuple[str, float]:
        """Fallback STT using local faster-whisper if available."""
        try:
            from faster_whisper import WhisperModel

            # Use small model for faster processing (can use base, small, medium, large)
            model = WhisperModel("base", device="cpu")

            # Create a file-like object
            audio_file = io.BytesIO(audio_data)

            # Transcribe
            segments, info = model.transcribe(audio_file, language="en")
            text = " ".join([segment.text for segment in segments])

            log.info(f"Fallback transcribed: {text}")
            return text, 0.85  # Lower confidence for local fallback

        except ImportError:
            log.warning("faster-whisper not installed; returning empty transcription")
            return "", 0.0
        except Exception as e:
            log.error(f"Fallback transcription error: {e}")
            return "", 0.0

    def is_speech_detected(self, audio_data: bytes, threshold: float = 0.1) -> bool:
        """
        Detect if there's speech in the audio (simple energy-based detection).

        Args:
            audio_data: Raw audio bytes
            threshold: Energy threshold (0-1)

        Returns:
            True if speech detected
        """
        try:
            import struct
            import numpy as np

            # Convert bytes to int16 array (assuming 16-bit PCM)
            audio_int = struct.unpack(
                f"{len(audio_data) // 2}h",
                audio_data
            )
            audio_array = np.array(audio_int, dtype=np.float32)

            # Normalize to 0-1
            max_val = np.max(np.abs(audio_array))
            if max_val == 0:
                return False

            normalized = audio_array / max_val

            # Calculate RMS energy
            rms = np.sqrt(np.mean(normalized ** 2))

            # Simple threshold check
            return rms > threshold

        except Exception as e:
            log.error(f"Error detecting speech: {e}")
            return True  # Assume speech if we can't determine

    def stream_transcribe(self, audio_stream_generator, language: str = "en"):
        """
        Transcribe audio from a stream (real-time as user speaks).

        Args:
            audio_stream_generator: Generator yielding audio chunks
            language: Language code

        Yields:
            Partial transcriptions as they become available
        """
        try:
            # For real-time, we'd use streaming if available
            # For now, collect and transcribe
            audio_chunks = []
            for chunk in audio_stream_generator:
                audio_chunks.append(chunk)
                # Periodically yield partial results
                if len(audio_chunks) % 5 == 0:  # Every 5 chunks
                    partial_audio = b"".join(audio_chunks)
                    text, conf = self.transcribe_audio(partial_audio, language)
                    if text:
                        yield text

            # Final transcription
            if audio_chunks:
                final_audio = b"".join(audio_chunks)
                text, conf = self.transcribe_audio(final_audio, language)
                yield text

        except Exception as e:
            log.error(f"Stream transcription error: {e}")
