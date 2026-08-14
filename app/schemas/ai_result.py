from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class AIScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_tools_skills: int = Field(strict=True, ge=0, le=10)
    portfolio_quality: int = Field(strict=True, ge=0, le=10)
    short_video_skills: int = Field(strict=True, ge=0, le=10)
    learning_new_ai: int = Field(strict=True, ge=0, le=10)
    content_discipline: int = Field(strict=True, ge=0, le=10)
    smm_understanding: int = Field(strict=True, ge=0, le=10)
    result_and_learning: int = Field(strict=True, ge=0, le=10)
    ai_content_automation_interest: int = Field(strict=True, ge=0, le=10)

    @computed_field
    @property
    def average_score(self) -> float:
        values = [
            self.ai_tools_skills,
            self.portfolio_quality,
            self.short_video_skills,
            self.learning_new_ai,
            self.content_discipline,
            self.smm_understanding,
            self.result_and_learning,
            self.ai_content_automation_interest,
        ]
        return round(sum(values) / len(values), 2)


class AIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str
    experience_summary: str
    experience_1_year: Literal["yes", "no", "unknown"]
    portfolio_status: Literal["yes", "no", "unknown"]
    portfolio_links: list[str]
    ai_tools: list[str]
    scores: AIScores
    strengths: list[str]
    missing_requirements: list[str]
    stop_factors: list[str]
    hr_summary: str
