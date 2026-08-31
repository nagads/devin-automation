"""Devin API integration service."""

import logging
import httpx
from typing import Optional
from datetime import datetime

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DevinSession:
    """Represents a Devin session response."""
    
    def __init__(self, data: dict):
        self.session_id = data.get("session_id")
        self.status = data.get("status") or data.get("status_enum")
        self.status_detail = data.get("status_detail")
        self.url = data.get("url")
        self.created_at = data.get("created_at")
        self.updated_at = data.get("updated_at")
        self.result = data.get("result")
        self.error = data.get("error")
        
        # Handle pull_requests array from v3 API
        pull_requests = data.get("pull_requests", [])
        if pull_requests and len(pull_requests) > 0:
            self.pull_request_url = pull_requests[0].get("pr_url")
            self.pull_request_state = pull_requests[0].get("pr_state")
        else:
            self.pull_request_url = data.get("pull_request_url")
            self.pull_request_state = None


class DevinService:
    """Service for interacting with Devin API."""
    
    def __init__(self):
        self.api_key = settings.devin_api_key
        self.org_id = settings.devin_org_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Use v3 API if org_id is provided, otherwise v1
        if self.org_id:
            self.base_url = f"https://api.devin.ai/v3/organizations/{self.org_id}"
            logger.info(f"Using Devin v3 API with org: {self.org_id}")
        else:
            self.base_url = "https://api.devin.ai/v1"
            logger.info("Using Devin v1 API (legacy)")
    
    async def create_session(
        self,
        prompt: str,
        repo_url: Optional[str] = None
    ) -> DevinSession:
        """
        Create a new Devin session to work on a task.
        
        Args:
            prompt: The task description for Devin
            repo_url: Optional repository URL for context
            
        Returns:
            DevinSession object with session details
        """
        payload = {
            "prompt": prompt
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/sessions",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                session = DevinSession(data)
                logger.info(f"Created Devin session: {session.session_id}")
                return session
                
        except httpx.HTTPError as e:
            logger.error(f"Error creating Devin session: {e}")
            raise
    
    async def get_session(self, session_id: str) -> DevinSession:
        """
        Get the current status of a Devin session.
        
        Args:
            session_id: The session ID to query
            
        Returns:
            DevinSession object with current status
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{session_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()
                
                return DevinSession(data)
                
        except httpx.HTTPError as e:
            logger.error(f"Error getting Devin session {session_id}: {e}")
            raise
    
    async def send_message(self, session_id: str, message: str) -> dict:
        """
        Send a message to an active Devin session.
        
        Args:
            session_id: The session ID
            message: Message to send to Devin
            
        Returns:
            Response data
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/sessions/{session_id}/messages",
                    headers=self.headers,
                    json={"message": message}
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPError as e:
            logger.error(f"Error sending message to session {session_id}: {e}")
            raise
    
    def build_bug_fix_prompt(
        self,
        issue_title: str,
        issue_body: str,
        repo_url: str,
        issue_number: int
    ) -> str:
        """
        Build the prompt for Devin to fix a bug.
        
        Args:
            issue_title: The bug issue title
            issue_body: The bug issue description
            repo_url: Repository URL to work on
            issue_number: Issue number for PR reference
            
        Returns:
            Formatted prompt string
        """
        return f"""Fix the following bug in the repository:

## Repository
{repo_url}

## Issue #{issue_number}: {issue_title}

## Description
{issue_body}

## Instructions
1. Clone the repository and create a new branch for your fix
2. Analyze the issue and identify the root cause
3. Implement a fix following the project's coding standards
4. Run existing tests to ensure your fix doesn't break anything
5. Add or update tests if applicable
6. Create a pull request with:
   - Title: "fix: {issue_title} (#{issue_number})"
   - Description explaining what was fixed and how
   - Reference to the original issue

## Important Notes
- Follow the existing code style and conventions
- Keep the fix focused and minimal
- If the issue is unclear or needs more information, note it in the PR description
- Target the main branch for the PR
"""

    def is_session_complete(self, session: DevinSession) -> bool:
        """Check if a session has completed (successfully or with failure)."""
        # Traditional completion statuses
        if session.status in ["completed", "failed", "error", "stopped", "suspended"]:
            return True
        # If session has PR and is waiting for user, consider it done
        if session.pull_request_url and session.status_detail in ["waiting_for_user", "inactivity"]:
            return True
        return False
    
    def is_session_successful(self, session: DevinSession) -> bool:
        """Check if a session completed successfully."""
        # Traditional success
        if session.status == "completed":
            return True
        # Has PR created = success for our purposes
        if session.pull_request_url:
            return True
        return False
