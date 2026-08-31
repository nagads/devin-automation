"""Main orchestration logic for the automation system."""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Issue, DevinSession as DevinSessionModel, ActivityLog, IssueStatus, SessionStatus
from app.services.github_service import GitHubService
from app.services.devin_service import DevinService

logger = logging.getLogger(__name__)
settings = get_settings()


class Orchestrator:
    """Orchestrates the bug remediation workflow."""
    
    def __init__(self, db: Session):
        self.db = db
        self.github = GitHubService()
        self.devin = DevinService()
    
    def log_activity(self, action: str, description: str, issue_id: int = None, session_id: str = None):
        """Log an activity to the database."""
        log = ActivityLog(
            action=action,
            description=description,
            issue_id=issue_id,
            session_id=session_id
        )
        self.db.add(log)
        self.db.commit()
    
    # ==================== SETUP ====================
    
    def setup(self) -> dict:
        """
        Clone issues from upstream to fork.
        
        Returns:
            Summary of cloned issues
        """
        logger.info("Starting setup: cloning issues from upstream")
        self.log_activity("setup_started", "Starting to clone issues from upstream")
        
        # Get eligible issues from upstream
        upstream_issues = self.github.get_upstream_bugs_without_pr(
            limit=settings.max_issues_to_clone
        )
        
        if not upstream_issues:
            self.log_activity("setup_complete", "No eligible issues found in upstream")
            return {
                "status": "complete",
                "message": "No eligible issues found in upstream",
                "issues_cloned": 0
            }
        
        cloned_count = 0
        errors = []
        
        for upstream_issue in upstream_issues:
            try:
                # Check if already cloned
                existing = self.db.query(Issue).filter(
                    Issue.upstream_issue_number == upstream_issue.number
                ).first()
                
                if existing:
                    logger.info(f"Issue #{upstream_issue.number} already cloned, skipping")
                    continue
                
                # Create issue in fork
                body = f"""**Cloned from apache/superset#{upstream_issue.number}**

Original issue: {upstream_issue.html_url}

---

{upstream_issue.body or 'No description provided.'}
"""
                
                fork_issue = self.github.create_issue_in_fork(
                    title=upstream_issue.title,
                    body=body,
                    labels=[settings.label_cloned, settings.label_pending],
                    upstream_issue_number=upstream_issue.number
                )
                
                # Store in database
                issue = Issue(
                    upstream_issue_number=upstream_issue.number,
                    upstream_issue_url=upstream_issue.html_url,
                    fork_issue_number=fork_issue.number,
                    fork_issue_url=fork_issue.html_url,
                    title=upstream_issue.title,
                    body=upstream_issue.body,
                    status=IssueStatus.PENDING
                )
                self.db.add(issue)
                self.db.commit()
                
                cloned_count += 1
                self.log_activity(
                    "issue_cloned",
                    f"Cloned issue #{upstream_issue.number} to fork as #{fork_issue.number}",
                    issue_id=issue.id
                )
                
            except Exception as e:
                error_msg = f"Error cloning issue #{upstream_issue.number}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        summary = {
            "status": "complete",
            "message": f"Setup complete. Cloned {cloned_count} issues.",
            "issues_cloned": cloned_count,
            "errors": errors if errors else None
        }
        
        self.log_activity("setup_complete", f"Setup complete. Cloned {cloned_count} issues.")
        return summary
    
    # ==================== RUN ====================
    
    async def run(self) -> dict:
        """
        Process pending issues by starting Devin sessions.
        
        Returns:
            Summary of processing
        """
        logger.info("Starting run: processing pending issues")
        self.log_activity("run_started", "Starting to process pending issues")
        
        # Check capacity
        active_sessions = self.db.query(DevinSessionModel).filter(
            DevinSessionModel.status.in_([SessionStatus.CREATED, SessionStatus.RUNNING])
        ).count()
        
        available_slots = settings.max_concurrent_sessions - active_sessions
        
        if available_slots <= 0:
            msg = f"At capacity: {active_sessions} active sessions"
            self.log_activity("run_skipped", msg)
            return {
                "status": "skipped",
                "message": msg,
                "issues_processed": 0
            }
        
        # Get pending issues
        pending_issues = self.db.query(Issue).filter(
            Issue.status == IssueStatus.PENDING
        ).limit(min(available_slots, settings.max_issues_per_poll)).all()
        
        if not pending_issues:
            self.log_activity("run_complete", "No pending issues to process")
            return {
                "status": "complete",
                "message": "No pending issues to process",
                "issues_processed": 0
            }
        
        processed_count = 0
        errors = []
        
        for issue in pending_issues:
            try:
                await self._process_issue(issue)
                processed_count += 1
            except Exception as e:
                error_msg = f"Error processing issue #{issue.fork_issue_number}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                
                # Mark as failed
                issue.status = IssueStatus.FAILED
                self.db.commit()
                
                self.github.update_issue_labels(
                    issue.fork_issue_number,
                    add_labels=[settings.label_failed],
                    remove_labels=[settings.label_pending]
                )
        
        summary = {
            "status": "complete",
            "message": f"Processed {processed_count} issues",
            "issues_processed": processed_count,
            "errors": errors if errors else None
        }
        
        self.log_activity("run_complete", f"Run complete. Processed {processed_count} issues.")
        return summary
    
    async def _process_issue(self, issue: Issue):
        """Process a single issue by starting a Devin session."""
        logger.info(f"Processing issue #{issue.fork_issue_number}: {issue.title}")
        
        # Update status to working
        issue.status = IssueStatus.WORKING
        self.db.commit()
        
        # Update GitHub labels
        self.github.update_issue_labels(
            issue.fork_issue_number,
            add_labels=[settings.label_working],
            remove_labels=[settings.label_pending]
        )
        
        # Build prompt for Devin
        repo_url = f"https://github.com/{settings.fork_repo}"
        prompt = self.devin.build_bug_fix_prompt(
            issue_title=issue.title,
            issue_body=issue.body or "No description provided.",
            repo_url=repo_url,
            issue_number=issue.fork_issue_number
        )
        
        # Create Devin session
        session = await self.devin.create_session(prompt=prompt, repo_url=repo_url)
        
        # Store session in database
        db_session = DevinSessionModel(
            session_id=session.session_id,
            session_url=session.url,
            issue_id=issue.id,
            status=SessionStatus.RUNNING
        )
        self.db.add(db_session)
        self.db.commit()
        
        self.log_activity(
            "session_created",
            f"Created Devin session {session.session_id} for issue #{issue.fork_issue_number}",
            issue_id=issue.id,
            session_id=session.session_id
        )
    
    async def check_sessions(self) -> dict:
        """
        Check status of all active Devin sessions.
        
        Returns:
            Summary of session statuses
        """
        active_sessions = self.db.query(DevinSessionModel).filter(
            DevinSessionModel.status.in_([SessionStatus.CREATED, SessionStatus.RUNNING])
        ).all()
        
        if not active_sessions:
            return {"status": "no_active_sessions", "checked": 0}
        
        completed = 0
        failed = 0
        
        for db_session in active_sessions:
            try:
                session = await self.devin.get_session(db_session.session_id)
                
                if self.devin.is_session_complete(session):
                    db_session.updated_at = datetime.utcnow()
                    db_session.completed_at = datetime.utcnow()
                    
                    issue = self.db.query(Issue).filter(Issue.id == db_session.issue_id).first()
                    
                    if self.devin.is_session_successful(session):
                        db_session.status = SessionStatus.COMPLETED
                        issue.status = IssueStatus.DONE
                        
                        # Try to get PR URL
                        if session.pull_request_url:
                            issue.pr_url = session.pull_request_url
                        
                        self.github.update_issue_labels(
                            issue.fork_issue_number,
                            add_labels=[settings.label_done],
                            remove_labels=[settings.label_working]
                        )
                        
                        completed += 1
                        self.log_activity(
                            "session_completed",
                            f"Devin session {db_session.session_id} completed successfully",
                            issue_id=issue.id,
                            session_id=db_session.session_id
                        )
                    else:
                        db_session.status = SessionStatus.FAILED
                        db_session.error_message = session.error
                        issue.status = IssueStatus.FAILED
                        
                        self.github.update_issue_labels(
                            issue.fork_issue_number,
                            add_labels=[settings.label_failed],
                            remove_labels=[settings.label_working]
                        )
                        
                        failed += 1
                        self.log_activity(
                            "session_failed",
                            f"Devin session {db_session.session_id} failed: {session.error}",
                            issue_id=issue.id,
                            session_id=db_session.session_id
                        )
                    
                    self.db.commit()
                    
            except Exception as e:
                logger.error(f"Error checking session {db_session.session_id}: {e}")
        
        return {
            "status": "checked",
            "total_checked": len(active_sessions),
            "completed": completed,
            "failed": failed
        }
    
    # ==================== TEARDOWN ====================
    
    def teardown(self) -> dict:
        """
        Reset Devin's work for the next demo run.
        
        This keeps issues intact but:
        - Closes Devin's PRs
        - Deletes Devin's branches
        - Resets issue labels back to pending
        - Clears session data (keeps issue records)
        
        Returns:
            Summary of teardown actions
        """
        logger.info("Starting teardown")
        self.log_activity("teardown_started", "Starting teardown - resetting Devin's work only")
        
        closed_prs = 0
        deleted_branches = []
        reset_issues = 0
        errors = []
        
        # 1. Close all open PRs (created by Devin)
        try:
            open_prs = self.github.get_open_pull_requests()
            for pr in open_prs:
                try:
                    self.github.close_pull_request(pr.number)
                    closed_prs += 1
                    
                    # Try to delete the branch
                    try:
                        self.github.delete_branch(pr.head.ref)
                        deleted_branches.append(pr.head.ref)
                    except Exception:
                        pass
                except Exception as e:
                    errors.append(f"Error closing PR #{pr.number}: {str(e)}")
        except Exception as e:
            errors.append(f"Error fetching PRs: {str(e)}")
        
        # 2. Reset issue labels back to pending (in GitHub)
        try:
            # Get issues that were worked on (working, done, or failed)
            for status_label in [settings.label_working, settings.label_done, settings.label_failed]:
                try:
                    issues = self.github.get_fork_issues_by_label(status_label)
                    for issue in issues:
                        try:
                            self.github.update_issue_labels(
                                issue.number,
                                add_labels=[settings.label_pending],
                                remove_labels=[settings.label_working, settings.label_done, settings.label_failed]
                            )
                            reset_issues += 1
                        except Exception as e:
                            errors.append(f"Error resetting labels on issue #{issue.number}: {str(e)}")
                except Exception:
                    pass  # Label might not exist yet
        except Exception as e:
            errors.append(f"Error resetting issue labels: {str(e)}")
        
        # 3. Reset issue status in database (keep issue records, just reset status)
        try:
            self.db.query(Issue).update({
                Issue.status: IssueStatus.PENDING,
                Issue.pr_number: None,
                Issue.pr_url: None,
                Issue.pr_merged: 0
            })
            self.db.commit()
        except Exception as e:
            errors.append(f"Error resetting issue status in DB: {str(e)}")
            self.db.rollback()
        
        # 4. Clear session data only (keep issues)
        try:
            self.db.query(DevinSessionModel).delete()
            self.db.commit()
        except Exception as e:
            errors.append(f"Error clearing sessions: {str(e)}")
            self.db.rollback()
        
        # 5. Clear old activity logs (optional - keep last 10 for context)
        try:
            # Keep recent activity, delete old ones
            recent_ids = [a.id for a in self.db.query(ActivityLog).order_by(
                ActivityLog.created_at.desc()
            ).limit(10).all()]
            
            if recent_ids:
                self.db.query(ActivityLog).filter(
                    ~ActivityLog.id.in_(recent_ids)
                ).delete(synchronize_session=False)
            self.db.commit()
        except Exception as e:
            errors.append(f"Error clearing old activity: {str(e)}")
            self.db.rollback()
        
        summary = {
            "status": "complete",
            "message": f"Teardown complete. Reset {reset_issues} issues to pending. Closed {closed_prs} PRs.",
            "reset_issues": reset_issues,
            "closed_prs": closed_prs,
            "deleted_branches": len(deleted_branches),
            "errors": errors if errors else None
        }
        
        self.log_activity("teardown_complete", summary["message"])
        
        return summary
    
    # ==================== STATUS ====================
    
    def get_status(self) -> dict:
        """Get current system status."""
        pending = self.db.query(Issue).filter(Issue.status == IssueStatus.PENDING).count()
        working = self.db.query(Issue).filter(Issue.status == IssueStatus.WORKING).count()
        done = self.db.query(Issue).filter(Issue.status == IssueStatus.DONE).count()
        failed = self.db.query(Issue).filter(Issue.status == IssueStatus.FAILED).count()
        
        total = pending + working + done + failed
        success_rate = (done / total * 100) if total > 0 else 0
        
        active_sessions = self.db.query(DevinSessionModel).filter(
            DevinSessionModel.status.in_([SessionStatus.CREATED, SessionStatus.RUNNING])
        ).count()
        
        recent_activity = self.db.query(ActivityLog).order_by(
            ActivityLog.created_at.desc()
        ).limit(10).all()
        
        return {
            "issues": {
                "pending": pending,
                "working": working,
                "done": done,
                "failed": failed,
                "total": total
            },
            "sessions": {
                "active": active_sessions,
                "max_concurrent": settings.max_concurrent_sessions
            },
            "metrics": {
                "success_rate": round(success_rate, 1),
                "prs_created": done  # Assuming done = PR created
            },
            "config": {
                "poll_interval_minutes": settings.poll_interval_minutes,
                "max_issues_per_poll": settings.max_issues_per_poll,
                "max_concurrent_sessions": settings.max_concurrent_sessions
            },
            "recent_activity": [
                {
                    "action": a.action,
                    "description": a.description,
                    "timestamp": a.created_at.isoformat()
                }
                for a in recent_activity
            ]
        }
