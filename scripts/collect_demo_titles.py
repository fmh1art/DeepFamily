#!/usr/bin/env python3
"""Collect the official VLDB/SIGMOD/ICDE 2025--2026 demo-title corpus.

Four lists are parsed from conference HTML. VLDB 2025 and ICDE 2025 are
transcribed from the official proceedings/program because their pages are not
reliably machine-readable from this environment. Expected counts make changes
or omissions fail loudly.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter

import requests
from bs4 import BeautifulSoup


COLLECTED_ON = "2026-09-06"

HTML_SOURCES = {
    ("SIGMOD", 2025): (
        "https://2025.sigmod.org/sigmod_demo_papers.shtml",
        "#maincontent li b",
    ),
    ("SIGMOD", 2026): (
        "https://2026.sigmod.org/sigmod_demos.shtml",
        "#maincontent li strong",
    ),
    ("VLDB", 2026): (
        "https://www.vldb.org/2026/demonstrations.html",
        "h2.demo-paper-title",
    ),
    ("ICDE", 2026): (
        "https://icde2026.github.io/demo-papers.html",
        ".paper-list .title",
    ),
}

STATIC_SOURCES = {
    ("VLDB", 2025): "https://www.vldb.org/pvldb/vol18/FrontMatterVol18No12.pdf",
    ("ICDE", 2025): "https://ieee-icde.org/2025/demonstrations/",
}

STATIC_TITLES = {
    ("VLDB", 2025): [
        "TCO2: Analyzing the Carbon Footprint of Database Server Replacements",
        "FDepHunter: Harnessing Negative Examples to Expose Fakes and Reveal Ghosts",
        "VIDEX: A Disaggregated and Extensible Virtual Index for Cloud-Native and AI-Driven Databases",
        "DVote: Constraining Committee Voting with Database Dependencies",
        "Graph Compression for Interpretable Graph Neural Network Inference At Scale",
        "Query running too slow? Rewrite it with Quorion!",
        "Demonstration of ModelarDB: Model-Based Management of High-Frequency Time Series Across Edge, Cloud, and Client",
        "Democratize MATCH_RECOGNIZE!",
        "Opening The Black-Box: Explaining Learned Cost Models For Databases",
        "Horizon: Robust Checks for SQL Migration Using LLMs",
        "A Demonstration of QueryArtisan: Real-Time Data Lake Analysis via Dynamically Generated Data Manipulation Code",
        "RecForUS: A Recommender System for Uncertain Scores",
        "PrivEval: a tool for interactive evaluation of privacy metrics in synthetic data generation",
        "Styx in Action: Transactional Cloud Applications Made Easy",
        "Can Surrogate Keys Negatively Impact Data Quality?",
        "JUSTINE (JUST-INsert Engine): Demonstrating Self-organizing Data Schemas",
        "Unify: A System For Unstructured Data Analytics",
        "UmbraPerf - Profiling Results Tailored for DBMS Developers",
        "Smart SPARQL Advisor: Guiding Users in Query Formulation with Performance Prediction",
        "Analytics Are Heavy. The DBMS Is Busy. When Will My Mission-Critical Transaction Start Running?",
        "Accelerating Tabular Inference: Training Data Generation with TENET",
        "Accordion: Balancing Performance and Cost in Cloud-Native Data Analysis with Intra-Query Runtime Elasticity",
        "Demonstration of Reflex: How SMPC Query Execution can be sped up through Efficient and Flexible Intermediate Result Size Trimming",
        "Enter the Warp: Fast and Adaptive Data Transfer with XDBC",
        "RadlER: Deduplicated Sampling On-Demand",
        "MLN-geeWhiz: A Dashboard for Supporting Complete Life-Cycle of Complex Data Analysis using Multilayer Networks",
        "Hint-QPT: Hints for Robust Query Performance Tuning",
        "ClaimIt: Finding Convincing Views to Endorse a Claim",
        "DortDB: Bridging Query Languages for Multi-Model Data Ponds",
        "DemandClean: A Multi-Objective Learning Framework for Balancing Model Tolerance to Data Authenticity and Diversity",
        "TARImpute: Task-Aware Auto-Recommender System for Missing Value Imputation Algorithms with Clustering Case Studies",
        "A Demonstration of POLARIS: An Interactive and Scalable Data Infrastructure for Polar Science",
        "GooseDB: A Database Engine that Optimally Refines Top-k Queries to Satisfy Representation Constraints",
        "NeuroFlinkCEP: Neurosymbolic Complex Event Recognition Optimized across IoT Platforms",
        'mlidea: Interactively Improving ML Data Preparation Code via "Shadow Pipelines"',
        "Mining Meaningful Keys and Foreign Keys with High Precision and Recall",
        "SDG-KG: A Framework to Compute SDG Indicator using Open Data",
        "FedVSE: A Privacy-Preserving and Efficient Vector Search Engine for Federated Databases",
        "APEX-DAG: Library and Language independent Pipeline EXtraction",
        "Demonstrating Matelda for Multi-Table Error Detection",
        "DBPecker: A Graph-Based Compound Anomaly Diagnosis System for Distributed RDBMSs",
        "DocDB: A Database for Unstructured Document Analysis",
        "ContextCache: Context-Aware Semantic Cache for Multi-Turn Queries in Large Language Models",
        "Simulating a Transactional Server for Multi-Model Systems",
        "TableCopilot: A Table Assistant Empowered by Natural Language Conditional Table Discovery",
        "LETIndex: A Secure Learned Index with TEE",
        "Play2Win: A Windowing Playground for Continuous Queries",
        "Vadacode: A Logician-friendly IDE for Datalog+/-",
        "Beyond Quacking: Deep Integration of Language Models and RAG into DuckDB",
        "SAIL: A Voyage to Symbolic Approximation Solutions for Time-Series Analysis",
        "Buckaroo: A Direct Manipulation Visual Data Wrangler",
        "Sort it Like You Mean It: Discovering Semantically Interesting Attribute Augmentations to Sort Tables",
        "EasyAD: A Demonstration of Automated Solutions for Time-Series Anomaly Detection",
        "LASEK: LLM-Assisted Style Exploration Kit for Geospatial Data",
        "A Demonstration of Q2O: Quantum-augmented Query Optimizer",
    ],
    ("ICDE", 2025): [
        "DATAMORPHER: Automatic Data Transformation Using LLM-based Zero-Shot Code Generation",
        "Db2une: Tuning IBM Db2 with Deep Learning",
        "DreamCreek: AI for Battery Formation and Grading",
        "BitTuner: A Toolbox for Automatically Configuring Learned Data Compressors",
        "DeviceScope: An Interactive App to Detect and Localize Appliance Patterns in Electricity Consumption Time Series",
        "Towards On-database Contextual Model Explanation",
        "scRAG: an Efficient Retrieval Augmented Generation System for scRNA-seq Data Analysis",
        "EasyTime: Time Series Forecasting Made Easy",
        "Data Backup System with No Impact on Business Processing Utilizing Storage and Container Technologies",
        "SwiftDP: An Efficient Framework for Automated Data Preparation Pipeline Generation",
        "MITra: Populating Graph Traversal Algorithms",
        "Graphint: Graph-based Time Series Clustering Visualisation Tool",
        "HRLMS: A Data-driven Hierarchical Reinforcement Learning System for Interactive Rule Intervention and Visualization",
        "EAST: An Interpretable Knob Estimation System for Cloud Database",
        "HiVQ: A Real-time Interactive Visual Query System on Geospatial Big Data",
        "Popper: A Dataflow System for In-Flight Error Handling in Machine Learning Workflow",
        "UniClean: A Multi-Signal Fusion Pipeline for Optimizing Data Cleaning Workflow",
        "LineageX: A Column Lineage Extraction System for SQL",
        "CSKQS: A Query System for Collective Spatial Keyword Queries",
        "PixelsDB: Serverless and NL-Aided Data Analytics with Flexible Service Levels and Prices",
        "RAISIN: A Parallel Subgraph Matching Tool Exploiting Community Structures in Social Networks",
        "Chat2DB: Chatting to the Database with Interactive Agent Assisted Language Models",
        "ARAG: Analysis and Retrieval Augmented Generation for Comprehensive Reasoning over Socioeconomic Data",
        "Artemis: A Customizable Workload Generation Toolkit for Benchmarking Cardinality Estimation",
        "IKGA: An Interactive Visualization Tool for Knowledge Graph Alignment",
        "CBAClean:A Comprehensive System for Recommending Data Cleaning Solutions through Cost-Benefit Analysis in Data Quality Management",
    ],
}

EXPECTED_COUNTS = {
    ("VLDB", 2025): 55,
    ("VLDB", 2026): 92,
    ("SIGMOD", 2025): 69,
    ("SIGMOD", 2026): 39,
    ("ICDE", 2025): 26,
    ("ICDE", 2026): 20,
}


def normalize(value: str) -> str:
    return " ".join(html.unescape(value).split())


def collect() -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], tuple[str, list[str], str]] = {}
    headers = {"User-Agent": "Mozilla/5.0"}

    for key, (url, selector) in HTML_SOURCES.items():
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        titles = [normalize(node.get_text(" ", strip=True)) for node in soup.select(selector)]
        grouped[key] = (url, titles, "parsed official accepted-list HTML")

    for key, titles in STATIC_TITLES.items():
        note = "transcribed official proceedings TOC" if key == ("VLDB", 2025) else "transcribed official program"
        grouped[key] = (STATIC_SOURCES[key], [normalize(title) for title in titles], note)

    for key, expected in EXPECTED_COUNTS.items():
        actual = len(grouped[key][1])
        if actual != expected:
            raise RuntimeError(f"{key}: expected {expected} titles, found {actual}")

    records: list[dict[str, object]] = []
    for venue in ("VLDB", "SIGMOD", "ICDE"):
        for year in (2025, 2026):
            url, titles, method = grouped[(venue, year)]
            for ordinal, title in enumerate(titles, 1):
                records.append(
                    {
                        "venue": venue,
                        "year": year,
                        "ordinal": ordinal,
                        "title": title,
                        "official_source": url,
                        "extraction": method,
                    }
                )
    return records


def render_markdown(records: list[dict[str, object]]) -> str:
    lines = [
        "# VLDB / SIGMOD / ICDE Demo titles, 2025--2026",
        "",
        f"Collected on {COLLECTED_ON}. Track membership follows each conference's official accepted list/program; titles preserve official wording except whitespace normalization.",
        "",
        "| Venue | 2025 | 2026 | Total |",
        "|---|---:|---:|---:|",
    ]
    counts = Counter((r["venue"], r["year"]) for r in records)
    for venue in ("VLDB", "SIGMOD", "ICDE"):
        a, b = counts[(venue, 2025)], counts[(venue, 2026)]
        lines.append(f"| {venue} | {a} | {b} | {a + b} |")
    lines.extend([f"| **All** | **{sum(counts[(v, 2025)] for v in ('VLDB', 'SIGMOD', 'ICDE'))}** | **{sum(counts[(v, 2026)] for v in ('VLDB', 'SIGMOD', 'ICDE'))}** | **{len(records)}** |", ""])

    for venue in ("VLDB", "SIGMOD", "ICDE"):
        for year in (2025, 2026):
            subset = [r for r in records if r["venue"] == venue and r["year"] == year]
            source = subset[0]["official_source"]
            method = subset[0]["extraction"]
            lines.extend([f"## {venue} {year} ({len(subset)})", "", f"Official source: [{source}]({source}); {method}.", ""])
            lines.extend(f"{r['ordinal']}. {r['title']}" for r in subset)
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    records = collect()
    if args.format == "json":
        print(json.dumps({"collected_on": COLLECTED_ON, "records": records}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(records))


if __name__ == "__main__":
    main()
