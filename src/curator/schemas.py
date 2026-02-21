from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class CuratorTaskTemplateSchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    task_type: str
    scope: str
    recurrence_rule: Optional[dict] = None
    deadline_rule: Optional[dict] = None
    order_index: int = 0
    applicable_from_week: Optional[int] = None
    applicable_to_week: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CuratorTaskTemplateCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    task_type: str
    scope: str = "student"
    recurrence_rule: Optional[dict] = None
    deadline_rule: Optional[dict] = None
    order_index: int = 0
    applicable_from_week: Optional[int] = None
    applicable_to_week: Optional[int] = None


class CuratorTaskInstanceSchema(BaseModel):
    id: int
    template_id: int
    template_title: Optional[str] = None
    template_description: Optional[str] = None
    task_type: Optional[str] = None
    scope: Optional[str] = None
    curator_id: int
    curator_name: Optional[str] = None
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    status: str
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_text: Optional[str] = None
    screenshot_url: Optional[str] = None
    week_reference: Optional[str] = None
    program_week: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CuratorTaskInstanceUpdateSchema(BaseModel):
    status: Optional[str] = None
    result_text: Optional[str] = None
    screenshot_url: Optional[str] = None
