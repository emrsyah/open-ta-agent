import pytest
from app.utils.streaming import _audit_citations
from app.core.models import CitedPaper

def test_audit_clean_citations():
    answer = "This is a fact [1] and another [2]."
    papers = [
        CitedPaper(id="p1", title="T1", abstract="A1", year=2020, citation_number=1),
        CitedPaper(id="p2", title="T2", abstract="A2", year=2021, citation_number=2),
    ]
    result = _audit_citations(answer, papers)
    assert result["is_clean"] is True
    assert result["hallucinated_citation_numbers"] == []
    assert result["total_citations_in_answer"] == 2
    assert result["total_papers_available"] == 2

def test_audit_hallucinated_citation():
    answer = "Fact [1] and fake [3]."
    papers = [
        CitedPaper(id="p1", title="T1", abstract="A1", year=2020, citation_number=1),
        CitedPaper(id="p2", title="T2", abstract="A2", year=2021, citation_number=2),
    ]
    result = _audit_citations(answer, papers)
    assert result["is_clean"] is False
    assert result["hallucinated_citation_numbers"] == [3]
    assert result["total_citations_in_answer"] == 2
    assert result["total_papers_available"] == 2

def test_audit_out_of_order_valid():
    answer = "Fact [2] then [1]."
    papers = [
        CitedPaper(id="p1", title="T1", abstract="A1", year=2020, citation_number=1),
        CitedPaper(id="p2", title="T2", abstract="A2", year=2021, citation_number=2),
    ]
    result = _audit_citations(answer, papers)
    assert result["is_clean"] is True
    assert result["hallucinated_citation_numbers"] == []

def test_audit_no_citations():
    answer = "Just text."
    papers = [CitedPaper(id="p1", title="T1", abstract="A1", year=2020, citation_number=1)]
    result = _audit_citations(answer, papers)
    assert result["is_clean"] is True
    assert result["total_citations_in_answer"] == 0

def test_audit_no_papers_hallucinated():
    answer = "Citing [1] but no papers."
    papers = []
    result = _audit_citations(answer, papers)
    assert result["is_clean"] is False
    assert result["hallucinated_citation_numbers"] == [1]
