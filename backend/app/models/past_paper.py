from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class PastPaper(Base, TimestampMixin):
    __tablename__ = "past_papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False, index=True)
    programme_id: Mapped[str] = mapped_column(String(36), ForeignKey("programmes.id"), nullable=False, index=True)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)  # "2023/2024"
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_type: Mapped[str] = mapped_column(String(20), nullable=False, default="main")  # main | supplementary | cat
    file_reference: Mapped[str] = mapped_column(String(500), nullable=False)  # storage key/path
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
