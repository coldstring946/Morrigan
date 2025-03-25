"""
Main entry point for the BBC Radio Processor.
"""
import argparse
import logging
import os
import sys
import time
from typing import Dict, List, Optional

# Add parent directory to path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config import load_config
from src.utils.logging import setup_logging
from src.downloader.get_iplayer import GetIPlayer, GetIPlayerError
from src.storage.database import Database
from src.storage.file_manager import FileManager


class BBCRadioProcessor:
    """
    Main class for the BBC Radio Processor application.
    
    This class coordinates the downloading, storage, and processing of BBC radio content.
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize the BBC Radio Processor.
        
        Args:
            config_path (str): Path to the configuration file.
        """
        self.config = load_config(config_path)
        self.logger = setup_logging(
            self.config["logging"]["level"],
            self.config["logging"]["log_path"],
            "downloader"
        )
        
        # Initialize components
        self.db = Database(self.config["database"])
        self.file_manager = FileManager(
            self.config["network"]["nas_mount"],
            self.config["downloader"]["download_path"],
            self.config["transcription"]["output_path"]
        )
        self.downloader = GetIPlayer(self.config["downloader"]["get_iplayer_options"])
    
    def refresh_shows(self) -> int:
        """
        Refresh the list of available shows.
        
        Returns:
            int: Number of new shows found.
        """
        self.logger.info("Refreshing show listings")
        
        try:
            # Refresh get_iplayer cache
            self.downloader.refresh_cache()
            
            # Get channels from config or list all
            channels = self.config["downloader"].get("channels", [])
            if not channels:
                channels = self.downloader.list_channels()
                
            # Get categories from config or list all
            categories = self.config["downloader"].get("categories", [])
            
            # Track new shows
            new_shows = 0
            
            # Process each channel
            for channel in channels:
                self.logger.info(f"Processing channel: {channel}")
                
                # Search for shows on this channel
                options = {"type": "radio", "channel": channel}
                if categories:
                    for category in categories:
                        options["category"] = category
                        shows = self.downloader.search("", options)
                        new_shows += self._process_shows(shows)
                else:
                    shows = self.downloader.search("", options)
                    new_shows += self._process_shows(shows)
            
            self.logger.info(f"Found {new_shows} new shows")
            return new_shows
            
        except GetIPlayerError as e:
            self.logger.error(f"Error refreshing shows: {e}")
            return 0
    
    def _process_shows(self, shows: List[Dict]) -> int:
        """
        Process a list of shows, adding new ones to the database.
        
        Args:
            shows (list): List of show dictionaries from get_iplayer.
            
        Returns:
            int: Number of new shows added.
        """
        new_shows = 0
        
        for show in shows:
            # Extract key information
            pid = show.get("pid")
            if not pid:
                continue
                
            # Check if show exists in database
            existing_show = self.db.get_show_by_pid(pid)
            if existing_show:
                continue
                
            # Add new show to database
            show_data = {
                "pid": pid,
                "title": show.get("name", "Unknown"),
                "description": show.get("desc", ""),
                "episode": show.get("episode", ""),
                "broadcast_date": show.get("firstbcast", ""),
                "duration": int(show.get("duration", 0)),
                "status": "pending",
                "metadata": {
                    "channel": show.get("channel", ""),
                    "categories": show.get("categories", "").split(","),
                    "thumbnail": show.get("thumbnail", ""),
                    "guidance": show.get("guidance", ""),
                    "web_url": show.get("web", "")
                }
            }
            
            self.db.add_show(show_data)
            new_shows += 1
            
        return new_shows
    
    def download_show(self, show_id: int) -> Dict:
        """
        Download a specific show by ID.
        
        Args:
            show_id (int): The database ID of the show.
            
        Returns:
            dict: A dictionary containing download results.
        """
        self.logger.info(f"Downloading show with ID: {show_id}")
        
        # Get show from database
        show = self.db.get_show(show_id)
        if not show:
            self.logger.error(f"Show with ID {show_id} not found")
            return {"success": False, "error": "Show not found"}
        
        # Update show status
        self.db.update_show(show_id, {"status": "downloading"})
        
        try:
            # Create download directory
            # Strip any non-filesystem-safe characters from title
            safe_title = "".join(c for c in show["title"] if c.isalnum() or c in " _-").strip()
            download_dir = os.path.join(self.config["downloader"]["download_path"], safe_title)
            os.makedirs(download_dir, exist_ok=True)
            
            # Download the show
            options = self.config["downloader"]["get_iplayer_options"].copy()
            options["output"] = download_dir
            result = self.downloader.download(show["pid"], options)
            
            if result["success"]:
                # Update show with download path
                if result["output_path"]:
                    self.db.update_show(show_id, {
                        "status": "downloaded",
                        "download_path": result["output_path"]
                    })
                else:
                    # If output path wasn't detected, use a glob pattern
                    self.db.update_show(show_id, {
                        "status": "downloaded",
                        "download_path": os.path.join(download_dir, f"*_{show['pid']}.*")
                    })
                
                self.logger.info(f"Successfully downloaded show: {show['title']}")
                return {"success": True, "show_id": show_id, "path": result["output_path"]}
            else:
                # Update show status to error
                self.db.update_show(show_id, {"status": "error"})
                self.logger.error(f"Failed to download show: {show['title']}")
                return {"success": False, "error": "Download failed", "details": result}
                
        except GetIPlayerError as e:
            # Update show status to error
            self.db.update_show(show_id, {"status": "error"})
            self.logger.error(f"Error downloading show: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Update show status to error
            self.db.update_show(show_id, {"status": "error"})
            self.logger.error(f"Unexpected error downloading show: {e}")
            return {"success": False, "error": str(e)}
    
    def process_pending_downloads(self, limit: int = 0) -> Dict:
        """
        Process all pending downloads.
        
        Args:
            limit (int): Maximum number of shows to download (0 for unlimited).
            
        Returns:
            dict: A dictionary containing process results.
        """
        self.logger.info("Processing pending downloads")
        
        # Get pending shows from database
        pending_shows = self.db.get_shows_by_status("pending", limit)
        
        if not pending_shows:
            self.logger.info("No pending downloads")
            return {"success": True, "downloaded": 0, "errors": 0}
        
        self.logger.info(f"Found {len(pending_shows)} pending downloads")
        
        # Track results
        results = {
            "success": True,
            "downloaded": 0,
            "errors": 0,
            "shows": []
        }
        
        # Process each show
        for show in pending_shows:
            result = self.download_show(show["id"])
            results["shows"].append({
                "id": show["id"],
                "title": show["title"],
                "success": result["success"]
            })
            
            if result["success"]:
                results["downloaded"] += 1
            else:
                results["errors"] += 1
            
            # Sleep briefly to avoid overloading
            time.sleep(1)
        
        self.logger.info(f"Processed {len(pending_shows)} shows, {results['downloaded']} successful, {results['errors']} errors")
        return results
    
    def check_for_transcription(self) -> Dict:
        """
        Check for shows ready for transcription and update their status.
        
        Returns:
            dict: A dictionary containing results.
        """
        self.logger.info("Checking for shows ready for transcription")
        
        # Get downloaded shows from database
        downloaded_shows = self.db.get_shows_by_status("downloaded")
        
        if not downloaded_shows:
            self.logger.info("No downloaded shows ready for transcription")
            return {"success": True, "shows": 0}
        
        self.logger.info(f"Found {len(downloaded_shows)} shows ready for transcription")
        
        # Mark shows as ready for transcription
        count = 0
        for show in downloaded_shows:
            # Make sure file exists
            file_path = show["download_path"]
            if not os.path.exists(file_path) and "*" in file_path:
                # Handle glob patterns
                import glob
                matching_files = glob.glob(file_path)
                if matching_files:
                    file_path = matching_files[0]
                    # Update the path in the database to the actual file
                    self.db.update_show(show["id"], {"download_path": file_path})
                else:
                    self.logger.warning(f"No files found matching pattern for show: {show['title']}")
                    continue
            
            if not os.path.exists(file_path):
                self.logger.warning(f"Download file not found for show: {show['title']}")
                continue
            
            # Update show status
            self.db.update_show(show["id"], {"status": "ready_for_transcription"})
            count += 1
        
        self.logger.info(f"Marked {count} shows as ready for transcription")
        return {"success": True, "shows": count}
    
    def run_service(self) -> None:
        """
        Run as a continuous service, periodically checking for shows and downloading.
        """
        self.logger.info("Starting BBC Radio Processor service")
        
        while True:
            try:
                # Refresh shows
                if self.config["downloader"].get("auto_refresh_interval", 0) > 0:
                    self.refresh_shows()
                
                # Process pending downloads
                max_downloads = self.config["downloader"].get("max_downloads_per_run", 0)
                self.process_pending_downloads(max_downloads)
                
                # Check for transcription
                if self.config["transcription"].get("auto_process", True):
                    self.check_for_transcription()
                
                # Sleep interval
                interval = self.config["downloader"].get("auto_refresh_interval", 60) * 60
                self.logger.info(f"Sleeping for {interval} seconds")
                time.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"Error in service loop: {e}", exc_info=True)
                # Sleep for a shorter time on error
                time.sleep(300)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BBC Radio Processor")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    parser.add_argument("--service", action="store_true", help="Run as a service")
    parser.add_argument("--command", choices=["refresh", "download", "process_pending", "check_transcription"],
                       help="Command to run")
    parser.add_argument("--show-id", type=int, help="Show ID for download command")
    parser.add_argument("--limit", type=int, default=0, help="Limit for process_pending command")
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    processor = BBCRadioProcessor(args.config)
    
    if args.service:
        processor.run_service()
    elif args.command == "refresh":
        processor.refresh_shows()
    elif args.command == "download":
        if not args.show_id:
            print("Error: --show-id is required for download command")
            return 1
        processor.download_show(args.show_id)
    elif args.command == "process_pending":
        processor.process_pending_downloads(args.limit)
    elif args.command == "check_transcription":
        processor.check_for_transcription()
    else:
        print("Error: Please specify --service or --command")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
