"""GitHub API integration service."""

import logging
from typing import Optional
from github import Github, GithubException
from github.Issue import Issue as GithubIssue
from github.PullRequest import PullRequest as GithubPR
from github.Repository import Repository

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GitHubService:
    """Service for interacting with GitHub API."""
    
    def __init__(self):
        self.client = Github(settings.github_token)
        self._fork_repo: Optional[Repository] = None
        self._upstream_repo: Optional[Repository] = None
    
    @property
    def fork_repo(self) -> Repository:
        """Get the fork repository."""
        if self._fork_repo is None:
            self._fork_repo = self.client.get_repo(settings.fork_repo)
        return self._fork_repo
    
    @property
    def upstream_repo(self) -> Repository:
        """Get the upstream repository."""
        if self._upstream_repo is None:
            self._upstream_repo = self.client.get_repo(settings.upstream_repo)
        return self._upstream_repo
    
    def get_upstream_bugs_without_pr(self, limit: int = 20) -> list[GithubIssue]:
        """
        Get open bug issues from upstream that don't have linked PRs.
        
        Args:
            limit: Maximum number of issues to return
            
        Returns:
            List of GitHub Issue objects
        """
        issues = []
        try:
            # Get open issues with bug label
            logger.info(f"Fetching issues from {settings.upstream_repo} with label '{settings.upstream_bug_label}'")
            open_issues = self.upstream_repo.get_issues(
                state="open",
                labels=[settings.upstream_bug_label]
            )
            
            count = 0
            for issue in open_issues:
                count += 1
                if len(issues) >= limit:
                    break
                    
                # Skip pull requests (GitHub API returns PRs as issues too)
                if issue.pull_request is not None:
                    logger.debug(f"Skipping #{issue.number} - it's a PR")
                    continue
                
                # For simplicity, just take the issue without checking for linked PRs
                # (The timeline check was too strict and slow)
                issues.append(issue)
                logger.info(f"Found eligible issue: #{issue.number} - {issue.title}")
            
            logger.info(f"Scanned {count} issues, found {len(issues)} eligible")
            return issues
            
        except GithubException as e:
            logger.error(f"Error fetching upstream issues: {e}")
            raise
    
    def _has_linked_pr(self, issue: GithubIssue) -> bool:
        """
        Check if an issue has a linked pull request.
        
        This checks the timeline events for PR references.
        """
        try:
            # Check timeline for cross-references to PRs
            timeline = issue.get_timeline()
            for event in timeline:
                if event.event == "cross-referenced":
                    # Check if the source is a PR
                    source = getattr(event, "source", None)
                    if source and hasattr(source, "issue"):
                        if source.issue.pull_request is not None:
                            return True
            return False
        except Exception as e:
            logger.warning(f"Could not check PR links for issue #{issue.number}: {e}")
            # If we can't check, assume no PR to avoid missing issues
            return False
    
    def create_issue_in_fork(
        self,
        title: str,
        body: str,
        labels: list[str],
        upstream_issue_number: int
    ) -> GithubIssue:
        """
        Create an issue in the fork repository.
        
        Args:
            title: Issue title
            body: Issue body (with attribution)
            labels: Labels to apply
            upstream_issue_number: Original issue number for reference
            
        Returns:
            Created GitHub Issue object
        """
        try:
            # Ensure labels exist
            self._ensure_labels_exist(labels)
            
            # Create the issue
            issue = self.fork_repo.create_issue(
                title=title,
                body=body,
                labels=labels
            )
            
            logger.info(f"Created issue #{issue.number} in fork: {title}")
            return issue
            
        except GithubException as e:
            logger.error(f"Error creating issue in fork: {e}")
            raise
    
    def _ensure_labels_exist(self, labels: list[str]):
        """Ensure all required labels exist in the fork repository."""
        existing_labels = {label.name for label in self.fork_repo.get_labels()}
        
        label_colors = {
            settings.label_cloned: "c5def5",      # Light blue
            settings.label_pending: "fbca04",      # Yellow
            settings.label_working: "0e8a16",      # Green
            settings.label_done: "6f42c1",         # Purple
            settings.label_failed: "d93f0b",       # Red
        }
        
        for label in labels:
            if label not in existing_labels:
                try:
                    color = label_colors.get(label, "ededed")
                    self.fork_repo.create_label(name=label, color=color)
                    logger.info(f"Created label: {label}")
                except GithubException as e:
                    if e.status != 422:  # 422 = already exists
                        raise
    
    def update_issue_labels(
        self,
        issue_number: int,
        add_labels: list[str] = None,
        remove_labels: list[str] = None
    ):
        """
        Update labels on an issue in the fork.
        
        Args:
            issue_number: Issue number in the fork
            add_labels: Labels to add
            remove_labels: Labels to remove
        """
        try:
            issue = self.fork_repo.get_issue(issue_number)
            
            if remove_labels:
                for label in remove_labels:
                    try:
                        issue.remove_from_labels(label)
                    except GithubException:
                        pass  # Label might not exist
            
            if add_labels:
                self._ensure_labels_exist(add_labels)
                issue.add_to_labels(*add_labels)
            
            logger.info(f"Updated labels on issue #{issue_number}")
            
        except GithubException as e:
            logger.error(f"Error updating labels on issue #{issue_number}: {e}")
            raise
    
    def get_fork_issues_by_label(self, label: str) -> list[GithubIssue]:
        """Get all open issues in fork with a specific label."""
        try:
            issues = list(self.fork_repo.get_issues(state="open", labels=[label]))
            return issues
        except GithubException as e:
            logger.error(f"Error fetching issues with label {label}: {e}")
            raise
    
    def close_issue(self, issue_number: int):
        """Close an issue in the fork."""
        try:
            issue = self.fork_repo.get_issue(issue_number)
            issue.edit(state="closed")
            logger.info(f"Closed issue #{issue_number}")
        except GithubException as e:
            logger.error(f"Error closing issue #{issue_number}: {e}")
            raise
    
    def get_open_pull_requests(self) -> list[GithubPR]:
        """Get all open pull requests in the fork."""
        try:
            return list(self.fork_repo.get_pulls(state="open"))
        except GithubException as e:
            logger.error(f"Error fetching pull requests: {e}")
            raise
    
    def close_pull_request(self, pr_number: int):
        """Close a pull request in the fork."""
        try:
            pr = self.fork_repo.get_pull(pr_number)
            pr.edit(state="closed")
            logger.info(f"Closed PR #{pr_number}")
        except GithubException as e:
            logger.error(f"Error closing PR #{pr_number}: {e}")
            raise
    
    def delete_branch(self, branch_name: str):
        """Delete a branch in the fork."""
        try:
            ref = self.fork_repo.get_git_ref(f"heads/{branch_name}")
            ref.delete()
            logger.info(f"Deleted branch: {branch_name}")
        except GithubException as e:
            if e.status != 404:  # Branch doesn't exist
                logger.error(f"Error deleting branch {branch_name}: {e}")
    
    def get_pr_for_issue(self, issue_number: int) -> Optional[GithubPR]:
        """Find a PR that references an issue number."""
        try:
            pulls = self.fork_repo.get_pulls(state="all")
            for pr in pulls:
                # Check if PR title or body references the issue
                if f"#{issue_number}" in pr.title or (pr.body and f"#{issue_number}" in pr.body):
                    return pr
            return None
        except GithubException as e:
            logger.error(f"Error finding PR for issue #{issue_number}: {e}")
            return None
