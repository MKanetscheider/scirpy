from anndata import AnnData
from typing import Dict
from .._util import _is_na
import numpy as np


def clip_and_count(
    adata: AnnData,
    groupby: str,
    target_col: str,
    *,
    clip_at: int = 3,
    fraction: bool = True,
) -> Dict:
    """Counts the number of identical entries in `target_col` 
    for each group in `group_by`. 

    Ignores NaN values. 
    
    Parameters
    ----------
    adata
        AnnData object to work on
    groupby
        Group by this column from `obs`
    target_col
        Column to count on.
    clip_at
        All entries in `target_col` with more copies than `clip_at`
        will be summarized into a single group.         
    fraction
        If True, compute fractions rather than reporting
        abosolute numbers.

    Returns
    -------
    Dictionary with counts/fractions per group 
    """
    if target_col not in adata.obs.columns:
        raise ValueError("`target_col` not found in obs.")
    # count abundance of each clonotype
    tcr_obs = adata.obs.loc[~_is_na(adata.obs[target_col]), :]
    clonotype_counts = (
        tcr_obs.groupby([groupby, target_col]).size().reset_index(name="count")
    )
    clonotype_counts.loc[clonotype_counts["count"] >= clip_at, "count"] = clip_at

    result_dict = dict()
    for group in clonotype_counts[groupby].unique():
        result_dict[group] = dict()
        for n in range(1, clip_at + 1):
            label = ">= {}".format(n) if n == clip_at else str(n)
            mask_group = clonotype_counts[groupby] == group
            mask_count = clonotype_counts["count"] == n
            tmp_count = np.sum(mask_group & mask_count)
            if fraction:
                tmp_count /= np.sum(mask_group)
            result_dict[group][label] = tmp_count

    return result_dict
