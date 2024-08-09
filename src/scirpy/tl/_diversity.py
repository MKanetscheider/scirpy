from typing import Callable, Literal, Optional, Union, cast

import numpy as np
import pandas as pd

from scirpy.util import DataHandler, _is_na


def _shannon_entropy(counts: np.ndarray):
    """Normalized shannon entropy according to
    https://math.stackexchange.com/a/945172
    """
    freqs = counts / np.sum(counts)
    np.testing.assert_almost_equal(np.sum(freqs), 1)

    if len(freqs) == 1:
        # the formula below is not defined for n==1
        return 0
    else:
        return -np.sum((freqs * np.log(freqs)) / np.log(len(freqs)))


def _dxx(counts: np.ndarray, *, percentage: int):
    """
    D50/DXX according to https://patents.google.com/patent/WO2012097374A1/en

    Parameters
    ----------
    percentage
        Percentage of J
    """
    freqs = counts / np.sum(counts)
    np.testing.assert_almost_equal(np.sum(freqs), 1)

    freqs = np.sort(freqs)[::-1]
    prop, i = 0, 0

    while prop < (percentage / 100):
        prop += freqs[i]
        i += 1

    return i / len(freqs) * 100


def Hill_diversity(counts: np.ndarray, q):
    if q == 0:
        return len(counts)
    if q == 1:
        p_i = counts / sum(counts)
        return np.exp(np.sum(-p_i * np.log(p_i)))
    else:
        p_i = counts / sum(counts)
        return np.power(np.sum(np.power(p_i, q)), 1 / (1 - q))


def hill_diversity_profile(
    adata: DataHandler.TYPE,
    groupby: str,
    target_col: str = "clone_id",
    airr_mod: str = "airr",
    q_min=0,
    q_max=2,
    q_step=1,
) -> pd.DataFrame:
    """\
    Calculates a Hill based diversity profile for a given diversity order (`q`) range

    Parameters
    ----------
    {adata}
    groupby
        Group by this column from `obs`. E.g, sample, or group.
    target_col
        Column containing the clonotype annoatation
    {airr_mod}
    q_min
        Specify lowest diversity order
    q_max
        Specify highest diversity order
    q_step
        Specify the fineness of diversity order calculation

    Returns
    -------
    Returns a pd.DataFrame where columns are groups specified by groupby and rows represent
    all calculated diversity orders -> allows seamlessly potting with seaborn
    """
    params = DataHandler(adata, airr_mod)
    ir_obs = params.get_obs([target_col, groupby])
    ir_obs = ir_obs.loc[~_is_na(ir_obs[target_col]), :]
    clono_counts = ir_obs.groupby([groupby, target_col], observed=True).size().reset_index(name="count")
    diversity = {}

    for q in np.arange(q_min, q_max + q_step, q_step):
        for k in sorted(ir_obs[groupby].dropna().unique()):
            tmp_counts = cast(
                np.ndarray,
                cast(pd.Series, clono_counts.loc[clono_counts[groupby] == k, "count"]).values,
            )
            if k in diversity:
                diversity[k].append(Hill_diversity(tmp_counts, q))
            else:
                diversity[k] = [Hill_diversity(tmp_counts, q)]
    df = pd.DataFrame.from_dict(diversity, orient="index", columns=list(np.arange(q_min, q_max + q_step, q_step)))
    df.index.name = groupby
    return df.T


def convert_hill_table(
    diversity_profile: pd.DataFrame,
    convert_to: Literal["diversity", "evenness_factor", "relative_evenness"] = "diversity",
) -> pd.DataFrame:
    """
    Converts pd.DataFrame generated by scipry.tl.hill_diversity_profile into other relevant alpha indices

    Parameters
    ----------
    diversity_profile
       pd.DataFrame generated by scipry.tl.hill_diversity_profile
    convert_to
       specify which conversion is desired:
           diversity -- infer respective indices from Hill numbers
           evenness_factor -- calculates EF for each diversity order as specified previously
           relative_evenness -- calculates RLE for each diversity order as specified previously

    for more information regarding alpha diversity see https://academic.oup.com/bib/article/19/4/679/2871295

    Returns
    -------
    pd.DataFrame, where rows are indices/diversity orders and columns are groups (i.e. severity)
    """
    if convert_to == "diversity":
        df = pd.DataFrame(
            columns=diversity_profile.columns,
            index=["Observed richness", "Shannon entropy", "Inverse Simpson", "Gini-Simpson"],
        )

        df.loc["Observed richness"] = diversity_profile.loc[0]
        df.loc["Shannon entropy"] = [np.log(x) for x in diversity_profile.loc[1]]
        df.loc["Inverse Simpson"] = diversity_profile.loc[2]
        df.loc["Gini-Simpson"] = [(1 - (1 / x)) for x in diversity_profile.loc[2]]
        return df

    elif convert_to == "evenness_factor":
        df = diversity_profile.copy()
        observed_richeness = diversity_profile.loc[0]
        for _index, row in df.iterrows():
            for i in range(len(row)):
                row.iloc[i] = row.iloc[i] / observed_richeness.iloc[i]
        return df

    elif convert_to == "relative_evenness":
        df = diversity_profile.copy()
        observed_richeness = diversity_profile.loc[0]
        for _index, row in df.iterrows():
            for i in range(len(row)):
                row.iloc[i] = np.log(row.iloc[i]) / np.log(observed_richeness.iloc[i])
        return df

    else:
        raise Exception("Invalid input. Please check your input to the convert_to argument!")


