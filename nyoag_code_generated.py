"""
NYAG Landlord Investigation Analysis - Polars + Parquet Version
===============================================================
Optimized for large-scale data processing using Polars and Parquet format.

Author: Analysis for NYAG Challenge
Date: January 2026
"""

import polars as pl
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Set visualization style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)

# ============================================================================
# SECTION 1: DATA LOADING AND PREPROCESSING WITH POLARS
# ============================================================================

def download_and_convert_to_parquet():
    """
    Download data from NYC Open Data and convert to Parquet format.
    
    Parquet Benefits:
    - 10-100x faster reads than CSV
    - Columnar storage = efficient filtering
    - Built-in compression (typically 50-80% smaller)
    - Preserves data types
    """
    from sodapy import Socrata
    
    client = Socrata("data.cityofnewyork.us", None)
    
    # Define datasets with filters
    datasets = {
        'violations': {
            'id': 'wvxf-dwi5',
            'filename': 'hpd_violations.parquet',
            'where': "inspectiondate >= '2023-01-01' AND boroid IN ('1', '3')",
            'limit': 500000
        },
        'registrations': {
            'id': 'tesw-yqqr',
            'filename': 'hpd_registrations.parquet',
            'where': "boroid IN ('1', '3')",
            'limit': 200000
        },
        'contacts': {
            'id': 'feu5-w2e2',
            'filename': 'hpd_contacts.parquet',
            'limit': 300000
        }
    }
    
    print("Downloading and converting datasets to Parquet...")
    
    for name, config in datasets.items():
        print(f"\nProcessing {name}...")
        
        # Download from Socrata API
        results = client.get(
            config['id'],
            where=config.get('where'),
            limit=config['limit']
        )
        
        # Convert to Polars DataFrame
        df = pl.DataFrame(results)
        
        # Write to Parquet with compression
        df.write_parquet(
            config['filename'],
            compression='zstd',  # Excellent compression ratio
            compression_level=3
        )
        
        print(f"Saved {len(df)} records to {config['filename']}")
        print(f"Columns: {df.columns}")
    
    print("\n✓ All datasets converted to Parquet format")

def load_parquet_data(subset_strategy='manhattan_brooklyn_recent'):
    """
    Load Parquet files using Polars lazy evaluation.
    
    Lazy evaluation allows filtering before loading into memory.
    
    Subsetting Strategy:
    - Time window: 2023-01-01 to present
    - Boroughs: Manhattan (1) and Brooklyn (3)
    """
    print("Loading data with lazy evaluation...")
    print(f"Strategy: {subset_strategy}")
    
    # Load with lazy evaluation for efficiency
    violations = pl.scan_parquet('hpd_violations.parquet')
    registrations = pl.scan_parquet('hpd_registrations.parquet')
    contacts = pl.scan_parquet('hpd_contacts.parquet')
    
    # Apply filters using lazy evaluation
    violations = violations.filter(
        (pl.col('inspectiondate') >= '2023-01-01') &
        (pl.col('boroid').is_in(['1', '3']))
    )
    
    registrations = registrations.filter(
        pl.col('boroid').is_in(['1', '3'])
    )
    
    print("Data loaded with lazy evaluation (not yet computed)")
    
    return violations, registrations, contacts

def load_pluto_parquet(pluto_path='pluto_manhattan_brooklyn.parquet'):
    """
    Load PLUTO data (download MapPLUTO and convert to Parquet).
    
    PLUTO download:
    https://www.nyc.gov/site/planning/data-maps/open-data/dwn-pluto-mappluto.page
    """
    if Path(pluto_path).exists():
        pluto = pl.scan_parquet(pluto_path)
        print(f"Loaded PLUTO data from {pluto_path}")
        return pluto
    else:
        print(f"PLUTO file not found: {pluto_path}")
        print("Download from NYC Planning and convert to Parquet")
        return None

# ============================================================================
# SECTION 2: BBL STANDARDIZATION AND LINKING WITH POLARS
# ============================================================================

