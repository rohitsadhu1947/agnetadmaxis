"""
Cohort Classification Engine — Agent segmentation, scoring, and engagement strategy.

Classifies agents into 16 named segments based on 9 axes of analysis.
Computes reactivation probability score (0-100) and decides engagement strategy.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from domain.enums import (
    CohortSegment, EngagementStrategy, CareerStage, MarketTier, WorkType,
    DormancyReasonCategory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metro / Tier classification for Indian cities
# ---------------------------------------------------------------------------
METRO_CITIES = {
    "mumbai", "delhi", "new delhi", "bangalore", "bengaluru", "chennai",
    "hyderabad", "kolkata", "pune", "ahmedabad",
}
TIER_2_CITIES = {
    "jaipur", "lucknow", "chandigarh", "kochi", "coimbatore", "surat",
    "nagpur", "nashik", "vadodara", "indore", "bhopal", "visakhapatnam",
    "gurgaon", "gurugram", "noida", "thane", "mysore", "mysuru",
    "thiruvananthapuram", "guwahati", "patna", "ranchi", "bhubaneswar",
    "dehradun", "agra", "amritsar", "goa",
}

# Dormancy reasons that are recoverable (operational / system issues)
RECOVERABLE_DORMANCY_PREFIXES = [
    "operational.", "training_gap.", "engagement_gap.",
]
LOW_RECOVERY_DORMANCY_PREFIXES = [
    "personal.lost_interest", "personal.other_employment",
    "economic.competitor_better_commission",
]

# ---------------------------------------------------------------------------
# Segment display names & descriptions
# ---------------------------------------------------------------------------
SEGMENT_INFO = {
    CohortSegment.PROMISING_ROOKIES: {
        "display": "Promising Rookies",
        "description": "New agents (<1yr) showing early signs of activity and responsiveness",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.STALLED_STARTERS: {
        "display": "Stalled Starters",
        "description": "Licensed but zero sales, stuck early in the pipeline",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.SLEEPING_GIANTS: {
        "display": "Sleeping Giants",
        "description": "High historical performance, recently gone dormant",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.FADING_STARS: {
        "display": "Fading Stars",
        "description": "Declining trajectory but still some recent activity",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.WEEKEND_WARRIORS: {
        "display": "Weekend Warriors",
        "description": "Part-time agents with sporadic but real activity",
        "strategy": EngagementStrategy.WHATSAPP_FIRST,
    },
    CohortSegment.ECONOMIC_DEFECTORS: {
        "display": "Economic Defectors",
        "description": "Left or considering leaving for better commissions elsewhere",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.SYSTEM_FRUSTRATED: {
        "display": "System Frustrated",
        "description": "Dormant primarily due to operational / tech issues",
        "strategy": EngagementStrategy.WHATSAPP_FIRST,
    },
    CohortSegment.ABANDONED_BY_ADM: {
        "display": "Abandoned by ADM",
        "description": "Never or rarely contacted by their assigned ADM",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.CHRONIC_NEVER_ACTIVATORS: {
        "display": "Chronic Never-Activators",
        "description": "Licensed 1+ year with zero sales ever",
        "strategy": EngagementStrategy.TELEGRAM_ONLY,
    },
    CohortSegment.LIFE_EVENT_PAUSED: {
        "display": "Life-Event Paused",
        "description": "Dormant due to health, family, or relocation",
        "strategy": EngagementStrategy.WHATSAPP_FIRST,
    },
    CohortSegment.REGULATORY_BLOCKED: {
        "display": "Regulatory Blocked",
        "description": "License expired or compliance issue preventing activity",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.DIGITAL_ORPHANS: {
        "display": "Digital Orphans",
        "description": "Low digital savviness, rural/semi-urban, need offline engagement",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.HIGH_POTENTIAL_UNPOLISHED: {
        "display": "High-Potential Unpolished",
        "description": "Good market context but lacking skills/training",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.COMPETITOR_POACHED: {
        "display": "Competitor Poached",
        "description": "Known to be active with a competitor insurer",
        "strategy": EngagementStrategy.DIRECT_CALL,
    },
    CohortSegment.SATISFIED_PASSIVES: {
        "display": "Satisfied Passives",
        "description": "Low effort but occasional sales, content with status quo",
        "strategy": EngagementStrategy.WHATSAPP_FIRST,
    },
    CohortSegment.LOST_CAUSES: {
        "display": "Lost Causes",
        "description": "No response for 1+ year, zero activity, unrecoverable",
        "strategy": EngagementStrategy.NO_CONTACT,
    },
}

# First message templates per segment (bilingual — Hindi/English)
FIRST_MESSAGE_TEMPLATES = {
    CohortSegment.PROMISING_ROOKIES: (
        "{name} ji, aapne Axis Max Life ke saath ek achhi shuruaat ki hai! "
        "Hum aapki journey mein madad karna chahte hain. "
        "Kya hum aapke liye ek training session schedule kar sakte hain?"
    ),
    CohortSegment.STALLED_STARTERS: (
        "{name} ji, humne dekha ki aapne abhi tak apni pehli policy sell nahi ki. "
        "Kya koi specific challenge hai jisme hum help kar sakte hain? "
        "Aapke liye ek dedicated support plan hai."
    ),
    CohortSegment.SLEEPING_GIANTS: (
        "{name} ji, aapka track record bahut achha raha hai. "
        "Hum aapko miss kar rahe hain! Kya sab theek hai? "
        "Aapke liye kuch exciting new products aaye hain."
    ),
    CohortSegment.FADING_STARS: (
        "{name} ji, aapke recent performance mein hum kuch changes notice kar rahe hain. "
        "Kya koi issue hai jisme hum madad kar sakte hain? "
        "Aap humare valuable partner hain."
    ),
    CohortSegment.WEEKEND_WARRIORS: (
        "{name} ji, aapka part-time contribution bhi bahut important hai. "
        "Hum aapke schedule ke hisaab se flexible support de sakte hain. "
        "Kya weekend mein ek short call ho sakti hai?"
    ),
    CohortSegment.ECONOMIC_DEFECTORS: (
        "{name} ji, hum samajhte hain ki commission structure important hai. "
        "Humne recently kuch changes kiye hain jo aapke liye beneficial ho sakte hain. "
        "Kya hum ek quick discussion kar sakte hain?"
    ),
    CohortSegment.SYSTEM_FRUSTRATED: (
        "{name} ji, humne suna ki aapko kuch system issues face karne pade. "
        "Hum is par kaam kar rahe hain aur aapki feedback bahut zaroori hai. "
        "Kya hum aapki problem solve kar sakte hain?"
    ),
    CohortSegment.ABANDONED_BY_ADM: (
        "{name} ji, main aapka naya point of contact hoon. "
        "Humein pata hai ki pehle proper support nahi mila, lekin ab hum committed hain. "
        "Kya aaj ek introductory call ho sakti hai?"
    ),
    CohortSegment.CHRONIC_NEVER_ACTIVATORS: (
        "{name} ji, aapne Axis Max Life ke saath apna license liya tha. "
        "Hum aapko first sale mein madad karna chahte hain. "
        "Kya aap interested hain ek guided selling session mein?"
    ),
    CohortSegment.LIFE_EVENT_PAUSED: (
        "{name} ji, hum umeed karte hain sab theek hai aapke saath. "
        "Jab bhi aap ready hon, hum yahan hain aapki madad ke liye. "
        "Koi rush nahi hai — bas ek check-in tha."
    ),
    CohortSegment.REGULATORY_BLOCKED: (
        "{name} ji, humne dekha ki aapke license/compliance mein kuch update chahiye. "
        "Hum is process mein aapki puri madad karenge. "
        "Kya hum details share kar sakte hain?"
    ),
    CohortSegment.DIGITAL_ORPHANS: (
        "{name} ji, aapko Axis Max Life ke tools use karne mein koi dikkat aa rahi hai? "
        "Hum aapko step-by-step guide de sakte hain ya in-person training arrange kar sakte hain."
    ),
    CohortSegment.HIGH_POTENTIAL_UNPOLISHED: (
        "{name} ji, aapke area mein bahut potential hai. "
        "Ek focused training session se aap apni selling skills aur improve kar sakte hain. "
        "Kya hum schedule karein?"
    ),
    CohortSegment.COMPETITOR_POACHED: (
        "{name} ji, hum jaante hain ki aapke paas options hain. "
        "Lekin Axis Max Life mein kuch naye opportunities aaye hain jo aapko pasand aayenge. "
        "Kya 5 minutes ke liye baat ho sakti hai?"
    ),
    CohortSegment.SATISFIED_PASSIVES: (
        "{name} ji, aapka contribution appreciated hai. "
        "Kya aap apni income thodi aur badhana chahenge? "
        "Humare paas kuch easy-sell products hain jo aapke customers ko suit karenge."
    ),
    CohortSegment.LOST_CAUSES: "",  # No outreach
}


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of reactivation score components."""
    historical_performance: float = 0.0   # 0-25
    responsiveness: float = 0.0           # 0-25
    market_potential: float = 0.0         # 0-15
    time_decay: float = 0.0              # 0-15
    reason_recoverability: float = 0.0    # 0-10
    demographics: float = 0.0            # 0-10

    @property
    def total(self) -> float:
        return (
            self.historical_performance + self.responsiveness +
            self.market_potential + self.time_decay +
            self.reason_recoverability + self.demographics
        )

    def to_dict(self) -> dict:
        return {
            "historical_performance": round(self.historical_performance, 1),
            "responsiveness": round(self.responsiveness, 1),
            "market_potential": round(self.market_potential, 1),
            "time_decay": round(self.time_decay, 1),
            "reason_recoverability": round(self.reason_recoverability, 1),
            "demographics": round(self.demographics, 1),
            "total": round(self.total, 1),
        }


