"""
Module for interacting with the get_iplayer tool to download BBC radio content.
"""
import os
import re
import json
import logging
import subprocess
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class GetIPlayerError(Exception):
    """Exception raised when get_iplayer encounters an error."""
    pass


class GetIPlayer:
    """
    Wrapper class for the get_iplayer tool.
    
    This class provides methods to search for, list, and download BBC radio content
    using the get_iplayer command-line tool.
    """
    
    def __init__(self, options: Optional[Dict] = None):
        """
        Initialize GetIPlayer with optional default options.
        
        Args:
            options (dict, optional): Default options to use with get_iplayer.
        """
        self.options = options or {}
        self._check_installation()
    
    def _check_installation(self) -> None:
        """
        Check if get_iplayer is installed and accessible.
        
        Raises:
            GetIPlayerError: If get_iplayer is not installed or not accessible.
        """
        try:
            result = subprocess.run(
                ["get_iplayer", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            logger.debug(f"get_iplayer version: {result.stdout.strip()}")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.error(f"get_iplayer is not installed or not accessible: {e}")
            raise GetIPlayerError("get_iplayer is not installed or not accessible")
    
    def _build_command(self, command: List[str], options: Optional[Dict] = None) -> List[str]:
        """
        Build a complete get_iplayer command with options.
        
        Args:
            command (list): The base command as a list of strings.
            options (dict, optional): Additional options to include.
            
        Returns:
            list: The complete command as a list of strings.
        """
        cmd = ["get_iplayer"]
        cmd.extend(command)
        
        # Apply default options
        for key, value in self.options.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.append(f"--{key}")
                cmd.append(str(value))
        
        # Apply command-specific options
        if options:
            for key, value in options.items():
                if isinstance(value, bool):
                    if value:
                        cmd.append(f"--{key}")
                else:
                    cmd.append(f"--{key}")
                    cmd.append(str(value))
        
        return cmd
    
    def _run_command(self, cmd: List[str]) -> Tuple[str, str]:
        """
        Run a get_iplayer command and return its output.
        
        Args:
            cmd (list): The command to run as a list of strings.
            
        Returns:
            tuple: A tuple of (stdout, stderr).
            
        Raises:
            GetIPlayerError: If the command fails to execute.
        """
        logger.debug(f"Running command: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False  # We'll handle errors manually
            )
            return result.stdout, result.stderr
        except subprocess.SubprocessError as e:
            logger.error(f"Error executing get_iplayer command: {e}")
            raise GetIPlayerError(f"Error executing get_iplayer command: {e}")
    
    def search(self, query: str, options: Optional[Dict] = None) -> List[Dict]:
        """
        Search for BBC content.
        
        Args:
            query (str): The search query.
            options (dict, optional): Additional options for the search.
            
        Returns:
            list: A list of dictionaries containing search results.
        """
        search_options = {"json": True, "type": "radio"}
        if options:
            search_options.update(options)
        
        cmd = self._build_command(["--search", query], search_options)
        stdout, stderr = self._run_command(cmd)
        
        if stderr and "ERROR" in stderr:
            logger.error(f"Error searching for content: {stderr}")
            raise GetIPlayerError(f"Error searching for content: {stderr}")
        
        try:
            # get_iplayer's JSON output is a bit inconsistent
            # We need to fix any malformed JSON
            json_str = stdout.strip()
            # Remove any non-JSON lines
            json_lines = [line for line in json_str.splitlines() if line.strip().startswith("{")]
            if not json_lines:
                return []
            
            json_str = "[" + ",".join(json_lines) + "]"
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            logger.debug(f"Response: {stdout}")
            raise GetIPlayerError(f"Error parsing JSON response: {e}")
    
    def get_show_info(self, pid: str) -> Dict:
        """
        Get detailed information about a specific show.
        
        Args:
            pid (str): The BBC programme ID.
            
        Returns:
            dict: A dictionary containing show information.
        """
        cmd = self._build_command(["--info", "--pid", pid, "--json"])
        stdout, stderr = self._run_command(cmd)
        
        if stderr and "ERROR" in stderr:
            logger.error(f"Error getting show info: {stderr}")
            raise GetIPlayerError(f"Error getting show info: {stderr}")
        
        try:
            json_str = stdout.strip()
            # Remove any non-JSON lines
            json_lines = [line for line in json_str.splitlines() if line.strip().startswith("{")]
            if not json_lines:
                raise GetIPlayerError(f"No information found for PID: {pid}")
            
            result = json.loads(json_lines[0])
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            logger.debug(f"Response: {stdout}")
            raise GetIPlayerError(f"Error parsing JSON response: {e}")
    
    def download(self, pid: str, options: Optional[Dict] = None) -> Dict:
        """
        Download a BBC show.
        
        Args:
            pid (str): The BBC programme ID.
            options (dict, optional): Additional options for the download.
            
        Returns:
            dict: A dictionary containing download results.
        """
        download_options = {"pid": pid, "output-type": "pid"}
        if options:
            download_options.update(options)
        
        cmd = self._build_command(["--get"], download_options)
        stdout, stderr = self._run_command(cmd)
        
        # Parse the output to extract the output path
        output_path = None
        for line in stdout.splitlines():
            match = re.search(r'INFO: File\(s\) saved to (.+)', line)
            if match:
                output_path = match.group(1).strip()
        
        if stderr and "ERROR" in stderr:
            logger.error(f"Error downloading content: {stderr}")
            raise GetIPlayerError(f"Error downloading content: {stderr}")
        
        return {
            "pid": pid,
            "success": "Downloading programme" in stdout or "File(s) saved to" in stdout,
            "output_path": output_path,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def refresh_cache(self) -> None:
        """
        Refresh the get_iplayer cache.
        
        Returns:
            None
        """
        cmd = self._build_command(["--refresh"])
        stdout, stderr = self._run_command(cmd)
        
        if stderr and "ERROR" in stderr:
            logger.error(f"Error refreshing cache: {stderr}")
            raise GetIPlayerError(f"Error refreshing cache: {stderr}")
        
        logger.info("get_iplayer cache refreshed successfully")
    
    def list_channels(self) -> List[str]:
        """
        List available BBC channels.
        
        Returns:
            list: A list of available channels.
        """
        cmd = self._build_command(["--channels"])
        stdout, stderr = self._run_command(cmd)
        
        if stderr and "ERROR" in stderr:
            logger.error(f"Error listing channels: {stderr}")
            raise GetIPlayerError(f"Error listing channels: {stderr}")
        
        channels = []
        for line in stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("get_iplayer"):
                channels.append(line)
        
        return channels
    
    def list_categories(self) -> List[str]:
        """
        List available BBC categories.
        
        Returns:
            list: A list of available categories.
        """
        cmd = self._build_command(["--categories"])
        stdout, stderr = self._run_command(cmd)
        
        if stderr and "ERROR" in stderr:
            logger.error(f"Error listing categories: {stderr}")
            raise GetIPlayerError(f"Error listing categories: {stderr}")
        
        categories = []
        for line in stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("get_iplayer"):
                categories.append(line)
        
        return categories