def standardize_bbl_polars(df, boro_col='boroid', block_col='block', lot_col='lot'):
    """
    Create standardized BBL using Polars expressions.
    BBL format: Borough(1) + Block(5) + Lot(4) = 10 digits
    
    Polars is much faster than pandas for this operation.
    """
    return df.with_columns([
        (
            pl.col(boro_col).cast(pl.Utf8).str.zfill(1) +
            pl.col(block_col).cast(pl.Utf8).str.zfill(5) +
            pl.col(lot_col).cast(pl.Utf8).str.zfill(4)
        ).alias('BBL')
    ])

def link_datasets_polars(violations, registrations, contacts, pluto=None):
    """
    Link all datasets using Polars joins.
    
    Polars joins are significantly faster than pandas,
    especially with lazy evaluation.
    """
    print("Standardizing BBLs across datasets...")
    
    # Standardize BBLs (still lazy)
    violations = standardize_bbl_polars(violations)
    registrations = standardize_bbl_polars(registrations)
    
    if pluto is not None:
        pluto = standardize_bbl_polars(
            pluto, 
            boro_col='Borough', 
            block_col='Block', 
            lot_col='Lot'
        )
    
    print("Linking violations to registrations...")
    # Left join violations with registrations
    merged = violations.join(
        registrations,
        on='BBL',
        how='left',
        suffix='_reg'
    )
    
    print("Linking to contacts...")
    # Join with contacts on registrationid
    merged = merged.join(
        contacts,
        on='registrationid',
        how='left',
        suffix='_contact'
    )
    
    if pluto is not None:
        print("Linking to PLUTO building data...")
        # Select specific PLUTO columns to reduce memory
        pluto_subset = pluto.select([
            'BBL',
            'UnitsRes',
            'UnitsTotal',
            'YearBuilt',
            'OwnerName',
            'Address'
        ])
        
        merged = merged.join(
            pluto_subset,
            on='BBL',
            how='left',
            suffix='_pluto'
        )
    
    print("Dataset linking complete (still lazy)")
    return merged

# ============================================================================
# SECTION 3: OWNERSHIP NETWORK ANALYSIS WITH POLARS
# ============================================================================

def identify_owner_networks_polars(contacts, registrations):
    """
    Identify actual landlords behind LLCs using Polars.
    
    Strategy:
    - Group by contact names, addresses, phone numbers
    - Use Polars' fast group_by operations
    """
    print("\nAnalyzing ownership networks...")
    
    # Collect contacts into memory (needed for complex grouping)
    contacts_df = contacts.collect()
    
    # Clean and standardize contact information
    contacts_df = contacts_df.with_columns([
        pl.col('businessname').str.to_uppercase().str.strip_chars().alias('businessname_clean'),
        pl.col('firstname').str.to_uppercase().str.strip_chars().alias('firstname_clean'),
        pl.col('lastname').str.to_uppercase().str.strip_chars().alias('lastname_clean'),
    ])
    
    # Create person identifier
    contacts_df = contacts_df.with_columns([
        (
            pl.col('firstname_clean').fill_null('') + 
            pl.lit('_') + 
            pl.col('lastname_clean').fill_null('')
        ).alias('person_id')
    ])
    
    # Group properties by person
    person_networks = (
        contacts_df
        .filter(pl.col('person_id') != '_')
        .group_by('person_id')
        .agg([
            pl.col('registrationid').n_unique().alias('num_properties'),
            pl.col('registrationid').unique().alias('registration_ids')
        ])
        .filter(pl.col('num_properties') > 1)
        .sort('num_properties', descending=True)
    )
    
    # Group by business address
    address_networks = (
        contacts_df
        .filter(
            pl.col('businesshousenumber').is_not_null() &
            pl.col('businessstreetname').is_not_null()
        )
        .with_columns([
            (
                pl.col('businesshousenumber').cast(pl.Utf8) + 
                pl.lit('_') + 
                pl.col('businessstreetname')
            ).alias('address_key')
        ])
        .group_by('address_key')
        .agg([
            pl.col('registrationid').n_unique().alias('num_properties'),
            pl.col('registrationid').unique().alias('registration_ids')
        ])
        .filter(pl.col('num_properties') > 1)
        .with_columns([
            (pl.lit('ADDRESS_') + pl.col('address_key')).alias('owner_identifier')
        ])
        .select(['owner_identifier', 'num_properties', 'registration_ids'])
    )
    
    # Combine both network types
    person_networks = person_networks.rename({'person_id': 'owner_identifier'})
    networks_df = pl.concat([person_networks, address_networks])
    networks_df = networks_df.sort('num_properties', descending=True)
    
    print(f"Identified {len(networks_df)} owners with multiple properties")
    return networks_df