@DataHandler.inject_param_docs()
def alpha_diversity(
    adata: DataHandler.TYPE,
    groupby: str,
    *,
    target_col: str = "clone_id",
    metric: Union[str, Callable[[np.ndarray], Union[int, float]]] = "normalized_shannon_entropy",
    inplace: bool = True,
    key_added: Union[None, str] = None,
    airr_mod: str = "airr",
    **kwargs,
) -> Optional[pd.DataFrame]:
    """\
    Computes the alpha diversity of clonotypes within a group.

    Use a metric out of  `normalized_shannon_entropy`, `D50`, `DXX`, and `scikit-bio’s alpha diversity metrics
    <http://scikit-bio.org/docs/latest/generated/skbio.diversity.alpha.html#module-skbio.diversity.alpha>`__.
    Alternatively, provide a custom function to calculate the diversity based on count vectors
    as explained here `<http://scikit-bio.org/docs/latest/diversity.html>`__

    Normalized shannon entropy:
        Uses the `Shannon Entropy <https://mathworld.wolfram.com/Entropy.html>`__ as
        diversity measure. The Entrotpy gets
        `normalized to group size <https://math.stackexchange.com/a/945172>`__.

    D50:
        The diversity index (D50) is a measure of the diversity of an immune repertoire of J individual cells
        (the total number of CDR3s) composed of S distinct CDR3s in a ranked dominance configuration where ri
        is the abundance of the ith most abundant CDR3, r1 is the abundance of the most abundant CDR3, r2 is the
        abundance of the second most abundant CDR3, and so on. C is the minimum number of distinct CDR3s,
        amounting to >50% of the total sequencing reads. D50 therefore is given by C/S x 100.
        `<https://patents.google.com/patent/WO2012097374A1/en>`__.

    DXX:
        Similar to D50 where XX indicates the percent of J (the total number of CDR3s).
        Requires to pass the `percentage` keyword argument which can be within 0 and
        100.


    Ignores NaN values.

    Parameters
    ----------
    {adata}
    groupby
        Column of `obs` by which the grouping will be performed.
    target_col
        Column on which to compute the alpha diversity
    metric
        A metric used for diversity estimation out of `normalized_shannon_entropy`,
        `D50`, `DXX`, any of scikit-bio’s alpha diversity metrics, or a custom function.
    {inplace}
    {key_added}
        Defaults to `alpha_diversity_{{target_col}}`.
    {airr_mod}
    **kwargs
        Additional arguments passed to the metric function.

    Returns
    -------
    Depending on the value of inplace returns a DataFrame with the alpha diversity
    for each group or adds a column to `adata.obs`.
    """
    params = DataHandler(adata, airr_mod)
    ir_obs = params.get_obs([target_col, groupby])
    ir_obs = ir_obs.loc[~_is_na(ir_obs[target_col]), :]
    clono_counts = ir_obs.groupby([groupby, target_col], observed=True).size().reset_index(name="count")

    diversity = {}
    for k in sorted(ir_obs[groupby].dropna().unique()):
        tmp_counts = cast(
            np.ndarray,
            cast(pd.Series, clono_counts.loc[clono_counts[groupby] == k, "count"]).values,
        )

        if isinstance(metric, str):
            if metric == "normalized_shannon_entropy":
                diversity[k] = _shannon_entropy(tmp_counts)
            elif metric == "D50":
                diversity[k] = _dxx(tmp_counts, percentage=50)
            elif metric == "DXX":
                if "percentage" in kwargs:
                    diversity[k] = _dxx(tmp_counts, percentage=cast(int, kwargs.get("percentage")))
                else:
                    raise ValueError(
                        "DXX requires the `percentage` keyword argument, which can " "range from 0 to 100."
                    )
            else:
                # make skbio an optional dependency
                try:
                    import skbio.diversity
                except ImportError:
                    raise ImportError(
                        "Using scikit-bio’s alpha diversity metrics requires the "
                        "installation of `scikit-bio`. You can install it with "
                        "`pip install scikit-bio`."
                    ) from None
                else:
                    # skbio.diversity takes count vectors as input and
                    # takes care of unknown metrics
                    diversity[k] = skbio.diversity.alpha_diversity(metric, tmp_counts).values[0]
        else:
            # calculate diversity using custom function
            diversity[k] = metric(tmp_counts)

    if inplace:
        metric_name = metric if isinstance(metric, str) else metric.__name__
        key_added = f"{metric_name}_{target_col}" if key_added is None else key_added
        params.set_obs(key_added, params.adata.obs[groupby].map(diversity))
    else:
        return pd.DataFrame().from_dict(diversity, orient="index")
