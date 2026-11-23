"""Strict Pydantic v2 schema for the 100-app Composio buildability audit."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

AuthMethod = Literal[
    "OAuth2",
    "API Key",
    "Bearer / PAT",
    "Basic Auth",
    "JWT / Service Account",
    "HMAC / Signed",
    "None (CLI / Local)",
]

AccessTier = Literal[
    "Self-Serve (Free / Trial)",
    "Self-Serve (Paid Plan Required)",
    "Sandbox Free, Prod Gated",
    "Partner / Sales-Gated",
    "No Public API / CLI-Only",
]

ApiSurface = Literal[
    "REST",
    "GraphQL",
    "REST + GraphQL",
    "gRPC / SDK-Only",
    "CLI-Only",
    "Undocumented / Private",
]

ApiBreadth = Literal[
    "Broad (Full CRUD / Webhooks)",
    "Medium (Core Resources)",
    "Narrow (Single Purpose / Read-Only)",
    "N/A (CLI / No API)",
]

ExistingMcp = Literal["Official MCP", "Community MCP", "None"]

BuildabilityVerdict = Literal[
    "Ship Today",
    "Ship with Caveats",
    "Skill / CLI Wrapper",
    "Blocked (Outreach Needed)",
]


class AppResearchRecord(BaseModel):
    id: int = Field(..., ge=1, le=100)
    name: str
    category: str
    hint_url: str
    one_liner: str = Field(..., description="Concise <=15 word description of what the app does.")
    auth_methods: list[AuthMethod]
    access_tier: AccessTier
    api_surface: ApiSurface
    api_breadth: ApiBreadth
    existing_mcp: ExistingMcp
    existing_mcp_url: Optional[str] = None
    buildability_verdict: BuildabilityVerdict
    main_blocker: str = Field(..., description="'None' if Ship Today; else concise main blocker.")
    evidence_urls: list[str] = Field(..., min_length=1, max_length=3)
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str


class CriticReview(BaseModel):
    has_discrepancy: bool
    corrected_record: Optional[AppResearchRecord] = None
    changed_fields: list[str] = Field(default_factory=list)
    reason: str