# ============================================================================
# SECTION 4: HARM SCORING METHODOLOGY WITH POLARS
# ============================================================================

def calculate_harm_score_polars(merged, networks_df):
    """
    Calculate comprehensive harm score using Polars expressions.
    
    Scoring Factors (weighted):
    1. Violation severity (40%): Class A, B, C violations
    2. Violation density (30%): Violations per unit
    3. Widespread harm (20%): % of units affected
    4. Persistence (10%): Unresolved violations over time
    """
    print("\nCalculating harm scores...")
    
    # Collect merged data (needed for complex calculations)
    merged_df = merged.collect()
    networks_collected = networks_df.clone()
    
    # Create severity weights mapping
    merged_df = merged_df.with_columns([
        pl.when(pl.col('class') == 'C')
        .then(pl.lit(5.0))
        .when(pl.col('class') == 'B')
        .then(pl.lit(2.5))
        .otherwise(pl.lit(1.0))
        .alias('severity_weight')
    ])
    
    # Prepare harm scores list
    harm_scores = []
    
    for row in networks_collected.iter_rows(named=True):
        owner_id = row['owner_identifier']
        reg_ids = row['registration_ids']
        
        # Filter violations for this owner
        owner_violations = merged_df.filter(
            pl.col('registrationid').is_in(reg_ids)
        )
        
        if len(owner_violations) == 0:
            continue
        
        # Calculate metrics using Polars aggregations
        metrics = owner_violations.select([
            pl.col('UnitsRes').sum().alias('total_units'),
            pl.col('BBL').n_unique().alias('unique_bbls'),
            pl.col('severity_weight').sum().alias('severity_score'),
            pl.len().alias('total_violations'),
            pl.col('class').filter(pl.col('class') == 'C').count().alias('class_c_count'),
            pl.col('violationstatus')
            .filter(pl.col('violationstatus') != 'Close')
            .count()
            .alias('unresolved_count')
        ]).row(0, named=True)
        
        total_units = max(metrics['total_units'] or 1, 1)
        unique_bbls = metrics['unique_bbls']
        severity_score = metrics['severity_score']
        total_violations = metrics['total_violations']
        unresolved_count = metrics['unresolved_count']
        
        # Calculate component scores
        density_score = total_violations / total_units
        widespread_score = unique_bbls / max(len(reg_ids), 1)
        persistence_score = unresolved_count / max(total_violations, 1)
        
        # Calculate weighted total harm score
        total_harm = (
            severity_score * 0.4 +
            (density_score * 100) * 0.3 +
            (widespread_score * 100) * 0.2 +
            (persistence_score * 100) * 0.1
        )
        
        harm_scores.append({
            'owner_identifier': owner_id,
            'total_harm_score': total_harm,
            'num_properties': len(reg_ids),
            'total_violations': total_violations,
            'severity_score': severity_score,
            'density_score': density_score,
            'widespread_score': widespread_score,
            'persistence_score': persistence_score,
            'total_units': total_units,
            'class_c_violations': metrics['class_c_count'],
            'unresolved_violations': unresolved_count
        })
    
    # Convert to Polars DataFrame
    harm_df = pl.DataFrame(harm_scores)
    harm_df = harm_df.sort('total_harm_score', descending=True)
    
    print(f"Calculated harm scores for {len(harm_df)} owners")
    return harm_df

