from typing import Dict, List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field


class DocType(str, Enum):
    LOAN_AGREEMENT = "LOAN_AGREEMENT"
    AUDIT_NOTE = "AUDIT_NOTE"
    KYC_DOSSIER = "KYC_DOSSIER"
    DECOY = "DECOY"
    CORRUPT = "CORRUPT"


class DocumentInfo(BaseModel):
    filename: str
    filepath: str
    doc_type: DocType
    account_id: Optional[str] = None
    company_name: Optional[str] = None
    is_valid: bool = True
    raw_text: Optional[str] = None


class CovenantClause(BaseModel):
    clause_number: str  # e.g., "6.1", "6.2", "6.3"
    title: Optional[str] = None
    metric_name: str  # e.g. "Leverage Ratio", "Capex Limit", "Related Party Limit"
    operator: str  # "<=", ">=", "<", ">"
    threshold: float
    period: str = "ANNUAL"  # "ANNUAL", "QUARTERLY"
    carve_out_clause: Optional[str] = None
    is_marginal_single_txn: bool = False  # True if test is tied to a single marginal transaction
    raw_clause_text: str = ""  # Full verbatim text of clause 6.X
    numerator_definition: Optional[str] = None   # Description of numerator items per contract
    denominator_definition: Optional[str] = None # Description of denominator items if ratio test
    references_audit_adjustment: bool = False    # True if clause references audit adjustments
    references_kyc: bool = False                 # True if clause references KYC/related parties


class CovenantExtractionResult(BaseModel):
    account_id: str
    company_name: str
    covenants: Dict[str, CovenantClause] = Field(default_factory=dict)


class AuditAdjustment(BaseModel):
    account_id: str
    company_name: Optional[str] = None
    ebitda_addbacks_total: float = 0.0
    ebitda_addback_descriptions: List[str] = Field(default_factory=list)
    capex_reclassifications_total: float = 0.0
    capex_reclass_counterparties: List[str] = Field(default_factory=list)
    excluded_txn_ids: List[str] = Field(default_factory=list)  # Transactions assigned to other periods by auditor
    notes: Optional[str] = None


class KYCDossierInfo(BaseModel):
    account_id: str
    company_name: Optional[str] = None
    related_parties: List[str] = Field(default_factory=list)  # list of affiliate company names/IDs
    related_parties_20plus: List[str] = Field(default_factory=list)  # entities with >= 20% ownership


class TransactionRecord(BaseModel):
    txn_id: str
    date: str
    account_id: str
    counterparty: str
    description: str
    amount: float
    currency: str


class CovenantAnswer(BaseModel):
    status: Literal["COMPLIANT", "BREACH"]
    actual: float
    evidence_txn_id: Optional[str] = None


class SubmissionSchema(BaseModel):
    team: str
    contact_email: str
    model: str
    answers: Dict[str, Dict[str, CovenantAnswer]]
