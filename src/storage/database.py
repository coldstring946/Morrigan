"""
Module for database operations.
"""
import os
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Exception raised when a database operation fails."""
    pass


class Database:
    """
    Database handler for the BBC Radio Processor.
    
    This class provides methods to interact with the database, handling
    both SQLite and PostgreSQL backends.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the database connection.
        
        Args:
            config (dict): Database configuration.
        """
        self.config = config
        self.db_type = config.get("type", "sqlite").lower()
        self.connection = None
        
        if self.db_type == "sqlite":
            self._init_sqlite()
        elif self.db_type == "postgresql":
            self._init_postgresql()
        else:
            raise DatabaseError(f"Unsupported database type: {self.db_type}")
    
    def _init_sqlite(self):
        """Initialize SQLite database connection."""
        try:
            db_path = os.path.join(self.config["path"], self.config["name"])
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            self.connection = sqlite3.connect(db_path)
            self.connection.row_factory = sqlite3.Row
            
            # Enable foreign keys
            self.connection.execute("PRAGMA foreign_keys = ON")
            
            # Create tables if they don't exist
            self._create_tables_sqlite()
            
            logger.info(f"Connected to SQLite database: {db_path}")
        except sqlite3.Error as e:
            logger.error(f"SQLite connection error: {e}")
            raise DatabaseError(f"SQLite connection error: {e}")
    
    def _init_postgresql(self):
        """Initialize PostgreSQL database connection."""
        try:
            import psycopg2
            import psycopg2.extras
            
            self.connection = psycopg2.connect(
                host=self.config.get("host", "localhost"),
                port=self.config.get("port", 5432),
                user=self.config.get("user", "postgres"),
                password=self.config.get("password", ""),
                database=self.config.get("name", "bbc_radio")
            )
            
            # Create tables if they don't exist
            self._create_tables_postgresql()
            
            logger.info(f"Connected to PostgreSQL database: {self.config.get('name')}")
        except ImportError:
            logger.error("psycopg2 module not found, required for PostgreSQL")
            raise DatabaseError("psycopg2 module not found, required for PostgreSQL")
        except Exception as e:
            logger.error(f"PostgreSQL connection error: {e}")
            raise DatabaseError(f"PostgreSQL connection error: {e}")
    
    def _create_tables_sqlite(self):
        """Create tables for SQLite database."""
        cursor = self.connection.cursor()
        
        # Create shows table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS shows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pid TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT,
            episode TEXT,
            broadcast_date TEXT,
            duration INTEGER,
            download_path TEXT,
            status TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create transcriptions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            format TEXT NOT NULL,
            word_count INTEGER,
            speakers INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (show_id) REFERENCES shows (id) ON DELETE CASCADE,
            UNIQUE (show_id, format)
        )
        """)
        
        # Create tasks table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            task_type TEXT NOT NULL,
            show_id INTEGER,
            status TEXT NOT NULL,
            progress REAL,
            result TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (show_id) REFERENCES shows (id) ON DELETE SET NULL
        )
        """)
        
        # Create settings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        self.connection.commit()
    
    def _create_tables_postgresql(self):
        """Create tables for PostgreSQL database."""
        cursor = self.connection.cursor()
        
        # Create shows table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS shows (
            id SERIAL PRIMARY KEY,
            pid VARCHAR(20) NOT NULL UNIQUE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            episode VARCHAR(255),
            broadcast_date TIMESTAMP,
            duration INTEGER,
            download_path VARCHAR(512),
            status VARCHAR(20) NOT NULL,
            metadata JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create transcriptions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id SERIAL PRIMARY KEY,
            show_id INTEGER NOT NULL REFERENCES shows(id) ON DELETE CASCADE,
            path VARCHAR(512) NOT NULL,
            format VARCHAR(20) NOT NULL,
            word_count INTEGER,
            speakers INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(show_id, format)
        )
        """)
        
        # Create tasks table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            task_id VARCHAR(50) NOT NULL UNIQUE,
            task_type VARCHAR(20) NOT NULL,
            show_id INTEGER REFERENCES shows(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL,
            progress FLOAT,
            result JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create settings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(50) PRIMARY KEY,
            value JSONB NOT NULL,
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        self.connection.commit()
        cursor.close()
    
    def add_show(self, show_data: Dict) -> int:
        """
        Add a new show to the database.
        
        Args:
            show_data (dict): Show data.
            
        Returns:
            int: ID of the inserted show.
        """
        try:
            cursor = self.connection.cursor()
            
            # Prepare metadata
            if self.db_type == "sqlite":
                if "metadata" in show_data and isinstance(show_data["metadata"], dict):
                    show_data["metadata"] = json.dumps(show_data["metadata"])
            
            # Add timestamp fields if not present
            now = datetime.now().isoformat()
            if "created_at" not in show_data:
                show_data["created_at"] = now
            if "updated_at" not in show_data:
                show_data["updated_at"] = now
            
            # Build SQL query dynamically
            fields = list(show_data.keys())
            placeholders = ", ".join(["?"] * len(fields))
            values = [show_data[field] for field in fields]
            
            query = f"INSERT INTO shows ({', '.join(fields)}) VALUES ({placeholders})"
            
            cursor.execute(query, values)
            self.connection.commit()
            
            # Get the ID of the inserted row
            if self.db_type == "sqlite":
                show_id = cursor.lastrowid
            else:
                cursor.execute("SELECT lastval()")
                show_id = cursor.fetchone()[0]
            
            cursor.close()
            return show_id
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Error adding show: {e}")
            raise DatabaseError(f"Error adding show: {e}")
    
    def update_show(self, show_id: int, show_data: Dict) -> bool:
        """
        Update an existing show.
        
        Args:
            show_id (int): Show ID.
            show_data (dict): Updated show data.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            cursor = self.connection.cursor()
            
            # Prepare metadata
            if self.db_type == "sqlite":
                if "metadata" in show_data and isinstance(show_data["metadata"], dict):
                    show_data["metadata"] = json.dumps(show_data["metadata"])
            
            # Always update the updated_at timestamp
            show_data["updated_at"] = datetime.now().isoformat()
            
            # Build SQL query dynamically
            set_clause = ", ".join([f"{key} = ?" for key in show_data.keys()])
            values = list(show_data.values())
            values.append(show_id)
            
            query = f"UPDATE shows SET {set_clause} WHERE id = ?"
            
            cursor.execute(query, values)
            self.connection.commit()
            cursor.close()
            
            return True
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Error updating show: {e}")
            raise DatabaseError(f"Error updating show: {e}")
    
    def get_show(self, show_id: int) -> Optional[Dict]:
        """
        Get a show by ID.
        
        Args:
            show_id (int): Show ID.
            
        Returns:
            dict: Show data or None if not found.
        """
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM shows WHERE id = ?"
            cursor.execute(query, (show_id,))
            
            row = cursor.fetchone()
            cursor.close()
            
            if not row:
                return None
            
            # Convert to dictionary
            show = dict(row) if self.db_type == "sqlite" else {k: row[k] for k in row.keys()}
            
            # Convert metadata from JSON string to dict
            if self.db_type == "sqlite" and "metadata" in show and show["metadata"]:
                show["metadata"] = json.loads(show["metadata"])
            
            return show
            
        except Exception as e:
            logger.error(f"Error getting show: {e}")
            raise DatabaseError(f"Error getting show: {e}")
    
    def get_show_by_pid(self, pid: str) -> Optional[Dict]:
        """
        Get a show by PID.
        
        Args:
            pid (str): BBC programme ID.
            
        Returns:
            dict: Show data or None if not found.
        """
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM shows WHERE pid = ?"
            cursor.execute(query, (pid,))
            
            row = cursor.fetchone()
            cursor.close()
            
            if not row:
                return None
            
            # Convert to dictionary
            show = dict(row) if self.db_type == "sqlite" else {k: row[k] for k in row.keys()}
            
            # Convert metadata from JSON string to dict
            if self.db_type == "sqlite" and "metadata" in show and show["metadata"]:
                show["metadata"] = json.loads(show["metadata"])
            
            return show
            
        except Exception as e:
            logger.error(f"Error getting show by PID: {e}")
            raise DatabaseError(f"Error getting show by PID: {e}")
    
    def get_shows_by_status(self, status: str, limit: int = 0) -> List[Dict]:
        """
        Get shows by status.
        
        Args:
            status (str): Show status.
            limit (int): Maximum number of shows to return (0 for all).
            
        Returns:
            list: List of show dictionaries.
        """
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM shows WHERE status = ? ORDER BY broadcast_date DESC"
            if limit > 0:
                query += f" LIMIT {limit}"
            
            cursor.execute(query, (status,))
            
            rows = cursor.fetchall()
            cursor.close()
            
            shows = []
            for row in rows:
                # Convert to dictionary
                show = dict(row) if self.db_type == "sqlite" else {k: row[k] for k in row.keys()}
                
                # Convert metadata from JSON string to dict
                if self.db_type == "sqlite" and "metadata" in show and show["metadata"]:
                    show["metadata"] = json.loads(show["metadata"])
                
                shows.append(show)
            
            return shows
            
        except Exception as e:
            logger.error(f"Error getting shows by status: {e}")
            raise DatabaseError(f"Error getting shows by status: {e}")
    
    def search_shows(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search for shows.
        
        Args:
            query (str): Search query.
            limit (int): Maximum number of shows to return.
            
        Returns:
            list: List of show dictionaries.
        """
        try:
            cursor = self.connection.cursor()
            
            # Prepare search query
            search_term = f"%{query}%"
            query_sql = """
            SELECT * FROM shows 
            WHERE title LIKE ? OR description LIKE ? OR episode LIKE ?
            ORDER BY broadcast_date DESC
            LIMIT ?
            """
            
            cursor.execute(query_sql, (search_term, search_term, search_term, limit))
            
            rows = cursor.fetchall()
            cursor.close()
            
            shows = []
            for row in rows:
                # Convert to dictionary
                show = dict(row) if self.db_type == "sqlite" else {k: row[k] for k in row.keys()}
                
                # Convert metadata from JSON string to dict
                if self.db_type == "sqlite" and "metadata" in show and show["metadata"]:
                    show["metadata"] = json.loads(show["metadata"])
                
                shows.append(show)
            
            return shows
            
        except Exception as e:
            logger.error(f"Error searching shows: {e}")
            raise DatabaseError(f"Error searching shows: {e}")
    
    def add_transcription(self, transcription_data: Dict) -> int:
        """
        Add a new transcription to the database.
        
        Args:
            transcription_data (dict): Transcription data.
            
        Returns:
            int: ID of the inserted transcription.
        """
        try:
            cursor = self.connection.cursor()
            
            # Add timestamp fields if not present
            now = datetime.now().isoformat()
            if "created_at" not in transcription_data:
                transcription_data["created_at"] = now
            if "updated_at" not in transcription_data:
                transcription_data["updated_at"] = now
            
            # Build SQL query dynamically
            fields = list(transcription_data.keys())
            placeholders = ", ".join(["?"] * len(fields))
            values = [transcription_data[field] for field in fields]
            
            query = f"INSERT INTO transcriptions ({', '.join(fields)}) VALUES ({placeholders})"
            
            cursor.execute(query, values)
            self.connection.commit()
            
            # Get the ID of the inserted row
            if self.db_type == "sqlite":
                transcription_id = cursor.lastrowid
            else:
                cursor.execute("SELECT lastval()")
                transcription_id = cursor.fetchone()[0]
            
            cursor.close()
            return transcription_id
            
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Error adding transcription: {e}")
            raise DatabaseError(f"Error adding transcription: {e}")
    
    def get_transcription(self, transcription_id: int) -> Optional[Dict]:
        """
        Get a transcription by ID.
        
        Args:
            transcription_id (int): Transcription ID.
            
        Returns:
            dict: Transcription data or None if not found.
        """
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM transcriptions WHERE id = ?"
            cursor.execute(query, (transcription_id,))
            
            row = cursor.fetchone()
            cursor.close()
            
            if not row:
                return None
            
            # Convert to dictionary
            return dict(row) if self.db_type == "sqlite" else {k: row[k] for k in row.keys()}
            
        except Exception as e:
            logger.error(f"Error getting transcription: {e}")
            raise DatabaseError(f"Error getting transcription: {e}")
    
    def get_transcriptions_for_show(self, show_id: int) -> List[Dict]:
        """
        Get all transcriptions for a show.
        
        Args:
            show_id (int): Show ID.
            
        Returns:
            list: List of transcription dictionaries.
        """
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM transcriptions WHERE show_id = ?"
            cursor.execute(query, (show_id,))
            
            rows = cursor.fetchall()
            cursor.close()
            
            transcriptions = []
            for row in rows:
                # Convert to dictionary
                transcription = dict(row) if self.db_type == "sqlite" else {k: row[k] for k in row.keys()}
                transcriptions.append(transcription)
            
            return transcriptions
            
        except Exception as e:
            logger.error(f"Error getting transcriptions for show: {e}")
            raise DatabaseError(f"Error getting transcriptions for show: {e}")
    
    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