# ============================================================================
# SECTION 5: VISUALIZATION FUNCTIONS
# ============================================================================

def create_visualizations_polars(harm_df, merged):
    """
    Generate comprehensive visualizations using Polars data.
    Convert to pandas only for plotting.
    """
    print("\nGenerating visualizations...")
    
    # Collect data for visualization
    harm_pd = harm_df.to_pandas()
    merged_pd = merged.collect().to_pandas()
    
    # Visualization 1: Top 20 Landlords by Harm Score
    plt.figure(figsize=(14, 8))
    top_20 = harm_pd.head(20)
    plt.barh(range(len(top_20)), top_20['total_harm_score'])
    plt.yticks(range(len(top_20)), top_20['owner_identifier'], fontsize=8)
    plt.xlabel('Total Harm Score')
    plt.title('Top 20 Landlords by Harm Score')
    plt.tight_layout()
    plt.savefig('top_landlords_harm_score.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # Visualization 2: Violation Distribution by Class
    plt.figure(figsize=(10, 6))
    violation_classes = merged_pd['class'].value_counts()
    plt.bar(violation_classes.index, violation_classes.values, color=['#2ecc71', '#f39c12', '#e74c3c'])
    plt.xlabel('Violation Class')
    plt.ylabel('Count')
    plt.title('Distribution of Violation Classes')
    plt.savefig('violation_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # Visualization 3: Scatter - Properties vs Violations
    plt.figure(figsize=(12, 8))
    plt.scatter(
        harm_pd['num_properties'], 
        harm_pd['total_violations'],
        alpha=0.6,
        s=harm_pd['total_harm_score']/10,
        c=harm_pd['class_c_violations'],
        cmap='YlOrRd'
    )
    plt.xlabel('Number of Properties')
    plt.ylabel('Total Violations')
    plt.title('Properties vs Violations (size = harm score, color = Class C count)')
    plt.colorbar(label='Class C Violations')
    plt.savefig('properties_violations_scatter.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # Visualization 4: Heatmap of Harm Components
    plt.figure(figsize=(12, 10))
    top_10 = harm_pd.head(10)
    heatmap_data = top_10[[
        'severity_score', 'density_score', 
        'widespread_score', 'persistence_score'
    ]].T
    heatmap_data.columns = top_10['owner_identifier']
    sns.heatmap(heatmap_data, annot=True, fmt='.2f', cmap='YlOrRd')
    plt.title('Harm Score Components - Top 10 Landlords')
    plt.tight_layout()
    plt.savefig('harm_components_heatmap.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print("✓ Visualizations saved!")

# ============================================================================
# SECTION 6: MAIN ANALYSIS PIPELINE
# ============================================================================

def main_analysis_polars():
    """
    Main analysis pipeline using Polars and Parquet.
    """
    print("="*70)
    print("NYAG LANDLORD INVESTIGATION ANALYSIS")
    print("Using Polars + Parquet for optimized performance")
    print("="*70)
    
    # Step 0: Convert to Parquet (run once)
    # Uncomment to download and convert data
    # download_and_convert_to_parquet()
    
    # Step 1: Load data with lazy evaluation
    violations, registrations, contacts = load_parquet_data()
    pluto = load_pluto_parquet()  # Optional
    
    # Step 2: Link datasets (still lazy until collect())
    merged = link_datasets_polars(violations, registrations, contacts, pluto)
    
    # Step 3: Identify ownership networks
    networks_df = identify_owner_networks_polars(contacts, registrations)
    
    # Step 4: Calculate harm scores
    harm_df = calculate_harm_score_polars(merged, networks_df)
    
    # Step 5: Generate visualizations
    create_visualizations_polars(harm_df, merged)
    
    # Step 6: Export results
    print("\nExporting results...")
    
    # Export top 10 to Parquet (preserves types)
    harm_df.head(10).write_parquet(
        'top_10_landlords_for_investigation.parquet',
        compression='zstd'
    )
    
    # Also export to CSV for easy viewing
    harm_df.head(10).write_csv('top_10_landlords_for_investigation.csv')
    
    # Export full results
    harm_df.write_parquet(
        'all_landlords_harm_scores.parquet',
        compression='zstd'
    )
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    print(f"\nTop 10 Landlords:")
    print(harm_df.head(10).select([
        'owner_identifier',
        'num_properties',
        'total_violations',
        'class_c_violations',
        'total_harm_score'
    ]))
    
    return harm_df, merged, networks_df

# ============================================================================
# SECTION 7: PERFORMANCE COMPARISON UTILITIES
# ============================================================================

def benchmark_polars_vs_pandas():
    """
    Benchmark Polars vs Pandas performance.
    """
    import time
    import pandas as pd
    
    print("\n" + "="*70)
    print("PERFORMANCE BENCHMARK: Polars vs Pandas")
    print("="*70)
    
    # Test 1: Reading Parquet
    print("\nTest 1: Reading Parquet file...")
    
    start = time.time()
    df_polars = pl.read_parquet('hpd_violations.parquet')
    polars_time = time.time() - start
    print(f"Polars: {polars_time:.3f} seconds")
    
    start = time.time()
    df_pandas = pd.read_parquet('hpd_violations.parquet')
    pandas_time = time.time() - start
    print(f"Pandas: {pandas_time:.3f} seconds")
    print(f"Speedup: {pandas_time/polars_time:.2f}x faster with Polars")
    
    # Test 2: Filtering
    print("\nTest 2: Filtering operations...")
    
    start = time.time()
    filtered_polars = df_polars.filter(
        (pl.col('class') == 'C') & 
        (pl.col('boroid') == '1')
    )
    polars_time = time.time() - start
    print(f"Polars: {polars_time:.4f} seconds")
    
    start = time.time()
    filtered_pandas = df_pandas[
        (df_pandas['class'] == 'C') & 
        (df_pandas['boroid'] == '1')
    ]
    pandas_time = time.time() - start
    print(f"Pandas: {pandas_time:.4f} seconds")
    print(f"Speedup: {pandas_time/polars_time:.2f}x faster with Polars")
    
    # Test 3: Group by aggregation
    print("\nTest 3: Group by aggregation...")
    
    start = time.time()
    grouped_polars = df_polars.group_by('BBL').agg([
        pl.col('violationid').count().alias('count'),
        pl.col('class').filter(pl.col('class') == 'C').count().alias('class_c')
    ])
    polars_time = time.time() - start
    print(f"Polars: {polars_time:.4f} seconds")
    
    start = time.time()
    grouped_pandas = df_pandas.groupby('BBL').agg({
        'violationid': 'count',
        'class': lambda x: (x == 'C').sum()
    })
    pandas_time = time.time() - start
    print(f"Pandas: {pandas_time:.4f} seconds")
    print(f"Speedup: {pandas_time/polars_time:.2f}x faster with Polars")
    
    print("\n" + "="*70)

# ============================================================================
# EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n🚀 Starting NYAG Analysis with Polars + Parquet\n")
    
    # Check if Parquet files exist
    required_files = [
        'hpd_violations.parquet',
        'hpd_registrations.parquet',
        'hpd_contacts.parquet'
    ]
    
    missing_files = [f for f in required_files if not Path(f).exists()]
    
    if missing_files:
        print("⚠️  Missing Parquet files:")
        for f in missing_files:
            print(f"   - {f}")
        print("\nTo get started:")
        print("1. Uncomment download_and_convert_to_parquet() in main_analysis_polars()")
        print("2. Or manually download CSVs and convert:")
        print("   df = pl.read_csv('file.csv')")
        print("   df.write_parquet('file.parquet', compression='zstd')")
    else:
        # Run main analysis
        harm_df, merged, networks = main_analysis_polars()
        
        # Optional: Run benchmark
        # benchmark_polars_vs_pandas()