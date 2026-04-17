"""
Wake word detector: Listens for "Jarvis" using Porcupine or local fallback.
"""

import logging
import os
from typing import Callable, Optional

log = logging.getLogger(__name__)


class WakeWordDetector:
    """Detects wake word ("Jarvis") from audio stream."""

    def __init__(self, access_key: str = None, wake_word: str = "jarvis"):
        """Initialize wake word detector."""
        self.wake_word = wake_word.lower()
        self.access_key = access_key or os.environ.get("PORCUPINE_ACCESS_KEY")
        self.detector = None
        self.is_listening = False

        if self.access_key:
            self._init_porcupine()
        else:
            log.warning("Porcupine access key not provided; using fallback detection")
            self.use_fallback = True

    def _init_porcupine(self):
        """Initialize Porcupine wake word detection."""
        try:
            import pvporcupine

            # Porcupine built-in keywords: jarvis, ok google, hey google, hey siri, alexa, americano, etc.
            # Check if jarvis is available
            self.detector = pvporcupine.create(
                access_key=self.access_key,
                keywords=["jarvis"]
            )
            log.info(f"Initialized Porcupine detector with {self.detector.frame_length} frame length")
        except ImportError:
            log.warning("pvporcupine not installed; using fallback detection")
            self.use_fallback = True
        except Exception as e:
            log.error(f"Failed to initialize Porcupine: {e}; using fallback")
            self.use_fallback = True

    def process_audio_frame(self, audio_frame: bytes) -> bool:
        """
        Process an audio frame and return True if wake word detected.

        Args:
            audio_frame: Raw audio data (16-bit PCM, 16kHz)

        Returns:
            True if wake word detected, False otherwise
        """
        if self.detector is None:
            return self._fallback_detection(audio_frame)

        try:
            # Convert bytes to int16 array
            import struct
            import numpy as np

            # Assumes 16-bit audio
            audio_int = struct.unpack(
                f"{len(audio_frame) // 2}h",
                audio_frame
            )
            audio_array = np.array(audio_int)

            # Process with Porcupine
            result = self.detector.process(audio_array)

            # result is True if wake word detected (index 0 = jarvis)
            if isinstance(result, int) and result == 0:
                log.info("Wake word 'Jarvis' detected!")
                return True

            return False

        except Exception as e:
            log.error(f"Error processing audio frame: {e}")
            return False

    def _fallback_detection(self, audio_frame: bytes) -> bool:
        """
        Fallback wake word detection using silence/threshold detection.
        This is a simple energy-based detector - just detects speech, not specific words.
        """
        try:
            import struct
            import numpy as np

            # Convert bytes to int16 array
            audio_int = struct.unpack(
                f"{len(audio_frame) // 2}h",
                audio_frame
            )
            audio_array = np.array(audio_int, dtype=np.float32)

            # Calculate RMS energy
            rms = np.sqrt(np.mean(audio_array ** 2))

            # If energy > threshold, consider it speech (poor substitute for actual wake word)
            # This will create many false positives, but works as fallback
            threshold = 500  # Arbitrary threshold
            return rms > threshold

        except Exception as e:
            log.error(f"Fallback detection error: {e}")
            return False

    def start_listening(self, audio_callback: Callable, sample_rate: int = 16000):
        """
        Start listening for wake word in audio stream.

        Args:
            audio_callback: Async callback that receives audio frames
            sample_rate: Sample rate in Hz (default 16000)
        """
        try:
            import sounddevice as sd

            self.is_listening = True
            frame_length = self.detector.frame_length if self.detector else 512

            def audio_stream_handler(indata, frames, time, status):
                if status:
                    log.error(f"Audio stream error: {status}")
                    return

                audio_bytes = indata.tobytes()
                if self.process_audio_frame(audio_bytes):
                    audio_callback()  # Wake word detected!

            # Create audio stream
            stream = sd.Stream(
                samplerate=sample_rate,
                channels=1,
                dtype='float32',
                blocksize=frame_length or 512,
                callback=audio_stream_handler
            )

            log.info("Starting wake word detection listener...")
            with stream:
                while self.is_listening:
                    import time
                    time.sleep(0.1)

        except ImportError:
            log.error("sounddevice not installed; cannot start listening")
        except Exception as e:
            log.error(f"Error starting listener: {e}")

    def stop_listening(self):
        """Stop listening for wake word."""
        self.is_listening = False
        log.info("Stopped wake word detection")

    def cleanup(self):
        """Cleanup resources."""
        if self.detector:
            try:
                self.detector.delete()
            except Exception as e:
                log.error(f"Error cleaning up detector: {e}")
