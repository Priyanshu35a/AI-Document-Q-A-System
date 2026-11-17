import os
import fitz  # PyMuPDF

def create_sample_pdf(output_path: str = "sample_company_report.pdf"):
    """
    Creates a rich 4-page PDF document with distinct facts on each page
    to verify page-aware chunking and grounded citations.
    """
    doc = fitz.open()

    # --- Page 1: Overview & Leadership ---
    page1 = doc.new_page()
    p1_text = """Acme Technologies — Annual Enterprise Report
Page 1: Corporate Overview & Leadership

Acme Technologies was founded in 2018 with the core mission of democratizing intelligent automation for healthcare and enterprise logistics.
The executive leadership team comprises:
- Chief Executive Officer (CEO): Dr. Elena Rostova
- Chief Technology Officer (CTO): Marcus Vance
- Head of Machine Learning Research: Dr. Sunita Patel

The company headquarters is situated in Seattle, Washington, with regional engineering hubs in Toronto and Berlin.
Across the past fiscal year, the global workforce expanded from 420 to 680 full-time employees.
"""
    page1.insert_text((50, 72), p1_text, fontsize=11)

    # --- Page 2: Financial Performance ---
    page2 = doc.new_page()
    p2_text = """Acme Technologies — Annual Enterprise Report
Page 2: Financial Performance & Fiscal Metrics

In the third fiscal quarter (Q3), Acme Technologies recorded a record revenue of $42.5 million, representing a 34% year-over-year increase.
Key financial highlights include:
- Gross Profit Margin: 72.4%
- Net Operating Income: $8.2 million
- Research and Development (R&D) Expenditure: $11.8 million
- Enterprise Software Subscription ARR: $128.0 million

The enterprise software division accounted for 68% of total gross revenue, driven by strong enterprise adoption of our cloud RAG platform.
"""
    page2.insert_text((50, 72), p2_text, fontsize=11)

    # --- Page 3: Technology & Quantum Breakthroughs ---
    page3 = doc.new_page()
    page3_text = """Acme Technologies — Annual Enterprise Report
Page 3: Technological Breakthroughs & Platform Architecture

On October 14, the R&D division unveiled the 'Apex-Neural' quantum indexing engine, achieving 99.4% precision in semantic vector retrieval.
Key technological features:
1. Sub-millisecond latency for dense vector searches over 100 million embeddings.
2. Zero-shot multilingual translation supporting 42 languages natively.
3. Strict no-hallucination verification module enforcing context attribution.
The Apex architecture combines BGE-M3 dense embeddings with hybrid sparse BM25 indexing for robust domain adaptation.
"""
    page3.insert_text((50, 72), page3_text, fontsize=11)

    # --- Page 4: ESG & 2027 Strategic Roadmap ---
    page4 = doc.new_page()
    page4_text = """Acme Technologies — Annual Enterprise Report
Page 4: Sustainability, ESG, & Strategic Roadmap

Acme Technologies has committed to achieving Net-Zero carbon emissions across all datacenter operations by the year 2028.
Strategic goals for 2027 include:
- Expansion of datacenter operations powered 100% by geothermal and solar renewable energy.
- Launch of on-premise privacy-preserving edge inference devices for hospital networks.
- Establishing the Acme AI Safety Fellowship with an initial endowment of $5.0 million.
"""
    page4.insert_text((50, 72), page4_text, fontsize=11)

    doc.save(output_path)
    doc.close()
    print(f"Sample PDF successfully generated at: {output_path}")

if __name__ == "__main__":
    create_sample_pdf()
