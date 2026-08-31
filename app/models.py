"""Database models for tracking issues and Devin sessions."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class IssueStatus(str, enum.Enum):
    """Status of a tracked issue."""
    PENDING = "pending"
    WORKING = "working"
    DONE = "done"
    FAILED = "failed"


class SessionStatus(str, enum.Enum):
    """Status of a Devin session."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Issue(Base):
    """Represents a cloned issue from upstream."""
    
    __tablename__ = "issues"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Upstream issue info
    upstream_issue_number = Column(Integer, nullable=False)
    upstream_issue_url = Column(String(500), nullable=False)
    
    # Fork issue info
    fork_issue_number = Column(Integer, nullable=True)
    fork_issue_url = Column(String(500), nullable=True)
    
    # Issue details
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=True)
    
    # Status tracking
    status = Column(Enum(IssueStatus), default=IssueStatus.PENDING, nullable=False)
    
    # PR info (if created)
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String(500), nullable=True)
    pr_merged = Column(Integer, default=0)  # 0 = not merged, 1 = merged
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sessions = relationship("DevinSession", back_populates="issue")
    
    def __repr__(self):
        return f"<Issue #{self.fork_issue_number}: {self.title[:50]}>"


class DevinSession(Base):
    """Represents a Devin session for fixing an issue."""
    
    __tablename__ = "devin_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Devin session info
    session_id = Column(String(100), unique=True, nullable=False)
    session_url = Column(String(500), nullable=True)
    
    # Link to issue
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False)
    
    # Status
    status = Column(Enum(SessionStatus), default=SessionStatus.CREATED, nullable=False)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    issue = relationship("Issue", back_populates="sessions")
    
    def __repr__(self):
        return f"<DevinSession {self.session_id}: {self.status}>"


class ActivityLog(Base):
    """Audit log of system activities."""
    
    __tablename__ = "activity_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Activity info
    action = Column(String(50), nullable=False)  # setup, run, teardown, session_created, etc.
    description = Column(Text, nullable=False)
    
    # Related entities (optional)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=True)
    session_id = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ActivityLog {self.action}: {self.description[:50]}>"
