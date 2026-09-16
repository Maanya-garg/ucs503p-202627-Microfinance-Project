"""
Stage 7 (stretch): geo-clustering for the branch-placement heatmap.

Groups districts by their aggregate borrower quality (mean credit score,
default rate, SHG density) using k-means, so a lender/bank can see which
districts look like "expand here" vs "build trust first" at a glance. Small
input (one row per district, ~10 districts in the synthetic dataset) so this
runs on demand from the API rather than needing a persisted results table --
recompute cost is negligible.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.orm import Session

CLUSTER_LABELS_BY_RANK = ["High Trust", "Moderate", "Emerging / Needs Trust-Building"]

DISTRICT_STATS_SQL = """
select
    d.id as district_id, d.name, d.state, d.lat, d.lon,
    count(distinct i.id) as n_borrowers,
    count(distinct case when i.shg_id is not null then i.id end) as n_shg_linked,
    avg(cs.score) as avg_score,
    avg(case when l.status = 'Defaulted' then 1.0 else 0.0 end) as default_rate
from districts d
left join individuals i on i.district_id = d.id
left join (
    select cs1.individual_id, cs1.score
    from credit_scores cs1
    inner join (
        select individual_id, max(calculated_date) as max_date
        from credit_scores group by individual_id
    ) latest on cs1.individual_id = latest.individual_id and cs1.calculated_date = latest.max_date
) cs on cs.individual_id = i.id
left join loans l on l.individual_id = i.id
group by d.id, d.name, d.state, d.lat, d.lon
"""


def cluster_districts(db: Session, n_clusters: int = 3) -> list[dict]:
    rows = db.execute(text(DISTRICT_STATS_SQL)).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        return []

    df["avg_score"] = df["avg_score"].fillna(df["avg_score"].median())
    df["default_rate"] = df["default_rate"].fillna(0.0)
    df["shg_density"] = (df["n_shg_linked"] / df["n_borrowers"].replace(0, np.nan)).fillna(0.0)

    n_clusters = max(1, min(n_clusters, len(df)))
    feature_cols = ["avg_score", "default_rate", "shg_density"]
    X = StandardScaler().fit_transform(df[feature_cols])

    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    df["cluster"] = km.fit_predict(X)

    # Rank clusters by mean avg_score so labels are meaningful ("High Trust" is
    # always the best-scoring cluster), not just an arbitrary k-means index.
    cluster_rank = (
        df.groupby("cluster")["avg_score"].mean().sort_values(ascending=False).index.tolist()
    )
    label_for_cluster = {}
    for rank, cluster_id in enumerate(cluster_rank):
        if n_clusters == len(CLUSTER_LABELS_BY_RANK):
            label_for_cluster[cluster_id] = CLUSTER_LABELS_BY_RANK[rank]
        else:
            label_for_cluster[cluster_id] = f"Cluster {rank + 1}"

    df["cluster_label"] = df["cluster"].map(label_for_cluster)

    return df[[
        "district_id", "name", "state", "lat", "lon", "n_borrowers", "n_shg_linked",
        "avg_score", "default_rate", "shg_density", "cluster", "cluster_label",
    ]].round({"avg_score": 1, "default_rate": 3, "shg_density": 3}).to_dict(orient="records")
