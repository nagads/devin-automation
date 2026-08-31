"""API endpoints for the orchestration system."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.orchestrator import Orchestrator
from app.services.scheduler import get_next_run_time
from app.models import Issue, DevinSession, ActivityLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["api"])


@router.post("/setup")
def setup(db: Session = Depends(get_db)):
    """Clone issues from upstream to fork."""
    try:
        orchestrator = Orchestrator(db)
        result = orchestrator.setup()
        return result
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run(db: Session = Depends(get_db)):
    """Manually trigger issue processing."""
    try:
        orchestrator = Orchestrator(db)
        
        # Check sessions first
        await orchestrator.check_sessions()
        
        # Process pending issues
        result = await orchestrator.run()
        return result
    except Exception as e:
        logger.error(f"Run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teardown")
def teardown(db: Session = Depends(get_db)):
    """Reset everything for next demo."""
    try:
        orchestrator = Orchestrator(db)
        result = orchestrator.teardown()
        return result
    except Exception as e:
        logger.error(f"Teardown failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Get current system status."""
    try:
        orchestrator = Orchestrator(db)
        status = orchestrator.get_status()
        
        # Add next poll time
        next_run = get_next_run_time()
        status["next_poll"] = next_run.isoformat() if next_run else None
        
        return status
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issues")
def list_issues(db: Session = Depends(get_db)):
    """List all tracked issues."""
    issues = db.query(Issue).order_by(Issue.created_at.desc()).all()
    
    result = []
    for i in issues:
        # Get the latest session for this issue
        session = db.query(DevinSession).filter(
            DevinSession.issue_id == i.id
        ).order_by(DevinSession.created_at.desc()).first()
        
        result.append({
            "id": i.id,
            "upstream_issue_number": i.upstream_issue_number,
            "upstream_issue_url": i.upstream_issue_url,
            "fork_issue_number": i.fork_issue_number,
            "fork_issue_url": i.fork_issue_url,
            "title": i.title,
            "status": i.status.value,
            "pr_url": i.pr_url,
            "pr_merged": bool(i.pr_merged),
            "devin_session_url": session.session_url if session else None,
            "created_at": i.created_at.isoformat(),
            "updated_at": i.updated_at.isoformat()
        })
    
    return result


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    """List all Devin sessions."""
    sessions = db.query(DevinSession).order_by(DevinSession.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "session_id": s.session_id,
            "session_url": s.session_url,
            "issue_id": s.issue_id,
            "status": s.status.value,
            "error_message": s.error_message,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    """Get details of a specific Devin session."""
    session = db.query(DevinSession).filter(DevinSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    issue = db.query(Issue).filter(Issue.id == session.issue_id).first()
    
    return {
        "id": session.id,
        "session_id": session.session_id,
        "session_url": session.session_url,
        "status": session.status.value,
        "error_message": session.error_message,
        "created_at": session.created_at.isoformat(),
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "issue": {
            "id": issue.id,
            "fork_issue_number": issue.fork_issue_number,
            "title": issue.title,
            "status": issue.status.value
        } if issue else None
    }


@router.get("/activity")
def get_activity(limit: int = 50, db: Session = Depends(get_db)):
    """Get recent activity log."""
    activities = db.query(ActivityLog).order_by(
        ActivityLog.created_at.desc()
    ).limit(limit).all()
    
    return [
        {
            "id": a.id,
            "action": a.action,
            "description": a.description,
            "issue_id": a.issue_id,
            "session_id": a.session_id,
            "created_at": a.created_at.isoformat()
        }
        for a in activities
    ]


@router.post("/check-sessions")
async def check_sessions(db: Session = Depends(get_db)):
    """Manually check status of active Devin sessions."""
    try:
        orchestrator = Orchestrator(db)
        result = await orchestrator.check_sessions()
        return result
    except Exception as e:
        logger.error(f"Session check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
