"""
Worker module for processing audio transcriptions.
"""
import os
import sys
import json
import time
import argparse
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

# Add parent directory to path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.utils.config import load_config
from src.utils.logging import setup_logging
from src.storage.database import Database
from src.storage.file_manager import FileManager


class TranscriptionError(Exception):
    """Exception raised when a transcription operation fails."""
    pass


class TranscriptionWorker:
    """
    Worker for processing audio transcriptions.
    
    This class manages the transcription of audio files using Whisper.
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize the transcription worker.
        
        Args:
            config_path (str): Path to the configuration file.
        """
        self.config = load_config(config_path)
        self.logger = setup_logging(
            self.config["logging"]["level"],
            self.config["logging"]["log_path"],
            "transcription"
        )
        
        # Initialize components
        self.db = Database(self.config["database"])
        self.file_manager = FileManager(
            self.config["network"]["nas_mount"],
            self.config["downloader"]["download_path"],
            self.config["transcription"]["output_path"]
        )
        
        # Check for GPU support
        self.has_gpu = self._check_gpu()
        if self.has_gpu:
            self.logger.info("GPU support detected")
        else:
            self.logger.warning("No GPU support detected, transcription will be slower")
        
        # Load Whisper model
        self.model = self._load_whisper_model(self.config["transcription"]["model"])
        
        # Initialize state
        self.running = False
        self.current_task = None
    
    def _check_gpu(self) -> bool:
        """
        Check if GPU support is available.
        
        Returns:
            bool: True if GPU is available, False otherwise.
        """
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            self.logger.warning("PyTorch not installed, cannot check GPU availability")
            return False
        except Exception as e:
            self.logger.error(f"Error checking GPU availability: {e}")
            return False
    
    def _load_whisper_model(self, model_name: str) -> Any:
        """
        Load the Whisper model.
        
        Args:
            model_name (str): Name of the model to load.
            
        Returns:
            object: Loaded model.
        """
        try:
            import whisper
            self.logger.info(f"Loading Whisper model: {model_name}")
            return whisper.load_model(model_name)
        except ImportError:
            self.logger.error("Whisper not installed, please install with: pip install openai-whisper")
            raise TranscriptionError("Whisper not installed")
        except Exception as e:
            self.logger.error(f"Error loading Whisper model: {e}")
            raise TranscriptionError(f"Error loading Whisper model: {e}")
    
    def process_next_task(self) -> bool:
        """
        Process the next available transcription task.
        
        Returns:
            bool: True if a task was processed, False otherwise.
        """
        # Get the next show ready for transcription
        shows = self.db.get_shows_by_status("ready_for_transcription", 1)
        if not shows:
            return False
        
        show = shows[0]
        self.logger.info(f"Processing show: {show['title']} (ID: {show['id']})")
        
        # Update show status
        self.db.update_show(show["id"], {"status": "transcribing"})
        self.current_task = show["id"]
        
        try:
            # Check if audio file exists
            audio_path = show["download_path"]
            if not os.path.exists(audio_path):
                self.logger.error(f"Audio file not found: {audio_path}")
                self.db.update_show(show["id"], {"status": "error"})
                return False
            
            # Create output directory
            output_dir = self.file_manager.get_processed_path(show["title"])
            os.makedirs(output_dir, exist_ok=True)
            
            # Transcribe the audio
            self.logger.info(f"Transcribing audio: {audio_path}")
            result = self.transcribe_audio(
                audio_path, 
                output_dir,
                self.config["transcription"]
            )
            
            # Update show status and add transcription to database
            self.db.update_show(show["id"], {"status": "transcribed"})
            
            # Add each transcription format to database
            for fmt, path in result["output_files"].items():
                transcription_data = {
                    "show_id": show["id"],
                    "path": path,
                    "format": fmt,
                    "word_count": result["word_count"],
                    "speakers": result.get("speakers", 1)
                }
                self.db.add_transcription(transcription_data)
            
            self.logger.info(f"Transcription completed for show: {show['title']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {e}", exc_info=True)
            self.db.update_show(show["id"], {"status": "error"})
            return False
        finally:
            self.current_task = None
    
    def transcribe_audio(self, audio_path: str, output_dir: str, 
                         options: Dict) -> Dict:
        """
        Transcribe an audio file.
        
        Args:
            audio_path (str): Path to the audio file.
            output_dir (str): Directory to save transcription files.
            options (dict): Transcription options.
            
        Returns:
            dict: Transcription results.
        """
        try:
            # Transcribe with Whisper
            language = options.get("language")
            fp16 = self.has_gpu
            
            self.logger.info(f"Running Whisper transcription with model: {self.config['transcription']['model']}")
            
            # Run transcription
            result = self.model.transcribe(
                audio_path,
                language=language,
                fp16=fp16,
                verbose=True
            )
            
            # Extract filename without extension
            base_filename = os.path.splitext(os.path.basename(audio_path))[0]
            
            # Process transcription result
            transcript = result["text"]
            segments = result["segments"]
            
            # Count words
            word_count = len(transcript.split())
            
            # Save transcription in requested formats
            output_files = {}
            formats = options.get("formats", ["json", "txt"])
            
            if "txt" in formats:
                txt_path = os.path.join(output_dir, f"{base_filename}.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(transcript)
                output_files["txt"] = txt_path
            
            if "json" in formats:
                json_path = os.path.join(output_dir, f"{base_filename}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                output_files["json"] = json_path
            
            if "srt" in formats:
                srt_path = os.path.join(output_dir, f"{base_filename}.srt")
                self._write_srt(segments, srt_path)
                output_files["srt"] = srt_path
            
            # Run speaker diarization if requested
            speakers = 1
            if options.get("diarize", False):
                speakers = self._run_diarization(audio_path, output_dir, base_filename)
            
            return {
                "transcript": transcript,
                "word_count": word_count,
                "speakers": speakers,
                "output_files": output_files
            }
            
        except Exception as e:
            self.logger.error(f"Error in transcription: {e}", exc_info=True)
            raise TranscriptionError(f"Error in transcription: {e}")
    
    def _write_srt(self, segments: List[Dict], output_path: str) -> None:
        """
        Write segments to an SRT subtitle file.
        
        Args:
            segments (list): List of transcript segments.
            output_path (str): Path to save the SRT file.
        """
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for i, segment in enumerate(segments, start=1):
                    # Format start and end times
                    start_time = self._format_timestamp(segment["start"])
                    end_time = self._format_timestamp(segment["end"])
                    
                    # Write SRT entry
                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{segment['text'].strip()}\n\n")
        except Exception as e:
            self.logger.error(f"Error writing SRT file: {e}")
            raise TranscriptionError(f"Error writing SRT file: {e}")
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Format a timestamp in seconds to SRT format (HH:MM:SS,mmm).
        
        Args:
            seconds (float): Time in seconds.
            
        Returns:
            str: Formatted timestamp.
        """
        hours = int(seconds // 3600)
        seconds %= 3600
        minutes = int(seconds // 60)
        seconds %= 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
    
    def _run_diarization(self, audio_path: str, output_dir: str, base_filename: str) -> int:
        """
        Run speaker diarization on an audio file.
        
        Args:
            audio_path (str): Path to the audio file.
            output_dir (str): Directory to save diarization results.
            base_filename (str): Base filename for output files.
            
        Returns:
            int: Number of speakers detected.
        """
        try:
            self.logger.info("Running speaker diarization")
            
            try:
                from pyannote.audio import Pipeline
            except ImportError:
                self.logger.warning("pyannote.audio not installed, skipping diarization")
                return 1
            
            # Run diarization
            pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")
            diarization = pipeline(audio_path)
            
            # Count speakers
            speakers = len(set(label for _, _, label in diarization.itertracks()))
            
            # Save diarization to RTTM file
            rttm_path = os.path.join(output_dir, f"{base_filename}.rttm")
            with open(rttm_path, "w") as f:
                diarization.write_rttm(f)
            
            self.logger.info(f"Diarization completed with {speakers} speakers")
            return speakers
            
        except Exception as e:
            self.logger.error(f"Error in diarization: {e}", exc_info=True)
            # Don't fail the whole transcription process if diarization fails
            return 1
    
    def run(self) -> None:
        """
        Run the worker in a continuous loop.
        """
        self.running = True
        self.logger.info("Starting transcription worker")
        
        while self.running:
            try:
                # Process next task if available
                task_processed = self.process_next_task()
                
                if not task_processed:
                    # Sleep before checking again
                    self.logger.debug("No tasks to process, sleeping...")
                    time.sleep(10)
            except Exception as e:
                self.logger.error(f"Error in worker loop: {e}", exc_info=True)
                time.sleep(30)  # Sleep longer on error
    
    def stop(self) -> None:
        """
        Stop the worker.
        """
        self.logger.info("Stopping transcription worker")
        self.running = False


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BBC Radio Transcription Worker")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    worker = TranscriptionWorker(args.config)
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("Shutting down worker...")
        worker.stop()
        sys.exit(0)
    
    # Register signal handlers
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the worker
    worker.run()
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) Initialize state
        self.running = False
        self.current_task = None
    
    def _check_gpu(self) -> bool:
        """
        Check if GPU support is available.
        
        Returns:
            bool: True if GPU is available, False otherwise.
        """
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            self.logger.warning("PyTorch not installed, cannot check GPU availability")
            return False
        except Exception as e:
            self.logger.error(f"Error checking GPU availability: {e}")
            return False
    
    def _load_whisper_model(self, model_name: str) -> Any:
        """
        Load the Whisper model.
        
        Args:
            model_name (str): Name of the model to load.
            
        Returns:
            object: Loaded model.
        """
        try:
            import whisper
            self.logger.info(f"Loading Whisper model: {model_name}")
            return whisper.load_model(model_name)
        except ImportError:
            self.logger.error("Whisper not installed, please install with: pip install openai-whisper")
            raise TranscriptionError("Whisper not installed")
        except Exception as e:
            self.logger.error(f"Error loading Whisper model: {e}")
            raise TranscriptionError(f"Error loading Whisper model: {e}")
    
    def process_next_task(self) -> bool:
        """
        Process the next available transcription task.
        
        Returns:
            bool: True if a task was processed, False otherwise.
        """
        # Get the next show ready for transcription
        shows = self.db.get_shows_by_status("ready_for_transcription", 1)
        if not shows:
            return False
        
        show = shows[0]
        self.logger.info(f"Processing show: {show['title']} (ID: {show['id']})")
        
        # Update show status
        self.db.update_show(show["id"], {"status": "transcribing"})
        self.current_task = show["id"]
        
        try:
            # Check if audio file exists
            audio_path = show["download_path"]
            if not os.path.exists(audio_path):
                self.logger.error(f"Audio file not found: {audio_path}")
                self.db.update_show(show["id"], {"status": "error"})
                return False
            
            # Create output directory
            output_dir = self.file_manager.get_processed_path(show["title"])
            os.makedirs(output_dir, exist_ok=True)
            
            # Transcribe the audio
            self.logger.info(f"Transcribing audio: {audio_path}")
            result = self.transcribe_audio(
                audio_path, 
                output_dir,
                self.config["transcription"]
            )
            
            # Update show status and add transcription to database
            self.db.update_show(show["id"], {"status": "transcribed"})
            
            # Add each transcription format to database
            for fmt, path in result["output_files"].items():
                transcription_data = {
                    "show_id": show["id"],
                    "path": path,
                    "format": fmt,
                    "word_count": result["word_count"],
                    "speakers": result.get("speakers", 1)
                }
                self.db.add_transcription(transcription_data)
            
            self.logger.info(f"Transcription completed for show: {show['title']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {e}", exc_info=True)
            self.db.update_show(show["id"], {"status": "error"})
            return False
        finally:
            self.current_task = None
    
    def transcribe_audio(self, audio_path: str, output_dir: str, 
                         options: Dict) -> Dict:
        """
        Transcribe an audio file.
        
        Args:
            audio_path (str): Path to the audio file.
            output_dir (str): Directory to save transcription files.
            options (dict): Transcription options.
            
        Returns:
            dict: Transcription results.
        """
        try:
            # Transcribe with Whisper
            language = options.get("language")
            fp16 = self.has_gpu
            
            self.logger.info(f"Running Whisper transcription with model: {self.config['transcription']['model']}")
            
            # Run transcription
            result = self.model.transcribe(
                audio_path,
                language=language,
                fp16=fp16,
                verbose=True
            )
            
            # Extract filename without extension
            base_filename = os.path.splitext(os.path.basename(audio_path))[0]
            
            # Process transcription result
            transcript = result["text"]
            segments = result["segments"]
            
            # Count words
            word_count = len(transcript.split())
            
            # Save transcription in requested formats
            output_files = {}
            formats = options.get("formats", ["json", "txt"])
            
            if "txt" in formats:
                txt_path = os.path.join(output_dir, f"{base_filename}.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(transcript)
                output_files["txt"] = txt_path
            
            if "json" in formats:
                json_path = os.path.join(output_dir, f"{base_filename}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                output_files["json"] = json_path
            
            if "srt" in formats:
                srt_path = os.path.join(output_dir, f"{base_filename}.srt")
                self._write_srt(segments, srt_path)
                output_files["srt"] = srt_path
            
            # Run speaker diarization if requested
            speakers = 1
            if options.get("diarize", False):
                speakers = self._run_diarization(audio_path, output_dir, base_filename)
            
            return {
                "transcript": transcript,
                "word_count": word_count,
                "speakers": speakers,
                "output_files": output_files
            }
            
        except Exception as e:
            self.logger.error(f"Error in transcription: {e}", exc_info=True)
            raise TranscriptionError(f"Error in transcription: {e}")
    
    def _write_srt(self, segments: List[Dict], output_path: str) -> None:
        """
        Write segments to an SRT subtitle file.
        
        Args:
            segments (list): List of transcript segments.
            output_path (str): Path to save the SRT file.
        """
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for i, segment in enumerate(segments, start=1):
                    # Format start and end times
                    start_time = self._format_timestamp(segment["start"])
                    end_time = self._format_timestamp(segment["end"])
                    
                    # Write SRT entry
                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{segment['text'].strip()}\n\n")
        except Exception as e:
            self.logger.error(f"Error writing SRT file: {e}")
            raise TranscriptionError(f"Error writing SRT file: {e}")
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Format a timestamp in seconds to SRT format (HH:MM:SS,mmm).
        
        Args:
            seconds (float): Time in seconds.
            
        Returns:
            str: Formatted timestamp.
        """
        hours = int(seconds // 3600)
        seconds %= 3600
        minutes = int(seconds // 60)
        seconds %= 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
