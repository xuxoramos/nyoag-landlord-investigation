# NYOAG Landlord Investigation

Identifying landlords in New York City that warrant investigation by the New York Office of the Attorney General (NYOAG), using HPD violation data, ownership network analysis, and a weighted harm-scoring methodology.

## Table of Contents

- [Overview](#overview)
- [Data Sources](#data-sources)
- [Methodology](#methodology)
- [Key Findings](#key-findings)
- [Visualizations](#visualizations)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
- [Repository Structure](#repository-structure)

## Overview

This project analyzes NYC Housing Preservation & Development (HPD) data to surface landlords whose properties exhibit the most severe and persistent housing code violations. The analysis focuses on **Manhattan (Borough 1)** and **Brooklyn (Borough 3)** with violations recorded **from January 2023 onward**. It links violations to property registrations and contact records to unmask the actual individuals behind LLCs and management companies, then ranks them by a composite harm score.

## Data Sources

| Dataset | Source | Description |
|---------|--------|-------------|
| **HPD Violations** | [NYC Open Data (wvxf-dwi5)](https://data.cityofnewyork.us/Housing-Development/Housing-Maintenance-Code-Violations/wvxf-dwi5) | Housing maintenance code violations |
| **HPD Registrations** | [NYC Open Data (tesw-yqqr)](https://data.cityofnewyork.us/Housing-Development/Multiple-Dwelling-Registrations/tesw-yqqr) | Multiple dwelling registrations |
| **HPD Contacts** | [NYC Open Data (feu5-w2e2)](https://data.cityofnewyork.us/Housing-Development/Registration-Contacts/feu5-w2e2) | Registration contact information |
| **PLUTO** | [NYC Planning](https://www.nyc.gov/site/planning/data-maps/open-data/dwn-pluto-mappluto.page) | Tax lot and building characteristics |

All datasets are converted to **Parquet** format for efficient columnar reads and compressed storage.

## Methodology

### 1. BBL Standardization & Dataset Linking

Every property is identified by a 10-digit **BBL** (Borough-Block-Lot) code. The pipeline standardizes BBLs across all four datasets and joins them through:

- **Violations → Registrations** via BBL
- **Merged → Contacts** via Registration ID
- **Merged → PLUTO** via BBL

### 2. Ownership Network Analysis

To see through shell LLCs and management entities, the analysis groups contacts by:

- **Person name** (first + last, cleaned and uppercased)
- **Business address** (house number + street name)

This identified **27,008 owners controlling multiple properties** in the target boroughs.

### 3. Harm Score Calculation

Each owner receives a composite harm score built from four weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| **Violation Severity** | 40% | Weighted sum of violations — Class C (immediately hazardous) = 5 pts, Class B (hazardous) = 2.5 pts, Class A (non-hazardous) = 1 pt |
| **Violation Density** | 30% | Total violations per residential unit |
| **Widespread Harm** | 20% | Fraction of an owner's properties that have violations |
| **Persistence** | 10% | Fraction of violations that remain unresolved |

## Key Findings

### Top 10 Landlords Flagged for Investigation

The analysis scored **16,083 owners** and ranked them by total harm. The ten highest-scoring are:

| Rank | Owner / Address Network | Properties | Total Violations | Class C Violations | Harm Score |
|------|------------------------|------------|------------------|--------------------|------------|
| 1 | 168 39th Street (address network) | 73 | 86,012 | 23,820 | 2,677,000 |
| 2 | Rick Gropper | 53 | 83,371 | 22,611 | 2,594,000 |
| 3 | Valerie Castillo | 6 | 81,715 | 22,095 | 2,543,000 |
| 4 | Rose Santo | 6 | 81,715 | 22,095 | 2,543,000 |
| 5 | 116 East 27th Street (address network) | 21 | 81,377 | 21,995 | 2,532,000 |
| 6 | 4611 12th Avenue (address network) | 36 | 41,056 | 14,772 | 1,283,000 |
| 7 | Arnice Steward | 28 | 39,456 | 14,312 | 1,234,000 |
| 8 | 3301 Foster Avenue (address network) | 28 | 39,456 | 14,312 | 1,234,000 |
| 9 | Herminio Torres | 205 | 35,621 | 10,181 | 1,108,000 |
| 10 | 1735 Park Avenue (address network) | 172 | 34,053 | 9,964 | 1,060,000 |

**Notable patterns:**

- **Valerie Castillo** and **Rose Santo** appear with identical violation counts across only 6 properties, suggesting co-ownership of a small but extremely problematic portfolio.
- **Herminio Torres** controls **205 properties** — the largest portfolio in the top 10 — with over 35,000 violations and more than 10,000 Class C (immediately hazardous) violations.
- Several address-based networks (168 39th St, 116 East 27th St) indicate management offices linked to large numbers of violating properties.

### Violation Class Distribution

The dataset contains roughly **1.5 million violations** in the target boroughs since 2023:

- **Class B** (hazardous): ~590,000 — the most common class
- **Class C** (immediately hazardous): ~445,000
- **Class A** (non-hazardous): ~400,000
- **Class I** (information): ~100,000

The high proportion of Class B and C violations underscores the severity of housing conditions in the studied boroughs.

## Visualizations

### Distribution of Violation Classes

![Distribution of Violation Classes](https://github.com/user-attachments/assets/172840f0-1766-4958-96f9-1999d24373c5)

Class B violations dominate the dataset, followed closely by Class C (immediately hazardous) and Class A. This distribution shows that the majority of recorded violations pose a direct risk to tenant health and safety.

### Top 20 Landlords by Harm Score

![Top 20 Landlords by Harm Score](https://github.com/user-attachments/assets/fa9b927c-58ac-461f-9db2-f8ba030b4184)

The harm score drops sharply after the top 5 landlords, suggesting a small group of owners is responsible for a disproportionate share of housing harm.

### Properties vs. Violations Scatter Plot

![Properties vs Violations](https://github.com/user-attachments/assets/b6b32ca6-145e-4130-82c8-c4810bf27424)

Each point represents an owner. Bubble size encodes the total harm score and color intensity encodes the number of Class C violations. Owners in the upper-right with deep-red, large bubbles are the highest-priority targets.

### Harm Score Components Heatmap (Top 10)

![Harm Components Heatmap](https://github.com/user-attachments/assets/36d00637-8cff-4425-ba95-903e0dc26f50)

This heatmap breaks down the four harm components for the top 10 landlords, revealing which factors — severity, density, widespread impact, or persistence — drive each owner's score.

## Technology Stack

| Tool | Role |
|------|------|
| **Polars** | High-performance DataFrame processing (Rust-backed, lazy evaluation, parallel) |
| **Parquet** | Columnar storage with Zstd compression — 50-80% smaller than CSV, 10-100x faster reads |
| **Matplotlib / Seaborn** | Visualization |
| **NumPy** | Numerical operations |
| **DuckDB** | Initial CSV-to-Parquet conversion (see `convert_to_parquet_duckdb.ipynb`) |

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
pip install -r requirements.txt
```

### Running the Analysis

1. **Obtain the data** — download CSV files from [NYC Open Data](https://data.cityofnewyork.us/) and place them in the `data/` directory, or uncomment the `download_and_convert_to_parquet()` call in the notebook (requires the `sodapy` package).
2. **Convert to Parquet** — run `convert_to_parquet_duckdb.ipynb` to convert raw CSVs to Parquet.
3. **Run the analysis** — open `nyoag_analysis.ipynb` and execute all cells.

Output artifacts:

- `top_10_landlords_for_investigation.csv` / `.parquet`
- `all_landlords_harm_scores.parquet`
- Four PNG visualizations

## Repository Structure

```
├── README.md
├── requirements.txt
├── LICENSE
├── convert_to_parquet_duckdb.ipynb   # CSV → Parquet conversion utility
├── nyoag_analysis.ipynb              # Main analysis notebook
├── data/
│   ├── hpd_contacts.zip
│   └── hpd_registrations.zip
├── violation_distribution.png
├── top_landlords_harm_score.png
├── properties_violations_scatter.png
└── harm_components_heatmap.png
```
