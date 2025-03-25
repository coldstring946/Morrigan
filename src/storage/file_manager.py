"""
Module for managing files and directories.
"""
import os
import shutil
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class FileManagerError(Exception):
    """Exception raised when a file operation fails."""
    pass


class FileManager:
    """
    Manager for file operations.
    
    This class provides methods to manage files and directories for the BBC Radio Processor.
    """
    
    def __init__(self, base_path: str, downloads_path: str, processed_path: str):
        """
        Initialize the file manager.
        
        Args:
            base_path (str): Base path for all operations.
            downloads_path (str): Path for downloaded files.
            processed_path (str): Path for processed files.
        """
        self.base_path = os.path.abspath(base_path)
        self.downloads_path = self._resolve_path(downloads_path)
        self.processed_path = self._resolve_path(processed_path)
        
        # Ensure directories exist
        self._ensure_dir(self.downloads_path)
        self._ensure_dir(self.processed_path)
        
        logger.info(f"FileManager initialized with base path: {self.base_path}")
        logger.info(f"Downloads path: {self.downloads_path}")
        logger.info(f"Processed path: {self.processed_path}")
    
    def _resolve_path(self, path: str) -> str:
        """
        Resolve a path relative to the base path if it's not absolute.
        
        Args:
            path (str): Path to resolve.
            
        Returns:
            str: Resolved path.
        """
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_path, path)
    
    def _ensure_dir(self, path: str) -> None:
        """
        Ensure a directory exists.
        
        Args:
            path (str): Directory path.
        """
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.error(f"Error creating directory {path}: {e}")
            raise FileManagerError(f"Error creating directory {path}: {e}")
    
    def get_download_path(self, show_title: str) -> str:
        """
        Get the download path for a show.
        
        Args:
            show_title (str): Show title.
            
        Returns:
            str: Path for downloading the show.
        """
        # Clean the title for use as a directory name
        safe_title = self.sanitize_filename(show_title)
        path = os.path.join(self.downloads_path, safe_title)
        self._ensure_dir(path)
        return path
    
    def get_processed_path(self, show_title: str) -> str:
        """
        Get the processed path for a show.
        
        Args:
            show_title (str): Show title.
            
        Returns:
            str: Path for processed files.
        """
        # Clean the title for use as a directory name
        safe_title = self.sanitize_filename(show_title)
        path = os.path.join(self.processed_path, safe_title)
        self._ensure_dir(path)
        return path
    
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename to be safe for the file system.
        
        Args:
            filename (str): Filename to sanitize.
            
        Returns:
            str: Sanitized filename.
        """
        # Replace problematic characters with underscores
        sanitized = re.sub(r'[\\/:*?"<>|]', '_', filename)
        # Remove leading/trailing spaces and periods
        sanitized = sanitized.strip(' .')
        # Limit length
        if len(sanitized) > 255:
            sanitized = sanitized[:255]
        return sanitized
    
    def copy_file(self, source: str, destination: str) -> str:
        """
        Copy a file from source to destination.
        
        Args:
            source (str): Source file path.
            destination (str): Destination file path.
            
        Returns:
            str: Path to the copied file.
        """
        try:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            
            # Copy the file
            shutil.copy2(source, destination)
            logger.info(f"Copied file: {source} to {destination}")
            return destination
        except OSError as e:
            logger.error(f"Error copying file {source} to {destination}: {e}")
            raise FileManagerError(f"Error copying file: {e}")
    
    def move_file(self, source: str, destination: str) -> str:
        """
        Move a file from source to destination.
        
        Args:
            source (str): Source file path.
            destination (str): Destination file path.
            
        Returns:
            str: Path to the moved file.
        """
        try:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            
            # Move the file
            shutil.move(source, destination)
            logger.info(f"Moved file: {source} to {destination}")
            return destination
        except OSError as e:
            logger.error(f"Error moving file {source} to {destination}: {e}")
            raise FileManagerError(f"Error moving file: {e}")
    
    def delete_file(self, path: str) -> bool:
        """
        Delete a file.
        
        Args:
            path (str): Path to the file.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if os.path.isfile(path):
                os.remove(path)
                logger.info(f"Deleted file: {path}")
                return True
            else:
                logger.warning(f"File does not exist: {path}")
                return False
        except OSError as e:
            logger.error(f"Error deleting file {path}: {e}")
            raise FileManagerError(f"Error deleting file: {e}")
    
    def list_files(self, directory: str, pattern: Optional[str] = None) -> List[str]:
        """
        List files in a directory.
        
        Args:
            directory (str): Directory path.
            pattern (str, optional): Pattern to match filenames.
            
        Returns:
            list: List of file paths.
        """
        try:
            directory = self._resolve_path(directory)
            
            if not os.path.isdir(directory):
                logger.warning(f"Directory does not exist: {directory}")
                return []
            
            if pattern:
                # Use Path for globbing
                return [str(p) for p in Path(directory).glob(pattern)]
            else:
                # List all files
                return [os.path.join(directory, f) for f in os.listdir(directory) 
                        if os.path.isfile(os.path.join(directory, f))]
        except OSError as e:
            logger.error(f"Error listing files in {directory}: {e}")
            raise FileManagerError(f"Error listing files: {e}")
    
    def get_file_size(self, path: str) -> int:
        """
        Get file size in bytes.
        
        Args:
            path (str): Path to the file.
            
        Returns:
            int: Size in bytes.
        """
        try:
            return os.path.getsize(path)
        except OSError as e:
            logger.error(f"Error getting file size for {path}: {e}")
            raise FileManagerError(f"Error getting file size: {e}")
    
    def get_file_info(self, path: str) -> Dict:
        """
        Get file information.
        
        Args:
            path (str): Path to the file.
            
        Returns:
            dict: File information.
        """
        try:
            if not os.path.isfile(path):
                raise FileManagerError(f"File does not exist: {path}")
            
            stat = os.stat(path)
            return {
                "path": path,
                "name": os.path.basename(path),
                "size": stat.st_size,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "extension": os.path.splitext(path)[1].lower()
            }
        except OSError as e:
            logger.error(f"Error getting file info for {path}: {e}")
            raise FileManagerError(f"Error getting file info: {e}")
    
    def create_directory(self, path: str) -> str:
        """
        Create a directory.
        
        Args:
            path (str): Directory path.
            
        Returns:
            str: Created directory path.
        """
        path = self._resolve_path(path)
        self._ensure_dir(path)
        return path
    
    def get_disk_usage(self, path: Optional[str] = None) -> Dict:
        """
        Get disk usage information.
        
        Args:
            path (str, optional): Path to check. Defaults to base path.
            
        Returns:
            dict: Disk usage information.
        """
        if path is None:
            path = self.base_path
        
        try:
            total, used, free = shutil.disk_usage(path)
            return {
                "total": total,
                "used": used,
                "free": free,
                "percent_used": (used / total) * 100
            }
        except OSError as e:
            logger.error(f"Error getting disk usage for {path}: {e}")
            raise FileManagerError(f"Error getting disk usage: {e}")
    
    def is_audio_file(self, path: str) -> bool:
        """
        Check if a file is an audio file based on extension.
        
        Args:
            path (str): File path.
            
        Returns:
            bool: True if audio file, False otherwise.
        """
        audio_extensions = ['.mp3', '.aac', '.wav', '.flac', '.ogg', '.m4a']
        ext = os.path.splitext(path)[1].lower()
        return ext in audio_extensions
    
    def get_audio_files(self, directory: str) -> List[str]:
        """
        Get all audio files in a directory.
        
        Args:
            directory (str): Directory path.
            
        Returns:
            list: List of audio file paths.
        """
        all_files = self.list_files(directory)
        return [f for f in all_files if self.is_audio_file(f)]