@dataclass
class CohortResult:
    """Full classification result for an agent."""
    agent_id: int
    agent_name: str
    cohort_segment: str
    reactivation_score: float
    engagement_strategy: str
    churn_risk_level: str
    score_breakdown: dict
    first_message: str = ""
    reasoning: dict = None

    def __post_init__(self):
        if self.reasoning is None:
            self.reasoning = {}


class CohortClassifier:
    """Classifies agents into cohort segments with reactivation scoring."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_agent(self, agent) -> CohortResult:
        """Classify a single agent: determine segment, score, and strategy."""
        score_breakdown = self._compute_score_breakdown(agent)
        total_score = score_breakdown.total
        segment = self._determine_segment(agent, score_breakdown)
        strategy = self._decide_strategy(segment, total_score)
        risk = self._determine_risk(total_score, segment)

        first_msg = ""
        template = FIRST_MESSAGE_TEMPLATES.get(segment, "")
        if template:
            first_msg = template.format(name=agent.name)

        reasoning = self._build_reasoning(agent, segment, score_breakdown, strategy)

        return CohortResult(
            agent_id=agent.id,
            agent_name=agent.name,
            cohort_segment=segment.value,
            reactivation_score=round(total_score, 1),
            engagement_strategy=strategy.value,
            churn_risk_level=risk,
            score_breakdown=score_breakdown.to_dict(),
            first_message=first_msg,
            reasoning=reasoning,
        )

    def bulk_classify(self, agents: list) -> List[CohortResult]:
        """Classify a batch of agents."""
        results = []
        for agent in agents:
            try:
                result = self.classify_agent(agent)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to classify agent {agent.id}: {e}")
        return results

    def apply_classification(self, agent, result: CohortResult) -> None:
        """Write classification result back to the Agent model."""
        agent.cohort_segment = result.cohort_segment
        agent.reactivation_score = result.reactivation_score
        agent.engagement_strategy = result.engagement_strategy
        agent.churn_risk_level = result.churn_risk_level

    # ------------------------------------------------------------------
    # Score computation (6 sub-scores, total 0-100)
    # ------------------------------------------------------------------

    def _compute_score_breakdown(self, agent) -> ScoreBreakdown:
        breakdown = ScoreBreakdown()

        # 1. Historical Performance (0-25)
        breakdown.historical_performance = self._score_historical(agent)

        # 2. Responsiveness (0-25)
        breakdown.responsiveness = self._score_responsiveness(agent)

        # 3. Market Potential (0-15)
        breakdown.market_potential = self._score_market(agent)

        # 4. Time Decay (0-15)
        breakdown.time_decay = self._score_time_decay(agent)

        # 5. Reason Recoverability (0-10)
        breakdown.reason_recoverability = self._score_recoverability(agent)

        # 6. Demographics (0-10)
        breakdown.demographics = self._score_demographics(agent)

        return breakdown

    def _score_historical(self, agent) -> float:
        """Historical performance: 0-25 pts.  Proportional scaling."""
        score = 0.0
        # Total policies sold (0-10) — linear: 0→0, 20+→10
        policies = agent.total_policies_sold or 0
        score += min(policies / 20.0, 1.0) * 10.0

        # Recent activity — policies last 12 months (0-8) — linear: 0→0, 5+→8
        recent = agent.policies_last_12_months or 0
        score += min(recent / 5.0, 1.0) * 8.0

        # Persistency ratio (0-7) — linear: 0→0, 1.0→7
        persistency = agent.persistency_ratio or 0.0
        score += min(persistency, 1.0) * 7.0

        return min(score, 25.0)

    def _score_responsiveness(self, agent) -> float:
        """Responsiveness: 0-25 pts.  Proportional scaling."""
        score = 0.0

        # Response rate (0-15) — linear: 0→0, 1.0→15
        rate = agent.response_rate or 0.0
        score += min(rate, 1.0) * 15.0

        # Recency of last contact (0-10) — inverse decay over 365 days
        if agent.last_contact_date:
            days_since = (date.today() - agent.last_contact_date).days
            if days_since <= 0:
                score += 10.0
            elif days_since >= 365:
                score += 0.0
            else:
                score += 10.0 * (1.0 - days_since / 365.0)

        return min(score, 25.0)

    def _score_market(self, agent) -> float:
        """Market potential based on location tier: 0-15 pts."""
        tier = self._get_market_tier(agent.location)
        score = 0.0

        # Location tier (0-8) — categorical is fine here
        tier_scores = {
            MarketTier.TIER_2: 8,    # Highest untapped potential
            MarketTier.METRO: 7,
            MarketTier.SEMI_URBAN: 5,
            MarketTier.RURAL: 3,
        }
        score += tier_scores.get(tier, 4)

        # Avg ticket size (0-7) — linear: 0→0, 50000+→7
        ticket = agent.avg_ticket_size or 0.0
        score += min(ticket / 50000.0, 1.0) * 7.0

        return min(score, 15.0)

    def _score_time_decay(self, agent) -> float:
        """Time decay — inverse of dormancy duration: 0-15 pts.

        0 dormancy days means the field was not provided (unknown) — gets
        a moderate default (7).  Genuinely active agents are detected by
        lifecycle_state = 'active' and get full score.
        """
        days = agent.dormancy_duration_days or 0
        lifecycle = (agent.lifecycle_state or "").lower()

        if days == 0:
            # If lifecycle is active, they are truly not dormant
            if lifecycle == "active":
                return 15.0
            # Otherwise 0 means "not provided" — give moderate score
            return 7.0

        # Inverse linear decay: 1 day → ~15, 365+ days → 1
        if days >= 365:
            return 1.0
        return 15.0 * (1.0 - days / 365.0)

    def _score_recoverability(self, agent) -> float:
        """Dormancy reason recoverability: 0-10 pts."""
        reason = agent.dormancy_reason or ""
        if not reason:
            return 5.0  # Unknown — moderate

        # Recoverable reasons (operational, training, engagement gaps)
        for prefix in RECOVERABLE_DORMANCY_PREFIXES:
            if reason.startswith(prefix):
                return 9.0

        # Low recovery reasons
        for prefix in LOW_RECOVERY_DORMANCY_PREFIXES:
            if reason.startswith(prefix):
                return 2.0

        # Regulatory — recoverable if facilitated
        if reason.startswith("regulatory."):
            return 7.0

        # Personal (health, family, relocation) — moderate
        if reason.startswith("personal."):
            return 4.0

        # Economic — depends
        if reason.startswith("economic."):
            return 5.0

        return 5.0

    def _score_demographics(self, agent) -> float:
        """Demographics score: 0-10 pts."""
        score = 0.0

        # Career stage (0-4)
        stage = self._get_career_stage(agent)
        stage_scores = {
            CareerStage.DEVELOPING: 4,  # Sweet spot — enough experience, still engaged
            CareerStage.ROOKIE: 3,
            CareerStage.EXPERIENCED: 2,  # Harder to re-engage
        }
        score += stage_scores.get(stage, 1)

        # Education (0-3)
        edu = (agent.education_level or "").lower()
        edu_scores = {
            "post_graduate": 3, "professional": 3, "graduate": 3,
            "12th": 2, "intermediate": 2, "diploma": 2,
        }
        score += edu_scores.get(edu, 1 if edu else 0)

        # Age factor (0-3) — bell curve around 25-45
        age = agent.age or 0
        if age == 0:
            score += 1.5  # Unknown — moderate
        elif 25 <= age <= 45:
            score += 3.0
        elif 22 <= age < 25 or 45 < age <= 55:
            score += 2.0
        else:
            score += 1.0

        return min(score, 10.0)

    # ------------------------------------------------------------------
    # Segment determination
    # ------------------------------------------------------------------

    def _determine_segment(self, agent, breakdown: ScoreBreakdown) -> CohortSegment:
        """Determine the best-fit segment based on agent attributes."""
        reason = (agent.dormancy_reason or "").lower()
        stage = self._get_career_stage(agent)
        tier = self._get_market_tier(agent.location)
        total = breakdown.total

        # --- Priority checks (specific signals override general scoring) ---

        # Regulatory blocked
        if reason.startswith("regulatory."):
            return CohortSegment.REGULATORY_BLOCKED

        # Competitor poached
        if (reason.startswith("economic.competitor") or
                (agent.is_poached and agent.previous_insurer)):
            return CohortSegment.COMPETITOR_POACHED

        # Life-event paused
        if reason.startswith("personal.health") or reason.startswith("personal.relocated") or reason.startswith("personal.family"):
            return CohortSegment.LIFE_EVENT_PAUSED

        # System frustrated (operational issues)
        if reason.startswith("operational."):
            return CohortSegment.SYSTEM_FRUSTRATED

        # Abandoned by ADM
        if (reason.startswith("engagement_gap.adm_never_contacted") or
                reason.startswith("engagement_gap.adm_no_followthrough")):
            if agent.contact_attempts == 0:
                return CohortSegment.ABANDONED_BY_ADM

        # --- Score + attribute based segments ---
        dormancy = agent.dormancy_duration_days or 0

        # Lost causes: dormant 1yr+, zero activity, no response
        if (dormancy > 365 and
                (agent.total_policies_sold or 0) == 0 and
                (agent.response_rate or 0) == 0):
            return CohortSegment.LOST_CAUSES

        # Sleeping giants: high historical, recently dormant (within 6 months)
        if ((agent.total_policies_sold or 0) >= 10 and
                breakdown.historical_performance >= 12 and
                0 < dormancy <= 180):
            return CohortSegment.SLEEPING_GIANTS

        # Fading stars: declining but still some recent activity
        if ((agent.total_policies_sold or 0) >= 5 and
                (agent.policies_last_12_months or 0) >= 1 and
                agent.policies_last_12_months < (agent.total_policies_sold or 0) / max(agent.years_in_insurance or 1, 1)):
            return CohortSegment.FADING_STARS

        # Economic defectors
        if reason.startswith("economic."):
            return CohortSegment.ECONOMIC_DEFECTORS

        # Chronic never-activators: licensed 1yr+ but 0 sales
        if (stage != CareerStage.ROOKIE and
                agent.total_policies_sold == 0 and
                agent.years_in_insurance >= 1):
            return CohortSegment.CHRONIC_NEVER_ACTIVATORS

        # Promising rookies: < 1yr, some positive signals
        if stage == CareerStage.ROOKIE:
            if agent.total_policies_sold >= 1 or (agent.response_rate or 0) > 0.3:
                return CohortSegment.PROMISING_ROOKIES
            else:
                return CohortSegment.STALLED_STARTERS

        # Weekend warriors: part-time with some activity
        if agent.work_type in ("part_time", "side_hustle"):
            if agent.total_policies_sold >= 1:
                return CohortSegment.WEEKEND_WARRIORS

        # Digital orphans: low digital score, rural/semi-urban
        if (agent.digital_savviness_score <= 3 and
                tier in (MarketTier.RURAL, MarketTier.SEMI_URBAN)):
            return CohortSegment.DIGITAL_ORPHANS

        # High potential unpolished: good market but lacking training
        if (tier in (MarketTier.METRO, MarketTier.TIER_2) and
                reason.startswith("training_gap.")):
            return CohortSegment.HIGH_POTENTIAL_UNPOLISHED

        # Satisfied passives: some sales, low effort, not long dormant
        if ((agent.total_policies_sold or 0) >= 1 and
                breakdown.responsiveness <= 8 and
                dormancy <= 180):
            return CohortSegment.SATISFIED_PASSIVES

        # Abandoned by ADM (fallback for engagement gap)
        if reason.startswith("engagement_gap."):
            return CohortSegment.ABANDONED_BY_ADM

        # Default based on score
        if total >= 50:
            return CohortSegment.FADING_STARS
        elif total >= 30:
            return CohortSegment.STALLED_STARTERS
        elif total >= 15:
            return CohortSegment.CHRONIC_NEVER_ACTIVATORS
        else:
            return CohortSegment.LOST_CAUSES

    # ------------------------------------------------------------------
    # Strategy & risk
    # ------------------------------------------------------------------

    def _decide_strategy(self, segment: CohortSegment, score: float) -> EngagementStrategy:
        """Decide engagement strategy based on segment default with score-based adjustments.

        The segment's recommended strategy is primary.  Score only downgrades
        the channel for very low scores (don't waste calls on lost causes) or
        upgrades for very low-contact segments with unexpectedly high scores.
        """
        default = SEGMENT_INFO[segment]["strategy"]

        # Lost causes — never contact
        if segment == CohortSegment.LOST_CAUSES:
            return EngagementStrategy.NO_CONTACT

        # Very low score (<15) — downgrade to no contact regardless of segment
        if score < 15:
            return EngagementStrategy.NO_CONTACT

        # Low score (15-29) — cap at telegram only
        if score < 30:
            if default in (EngagementStrategy.NO_CONTACT, EngagementStrategy.TELEGRAM_ONLY):
                return default
            return EngagementStrategy.TELEGRAM_ONLY

        # Medium score (30-54) — cap at whatsapp
        if score < 55:
            if default == EngagementStrategy.DIRECT_CALL:
                return EngagementStrategy.WHATSAPP_FIRST
            return default

        # High score (55+) — use segment default (which may be call, whatsapp, etc.)
        return default

    def _determine_risk(self, score: float, segment: CohortSegment) -> str:
        """Determine churn risk level."""
        if segment == CohortSegment.LOST_CAUSES:
            return "lost"
        if score >= 60:
            return "low"
        elif score >= 35:
            return "medium"
        else:
            return "high"

    # ------------------------------------------------------------------
    # Classification Reasoning Engine
    # ------------------------------------------------------------------

    def _build_reasoning(self, agent, segment: CohortSegment,
                         breakdown: ScoreBreakdown,
                         strategy: EngagementStrategy) -> dict:
        """Build a rich, segment-specific reasoning dict explaining *why*
        this agent was classified into the given segment and what the ADM
        should do about it.

        Returns a dict with five keys:
            classification_reasons  – 2-4 sentences explaining the segment fit
            key_factors             – top 3-4 data points that drove the decision
            risk_signals            – concerning patterns
            opportunities           – positive signals
            recommended_actions     – 2-3 concrete next steps for the ADM
        """
        # ----- gather raw data safely --------------------------------
        policies = agent.total_policies_sold or 0
        recent_policies = agent.policies_last_12_months or 0
        premium = agent.total_premium_generated or 0.0
        recent_premium = agent.premium_last_12_months or 0.0
        persistency = agent.persistency_ratio or 0.0
        dormancy = agent.dormancy_duration_days or 0
        days_inactive = agent.days_since_last_activity or 0
        response_rate = agent.response_rate or 0.0
        contact_attempts = agent.contact_attempts or 0
        contact_responses = agent.contact_responses or 0
        digital_score = agent.digital_savviness_score or 0.0
        age = agent.age or 0
        years = agent.years_in_insurance or 0.0
        education = (agent.education_level or "unknown").replace("_", " ").title()
        work_type = (agent.work_type or "full_time").replace("_", " ").title()
        location = agent.location or "Unknown"
        reason = agent.dormancy_reason or ""
        avg_ticket = agent.avg_ticket_size or 0.0
        best_month = agent.best_month_premium or 0.0
        has_app = agent.has_app_installed or False
        preferred_channel = agent.preferred_channel or "unknown"
        avg_response_hrs = agent.avg_response_time_hours
        tier = self._get_market_tier(location)
        stage = self._get_career_stage(agent)
        total_score = round(breakdown.total, 1)

        # ----- helpers ------------------------------------------------
        def _fmt_premium(val: float) -> str:
            if val >= 100_000:
                return f"Rs {val / 100_000:.1f}L"
            if val >= 1_000:
                return f"Rs {val / 1_000:.1f}K"
            return f"Rs {val:.0f}"

        def _dormancy_label(d: int) -> str:
            if d <= 30:
                return f"{d} days (very recent)"
            if d <= 90:
                return f"{d} days (~{d // 30} months)"
            if d <= 365:
                return f"{d} days (~{d // 30} months)"
            return f"{d} days ({d // 365}yr {(d % 365) // 30}mo)"

        def _response_pct(r: float) -> str:
            return f"{r * 100:.0f}%"

        # ----- build key_factors (always present) ---------------------
        key_factors = []

        key_factors.append({
            "factor": "Total Policies Sold",
            "value": str(policies),
            "impact": "positive" if policies >= 5 else ("neutral" if policies >= 1 else "negative"),
        })

        key_factors.append({
            "factor": "Dormancy Duration",
            "value": _dormancy_label(dormancy),
            "impact": "positive" if dormancy <= 60 else ("neutral" if dormancy <= 180 else "negative"),
        })

        key_factors.append({
            "factor": "Response Rate",
            "value": _response_pct(response_rate),
            "impact": "positive" if response_rate >= 0.5 else ("neutral" if response_rate >= 0.2 else "negative"),
        })

        if recent_policies > 0 or policies > 0:
            key_factors.append({
                "factor": "Policies Last 12 Months",
                "value": str(recent_policies),
                "impact": "positive" if recent_policies >= 3 else ("neutral" if recent_policies >= 1 else "negative"),
            })

        if persistency > 0:
            key_factors.append({
                "factor": "Persistency Ratio",
                "value": f"{persistency * 100:.0f}%",
                "impact": "positive" if persistency >= 0.7 else ("neutral" if persistency >= 0.4 else "negative"),
            })

        # Cap at 4 factors
        key_factors = key_factors[:4]

        # ----- build risk_signals & opportunities globally first ------
        risk_signals = []
        opportunities = []

        # ---- risk signals (data-driven) ----
        if dormancy > 200:
            risk_signals.append(f"Dormant for {dormancy} days — deep disengagement window")
        if dormancy > 365:
            risk_signals.append(f"Dormancy exceeds 1 year ({dormancy} days) — very high churn probability")
        if contact_attempts > 0 and contact_responses == 0:
            risk_signals.append(f"Zero responses to {contact_attempts} contact attempt(s)")
        if contact_attempts >= 5 and response_rate < 0.1:
            risk_signals.append(f"Very low response rate ({_response_pct(response_rate)}) despite {contact_attempts} attempts")
        if policies == 0 and years >= 1:
            risk_signals.append(f"Zero policies sold despite {years:.1f} years since onboarding")
        if recent_policies == 0 and policies >= 3:
            risk_signals.append("No policies in last 12 months despite historical track record")
        if not has_app and digital_score <= 2:
            risk_signals.append(f"No app installed and low digital savviness ({digital_score}/10)")
        if reason.startswith("personal.lost_interest"):
            risk_signals.append("Dormancy reason: agent has lost interest in insurance selling")
        if reason.startswith("personal.other_employment"):
            risk_signals.append("Agent has taken up alternative employment")
        if reason.startswith("economic.competitor"):
            risk_signals.append("Agent attracted by competitor commission structure")
        if reason.startswith("regulatory.license_expired"):
            risk_signals.append("License has expired — cannot sell until renewed")

        # ---- opportunities (data-driven) ----
        if persistency >= 0.7:
            opportunities.append(f"High persistency ratio ({persistency * 100:.0f}%) — strong customer relationships")
        if tier == MarketTier.TIER_2:
            opportunities.append(f"Located in high-potential Tier 2 market ({location})")
        elif tier == MarketTier.METRO:
            opportunities.append(f"Metro market location ({location}) with dense customer base")
        if response_rate >= 0.5:
            opportunities.append(f"Good response rate ({_response_pct(response_rate)}) — agent is reachable")
        if digital_score >= 7:
            opportunities.append(f"High digital savviness ({digital_score}/10) — can leverage digital tools")
        if has_app and digital_score >= 5:
            opportunities.append("App installed and digitally capable — ready for digital engagement")
        if 25 <= age <= 40:
            opportunities.append(f"Prime selling age ({age}) with long career runway")
        if education in ("Graduate", "Post Graduate", "Professional"):
            opportunities.append(f"Well-educated ({education}) — can handle complex products")
        if best_month > 0:
            opportunities.append(f"Proven peak capacity: best month premium was {_fmt_premium(best_month)}")
        if avg_ticket > 20000:
            opportunities.append(f"High average ticket size ({_fmt_premium(avg_ticket)}) — quality over quantity seller")
        if dormancy <= 60 and policies >= 1:
            opportunities.append(f"Only {dormancy} days dormant — strong recovery window")
        if recent_policies >= 3:
            opportunities.append(f"Still active recently with {recent_policies} policies in last 12 months")
        if stage == CareerStage.DEVELOPING:
            opportunities.append(f"In developing career stage ({years:.0f} yrs) — high coaching ROI")
        if work_type == "Part Time" or work_type == "Side Hustle":
            if policies >= 1:
                opportunities.append(f"Producing despite being {work_type} — potential for more with incentives")
        if reason.startswith("operational.") or reason.startswith("training_gap."):
            opportunities.append("Dormancy cause is addressable (operational/training) — fixable with intervention")

        # ----- segment-specific classification_reasons ----------------
        classification_reasons = []
        recommended_actions = []

        seg = segment  # alias for brevity

        if seg == CohortSegment.SLEEPING_GIANTS:
            classification_reasons.append(
                f"Previously high-performing agent with {policies} lifetime policies "
                f"and {_fmt_premium(premium)} total premium generated."
            )
            classification_reasons.append(
                f"Only dormant for {dormancy} days — recovery window is "
                f"{'strong' if dormancy <= 90 else 'moderate'}."
            )
            classification_reasons.append(
                f"Historical performance score ({breakdown.historical_performance:.0f}/25) "
                f"indicates {'strong' if breakdown.historical_performance >= 15 else 'solid'} sales capability."
            )
            if persistency >= 0.6:
                classification_reasons.append(
                    f"Persistency ratio of {persistency * 100:.0f}% shows loyal customer base that can be re-activated."
                )
            recommended_actions = [
                "Schedule a personal 1-on-1 call within 48 hours to understand the dormancy reason",
                f"Share latest commission structure and new product launches relevant to {location} market",
                "Offer a reactivation incentive — e.g., bonus on first 2 policies within 30 days",
            ]

        elif seg == CohortSegment.LOST_CAUSES:
            classification_reasons.append(
                f"No policies sold in {dormancy}+ days of enrollment."
            )
            if contact_attempts > 0:
                classification_reasons.append(
                    f"Zero response rate to {contact_attempts} contact attempt(s) — "
                    f"agent is unreachable or disengaged."
                )
            else:
                classification_reasons.append(
                    "No contact attempts recorded — agent was never properly engaged."
                )
            classification_reasons.append(
                f"Reactivation score of {total_score}/100 is well below recovery threshold."
            )
            classification_reasons.append(
                "High dormancy with no positive engagement signals — reactivation is not cost-effective."
            )
            recommended_actions = [
                "Deprioritize from active outreach — move to passive monitoring list",
                "Send one final low-cost Telegram message offering re-engagement",
                "Reallocate ADM bandwidth to higher-potential agents",
            ]

        elif seg == CohortSegment.PROMISING_ROOKIES:
            classification_reasons.append(
                f"New agent (< 1 year, {years:.1f} yrs) showing early positive signals."
            )
            if policies >= 1:
                classification_reasons.append(
                    f"Already sold {policies} policy(ies) — demonstrates ability to convert."
                )
            if response_rate > 0.3:
                classification_reasons.append(
                    f"Response rate of {_response_pct(response_rate)} indicates willingness to engage."
                )
            classification_reasons.append(
                f"Located in {tier.value.replace('_', ' ').title()} market ({location}) "
                f"with {'strong' if tier in (MarketTier.METRO, MarketTier.TIER_2) else 'moderate'} demand."
            )
            recommended_actions = [
                "Assign a buddy/mentor from the top-performing agents in the region",
                "Schedule weekly check-in calls for the first 90 days",
                "Send product training content via WhatsApp — start with term life basics",
            ]

        elif seg == CohortSegment.STALLED_STARTERS:
            classification_reasons.append(
                f"Licensed for {years:.1f} years but has not made a first sale yet."
            )
            if response_rate > 0:
                classification_reasons.append(
                    f"Some responsiveness ({_response_pct(response_rate)}) — agent is reachable but struggling to convert."
                )
            else:
                classification_reasons.append(
                    "No response to outreach attempts — may need a different engagement approach."
                )
            if reason:
                reason_label = reason.replace(".", " > ").replace("_", " ").title()
                classification_reasons.append(
                    f"Dormancy reason: {reason_label}."
                )
            recommended_actions = [
                "Schedule an in-person or video training session focused on first-sale techniques",
                "Pair with a successful agent in the same city for joint field visits",
                "Share simplified sales scripts and objection-handling guides via WhatsApp",
            ]

        elif seg == CohortSegment.FADING_STARS:
            yearly_avg = policies / max(years, 1)
            classification_reasons.append(
                f"Agent has {policies} lifetime policies but trajectory is declining — "
                f"only {recent_policies} in last 12 months vs historical avg of {yearly_avg:.1f}/year."
            )
            classification_reasons.append(
                f"Still showed some recent activity, indicating partial engagement."
            )
            if dormancy > 0:
                classification_reasons.append(
                    f"Dormancy of {dormancy} days suggests slipping into disengagement."
                )
            classification_reasons.append(
                f"Reactivation score {total_score}/100 — {'worth investing in' if total_score >= 40 else 'needs urgent attention'}."
            )
            recommended_actions = [
                "Schedule a call to understand what has changed — personal issues? competition? dissatisfaction?",
                f"Highlight the agent's own track record: {policies} policies, {_fmt_premium(premium)} premium — remind them of their capability",
                "Offer a short-term contest or incentive to re-ignite competitive drive",
            ]

        elif seg == CohortSegment.WEEKEND_WARRIORS:
            classification_reasons.append(
                f"Agent works {work_type.lower()} but has still managed {policies} policy(ies)."
            )
            if agent.other_occupation:
                classification_reasons.append(
                    f"Primary occupation elsewhere ({agent.other_occupation}) — insurance is supplementary income."
                )
            classification_reasons.append(
                f"Sporadic activity pattern with {recent_policies} policies in last 12 months."
            )
            classification_reasons.append(
                "Part-time contributors can be valuable with the right low-friction engagement model."
            )
            recommended_actions = [
                "Engage via WhatsApp/Telegram at non-business hours (evenings, weekends)",
                "Share quick-sell product bundles that require minimal documentation",
                "Provide pre-filled proposal templates to reduce time investment per sale",
            ]

        elif seg == CohortSegment.ECONOMIC_DEFECTORS:
            classification_reasons.append(
                "Agent's dormancy is driven by economic/commission concerns."
            )
            if reason.startswith("economic.competitor"):
                classification_reasons.append(
                    "Agent has been attracted by competitor offering better commission rates."
                )
            elif reason.startswith("economic.commission_too_low"):
                classification_reasons.append(
                    "Agent feels the current commission structure is insufficient."
                )
            elif reason.startswith("economic.insufficient_income"):
                classification_reasons.append(
                    "Insurance income is too low to sustain the agent's effort."
                )
            classification_reasons.append(
                f"With {policies} policies and {_fmt_premium(premium)} total premium, "
                f"the agent has demonstrated sales ability."
            )
            recommended_actions = [
                "Schedule a 1-on-1 call to present the revised commission structure",
                "Share new commission structure PDF and income calculator tool",
                "Highlight top-earner case studies from the same region to show income potential",
            ]

        elif seg == CohortSegment.SYSTEM_FRUSTRATED:
            classification_reasons.append(
                "Agent went dormant primarily due to operational or system issues."
            )
            reason_label = reason.replace(".", " > ").replace("_", " ").title()
            classification_reasons.append(
                f"Specific issue: {reason_label}."
            )
            classification_reasons.append(
                "This is an addressable, non-agent-fault dormancy — high recovery potential if issue is resolved."
            )
            recommended_actions = [
                "Immediately escalate the specific operational issue to the relevant team",
                "Send a WhatsApp message acknowledging the problem and sharing a timeline for resolution",
                "Follow up within 72 hours with resolution status and offer hands-on assistance",
            ]

        elif seg == CohortSegment.ABANDONED_BY_ADM:
            classification_reasons.append(
                "Agent has received little to no ADM engagement."
            )
            if contact_attempts == 0:
                classification_reasons.append(
                    "Zero contact attempts recorded — the agent was never reached out to."
                )
            else:
                classification_reasons.append(
                    f"Only {contact_attempts} contact attempt(s) with {contact_responses} response(s) — insufficient follow-through."
                )
            classification_reasons.append(
                f"Agent has been on the books for {years:.1f} years with {policies} policies — "
                f"{'performance exists but was never nurtured' if policies > 0 else 'never given a chance to perform'}."
            )
            recommended_actions = [
                "Assign as a priority contact — schedule introductory call within 24 hours",
                "Acknowledge the gap in support honestly and share a personal engagement plan",
                "Set up weekly check-ins for the first month to build trust and momentum",
            ]

        elif seg == CohortSegment.CHRONIC_NEVER_ACTIVATORS:
            classification_reasons.append(
                f"Licensed for {years:.1f} years with zero policies sold."
            )
            classification_reasons.append(
                "Agent never crossed the activation barrier — likely needs fundamental support."
            )
            if contact_attempts > 3:
                classification_reasons.append(
                    f"Despite {contact_attempts} contact attempts, no conversion occurred — "
                    f"standard outreach is not working."
                )
            if digital_score <= 3:
                classification_reasons.append(
                    f"Low digital savviness ({digital_score}/10) may be a contributing barrier."
                )
            recommended_actions = [
                "Evaluate if agent is still interested in selling insurance — direct call required",
                "If interested, offer an in-person guided selling session with a live prospect",
                "Consider a structured 30-day activation bootcamp with daily micro-targets",
            ]

        elif seg == CohortSegment.LIFE_EVENT_PAUSED:
            classification_reasons.append(
                "Agent's dormancy is due to a personal life event."
            )
            if reason.startswith("personal.health"):
                classification_reasons.append(
                    "Health issues are the primary cause — agent needs empathetic, no-pressure engagement."
                )
            elif reason.startswith("personal.family"):
                classification_reasons.append(
                    "Family obligations are the primary cause — agent may return once situation stabilizes."
                )
            elif reason.startswith("personal.relocated"):
                classification_reasons.append(
                    "Agent has relocated — needs re-mapping to new territory and local market support."
                )
            classification_reasons.append(
                f"Prior track record of {policies} policies suggests capability — this is a pause, not an exit."
            )
            recommended_actions = [
                "Send a warm, empathetic WhatsApp message — no sales pressure, just a welfare check",
                "Mark for gentle re-engagement in 30-60 days depending on the situation",
                "Keep the agent on low-frequency updates about new products and incentives",
            ]

        elif seg == CohortSegment.REGULATORY_BLOCKED:
            classification_reasons.append(
                "Agent is blocked by a regulatory or compliance issue."
            )
            if reason.startswith("regulatory.license_expired"):
                classification_reasons.append(
                    "License has expired and must be renewed before the agent can sell."
                )
            elif reason.startswith("regulatory.license_expiring"):
                classification_reasons.append(
                    "License is expiring soon — time-sensitive intervention needed."
                )
            elif reason.startswith("regulatory.compliance"):
                classification_reasons.append(
                    "There is a compliance issue that needs resolution."
                )
            classification_reasons.append(
                f"Agent has {policies} policies and {_fmt_premium(premium)} premium — "
                f"worth retaining if the regulatory blocker can be cleared."
            )
            recommended_actions = [
                "Call the agent immediately to explain the license/compliance status and next steps",
                "Provide step-by-step renewal/compliance documentation and offer to assist with the process",
                "Set a hard follow-up date 7 days before any regulatory deadline",
            ]

        elif seg == CohortSegment.DIGITAL_ORPHANS:
            classification_reasons.append(
                f"Agent has very low digital savviness ({digital_score}/10) and is in a "
                f"{tier.value.replace('_', ' ')} market ({location})."
            )
            if not has_app:
                classification_reasons.append(
                    "Has not installed the mobile app — all engagement must be offline or voice-based."
                )
            classification_reasons.append(
                "Digital tooling barriers may be the primary reason for underperformance, not lack of intent."
            )
            classification_reasons.append(
                f"Education level ({education}) and age ({age if age else 'unknown'}) "
                f"suggest {'potential for digital upskilling' if education in ('Graduate', 'Post Graduate', 'Professional') else 'a need for offline-first approach'}."
            )
            recommended_actions = [
                "Arrange an in-person or phone-based training on the mobile app and basic digital tools",
                "Provide printed/WhatsApp-image-based product guides instead of digital-only resources",
                "Assign a local field buddy who can co-sell and demonstrate the digital workflow",
            ]

        elif seg == CohortSegment.HIGH_POTENTIAL_UNPOLISHED:
            classification_reasons.append(
                f"Agent is in a {'Metro' if tier == MarketTier.METRO else 'Tier 2'} market ({location}) "
                f"with strong demand potential."
            )
            classification_reasons.append(
                "Dormancy is due to a training or skills gap — not lack of market opportunity."
            )
            if policies > 0:
                classification_reasons.append(
                    f"Has sold {policies} policies, showing base capability that can be scaled with training."
                )
            else:
                classification_reasons.append(
                    "Zero sales so far, but the market context makes this agent worth developing."
                )
            recommended_actions = [
                "Enroll in a focused product knowledge + sales technique training program",
                "Assign a high-performing mentor from the same city for shadow selling",
                "Set a 60-day milestone plan: first sale within 30 days, 3 policies within 60 days",
            ]

        elif seg == CohortSegment.COMPETITOR_POACHED:
            classification_reasons.append(
                "Agent is known to be active with a competitor insurer."
            )
            if agent.previous_insurer:
                classification_reasons.append(
                    f"Previous/competing insurer identified: {agent.previous_insurer}."
                )
            classification_reasons.append(
                f"Agent has {policies} policies with us and {_fmt_premium(premium)} total premium — "
                f"{'a valuable relationship worth fighting for' if policies >= 5 else 'some history that can be leveraged'}."
            )
            recommended_actions = [
                "Schedule an urgent 1-on-1 call — understand what the competitor is offering",
                "Prepare a personalized comparison: our commission + support vs competitor",
                "Offer a loyalty/win-back incentive package tied to next-quarter targets",
            ]

        elif seg == CohortSegment.SATISFIED_PASSIVES:
            classification_reasons.append(
                f"Agent sells at a low but steady pace — {policies} total, {recent_policies} in last 12 months."
            )
            classification_reasons.append(
                f"Dormancy of {dormancy} days is moderate — agent is not lost, just not pushing hard."
            )
            classification_reasons.append(
                f"Response rate of {_response_pct(response_rate)} and work type '{work_type}' suggest "
                f"content with current effort level."
            )
            recommended_actions = [
                "Send a friendly WhatsApp nudge highlighting easy-sell products and pending renewals",
                "Share income potential calculator showing what 2-3 more policies/month could mean",
                "Invite to a regional agents' meet-up to reignite competitive energy",
            ]

        # Trim to max counts
        classification_reasons = classification_reasons[:4]
        risk_signals = risk_signals[:5]
        opportunities = opportunities[:5]
        recommended_actions = recommended_actions[:3]

        return {
            "classification_reasons": classification_reasons,
            "key_factors": key_factors,
            "risk_signals": risk_signals,
            "opportunities": opportunities,
            "recommended_actions": recommended_actions,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_market_tier(location: str) -> MarketTier:
        """Classify location into market tier."""
        city = (location or "").lower().strip()
        if city in METRO_CITIES:
            return MarketTier.METRO
        elif city in TIER_2_CITIES:
            return MarketTier.TIER_2
        # Simple heuristic: if not in known sets, check state
        return MarketTier.SEMI_URBAN

    @staticmethod
    def _get_career_stage(agent) -> CareerStage:
        """Determine career stage from years in insurance."""
        years = agent.years_in_insurance or 0
        if years < 1:
            return CareerStage.ROOKIE
        elif years < 3:
            return CareerStage.DEVELOPING
        else:
            return CareerStage.EXPERIENCED

    @staticmethod
    def get_segment_info(segment: str) -> dict:
        """Get display info for a segment."""
        try:
            seg = CohortSegment(segment)
            return SEGMENT_INFO.get(seg, {})
        except ValueError:
            return {}

    @staticmethod
    def get_all_segments() -> List[dict]:
        """Get info for all segments."""
        return [
            {
                "segment": seg.value,
                "display": info["display"],
                "description": info["description"],
                "default_strategy": info["strategy"].value,
            }
            for seg, info in SEGMENT_INFO.items()
        ]


# Singleton
cohort_classifier = CohortClassifier()
