import pytest
from scirpy.ir_dist.metrics import DistanceCalculator
from scirpy.ir_dist._clonotype_neighbors import ClonotypeNeighbors
import numpy as np
import numpy.testing as npt
import scirpy as ir
import scipy.sparse
from .fixtures import adata_cdr3, adata_cdr3_2  # NOQA
from .util import _squarify
from scirpy.util import _is_symmetric
import pandas.testing as pdt
import pandas as pd
from anndata import AnnData


def _assert_frame_equal(left, right):
    """alias to pandas.testing.assert_frame_equal configured for the tests in this file"""
    pdt.assert_frame_equal(left, right, check_dtype=False, check_categorical=False)


@pytest.fixture
def adata_cdr3_mock_distance_calculator():
    class MockDistanceCalculator(DistanceCalculator):
        def __init__(self, n_jobs=None):
            pass

        def calc_dist_mat(self, seqs, seqs2=None):
            """Don't calculate distances, but return the
            hard-coded distance matrix needed for the test"""
            mat_seqs = np.array(["AAA", "AHA", "KK", "KKK", "KKY", "LLL"])
            mask = np.isin(mat_seqs, seqs)
            dist_mat = scipy.sparse.csr_matrix(
                np.array(
                    [
                        [1, 4, 0, 0, 0, 0],
                        [4, 1, 0, 0, 0, 0],
                        [0, 0, 1, 10, 10, 0],
                        [0, 0, 10, 1, 5, 0],
                        [0, 0, 10, 5, 1, 0],
                        [0, 0, 0, 0, 0, 1],
                    ]
                )[mask, :][:, mask]
            )
            assert _is_symmetric(dist_mat)
            return dist_mat

    return MockDistanceCalculator()


@pytest.mark.parametrize(
    "metric,cutoff,expected_square,expected",
    [
        (
            "identity",
            0,
            _squarify(
                [
                    [1, 0, 0, 0, 1],
                    [0, 1, 0, 0, 0],
                    [0, 0, 1, 1, 0],
                    [0, 0, 0, 1, 0],
                    [0, 0, 0, 0, 1],
                ]
            ),
            [
                [0, 0, 1, 0],
                [1, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 1, 0],
            ],
        ),
        (
            "levenshtein",
            10,
            _squarify(
                [
                    [1, 2, 3, 3, 1],
                    [0, 1, 3, 3, 2],
                    [0, 0, 1, 1, 3],
                    [0, 0, 0, 1, 3],
                    [0, 0, 0, 0, 1],
                ]
            ),
            [
                [2, 3, 1, 3],
                [1, 4, 2, 4],
                [3, 4, 3, 4],
                [3, 4, 3, 4],
                [2, 3, 1, 3],
            ],
        ),
    ],
)
def test_sequence_dist(metric, cutoff, expected_square, expected):
    seqs1 = np.array(["AAA", "ARA", "FFA", "FFA", "AAA"])
    seqs2 = np.array(["ARA", "CAC", "AAA", "CAC"])

    res = ir.ir_dist.sequence_dist(seqs1, metric=metric, cutoff=cutoff)
    npt.assert_almost_equal(res.toarray(), np.array(expected_square))

    res = ir.ir_dist.sequence_dist(seqs1, seqs2, metric=metric, cutoff=cutoff)
    res_t = ir.ir_dist.sequence_dist(seqs2, seqs1, metric=metric, cutoff=cutoff)
    npt.assert_almost_equal(
        res.toarray(),
        np.array(expected),
    )
    npt.assert_almost_equal(
        res_t.toarray(),
        np.array(expected).T,
    )


@pytest.mark.parametrize(
    "metric,expected_key,expected_dist_vj,expected_dist_vdj",
    [
        (
            "identity",
            "ir_dist_aa_identity",
            np.identity(2),
            np.identity(5),
        ),
        (
            "mock",
            "ir_dist_aa_custom",
            np.array([[1, 4], [4, 1]]),
            np.array(
                [
                    [1, 0, 0, 0, 0],
                    [0, 1, 10, 10, 0],
                    [0, 10, 1, 5, 0],
                    [0, 10, 5, 1, 0],
                    [0, 0, 0, 0, 1],
                ]
            ),
        ),
    ],
)
def test_ir_dist(
    adata_cdr3,
    adata_cdr3_mock_distance_calculator,
    metric,
    expected_key,
    expected_dist_vj,
    expected_dist_vdj,
):
    expected_seq_vj = np.array(["AAA", "AHA"])
    expected_seq_vdj = np.array(["AAA", "KK", "KKK", "KKY", "LLL"])
    ir.pp.ir_dist(
        adata_cdr3,
        metric=metric if metric != "mock" else adata_cdr3_mock_distance_calculator,
        sequence="aa",
    )
    res = adata_cdr3.uns[expected_key]
    npt.assert_array_equal(res["VJ"]["seqs"], expected_seq_vj)
    npt.assert_array_equal(res["VDJ"]["seqs"], expected_seq_vdj)
    npt.assert_array_equal(res["VJ"]["distances"].toarray(), expected_dist_vj)
    npt.assert_array_equal(res["VDJ"]["distances"].toarray(), expected_dist_vdj)


@pytest.mark.parametrize("with_adata2", [False, True])
@pytest.mark.parametrize("n_jobs", [1, 2])
@pytest.mark.parametrize(
    "comment,metric,ctn_kwargs,expected_clonotype_df,expected_dist",
    (
        [
            "test single chain with identity distance",
            "identity",
            {"receptor_arms": "VJ", "dual_ir": "primary_only"},
            {"IR_VJ_1_junction_aa": ["AAA", "AHA", "nan"]},
            [
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 0],
            ],
        ],
        [
            """test single receptor arm with multiple chains and identity distance""",
            "identity",
            {"receptor_arms": "VJ", "dual_ir": "any"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
            },
            [
                [1, 1, 0, 1, 1],
                [1, 1, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [1, 0, 0, 1, 1],
                [1, 0, 0, 1, 1],
            ],
        ],
        [
            """test single chain with custom distance""",
            "custom",
            {"receptor_arms": "VJ", "dual_ir": "primary_only"},
            {"IR_VJ_1_junction_aa": ["AAA", "AHA", "nan"]},
            [
                [1, 4, 0],
                [4, 1, 0],
                [0, 0, 0],
            ],
        ],
        [
            """test single receptor arm with multiple chains and custom distance""",
            "custom",
            {"receptor_arms": "VJ", "dual_ir": "any"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
            },
            [
                [1, 1, 0, 1, 1],
                [1, 1, 0, 4, 4],
                [0, 0, 0, 0, 0],
                [1, 4, 0, 1, 1],
                [1, 4, 0, 1, 1],
            ],
        ],
        [
            """test single receptor arm with multiple chains and custom distance""",
            "custom",
            {"receptor_arms": "VJ", "dual_ir": "all"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
            },
            [
                [1, 0, 0, 4, 0],
                [0, 1, 0, 0, 4],
                [0, 0, 0, 0, 0],
                [4, 0, 0, 1, 0],
                [0, 4, 0, 0, 1],
            ],
        ],
        [
            """test both receptor arms, primary chain only""",
            "custom",
            {"receptor_arms": "all", "dual_ir": "primary_only"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL"],
            },
            [
                [1, 10, 0, 0],
                [10, 1, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 1],
            ],
        ],
        [
            """Test with any receptor arms, primary chain only""",
            "custom",
            {"receptor_arms": "any", "dual_ir": "primary_only"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL"],
            },
            [
                [1, 4, 0, 1],
                [4, 1, 0, 4],
                [0, 0, 0, 0],
                [1, 4, 0, 1],
            ],
        ],
        [
            "Test with any receptor arms, all chains",
            "custom",
            {"receptor_arms": "any", "dual_ir": "all"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL", "LLL"],
                "IR_VDJ_2_junction_aa": ["KKK", "KKK", "nan", "AAA", "nan"],
            },
            [
                [1, 10, 0, 4, 0],
                [10, 1, 0, 0, 4],
                [0, 0, 0, 0, 0],
                [4, 0, 0, 1, 0],
                [0, 4, 0, 0, 1],
            ],
        ],
        [
            "Test with any receptor amrms, any chains",
            "custom",
            {"receptor_arms": "any", "dual_ir": "any"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL", "LLL"],
                "IR_VDJ_2_junction_aa": ["KKK", "KKK", "nan", "AAA", "nan"],
            },
            [
                [1, 1, 0, 1, 1],
                [1, 1, 0, 4, 4],
                [0, 0, 0, 0, 0],
                [1, 4, 0, 1, 1],
                [1, 4, 0, 1, 1],
            ],
        ],
        [
            "Test with all receptor arms, any dual ir",
            "custom",
            {"receptor_arms": "all", "dual_ir": "any"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL", "LLL"],
                "IR_VDJ_2_junction_aa": ["KKK", "KKK", "nan", "AAA", "nan"],
            },
            [
                [1, 1, 0, 0, 0],
                [1, 1, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [0, 0, 0, 1, 1],
                [0, 0, 0, 1, 1],
            ],
        ],
        [
            "Test with all receptor amrs, all dual ir",
            "custom",
            {"receptor_arms": "all", "dual_ir": "all"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL", "LLL"],
                "IR_VDJ_2_junction_aa": ["KKK", "KKK", "nan", "AAA", "nan"],
            },
            [
                [1, 0, 0, 0, 0],
                [0, 1, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [0, 0, 0, 1, 0],
                [0, 0, 0, 0, 1],
            ],
        ],
    ),
)
def test_compute_distances(
    adata_cdr3,
    adata_cdr3_mock_distance_calculator,
    comment,
    metric,
    ctn_kwargs,
    expected_clonotype_df,
    expected_dist,
    n_jobs,
    with_adata2,
):
    f"""{comment}"""
    distance_key = f"ir_dist_aa_{metric}"
    metric = adata_cdr3_mock_distance_calculator if metric == "custom" else metric
    adata2 = adata_cdr3 if with_adata2 else None
    expected_dist = np.array(expected_dist)
    ir.pp.ir_dist(
        adata_cdr3, adata2, metric=metric, sequence="aa", key_added=distance_key
    )
    cn = ClonotypeNeighbors(
        adata_cdr3,
        adata2,
        distance_key=distance_key,
        sequence_key="junction_aa",
        n_jobs=n_jobs,
        chunksize=1,
        **ctn_kwargs,
    )
    _assert_frame_equal(cn.clonotypes, pd.DataFrame(expected_clonotype_df))
    dist = cn.compute_distances()
    print(dist)
    assert dist.nnz == np.sum(expected_dist != 0)
    npt.assert_equal(dist.toarray(), expected_dist)


@pytest.mark.parametrize("n_jobs", [1, 2])
@pytest.mark.parametrize("with_adata2", [False, True])
@pytest.mark.parametrize("dual_ir", ["all", "any", "primary_only"])
@pytest.mark.parametrize(
    "receptor_arms,expected",
    [
        (
            "all",
            np.array(
                [
                    [1, 0, 0],
                    [0, 1, 0],
                    [0, 0, 1],
                ]
            ),
        ),
        (
            "any",
            np.array(
                [
                    [1, 1, 0],
                    [1, 1, 1],
                    [0, 1, 1],
                ]
            ),
        ),
        ("VJ", np.array([[1, 0], [0, 0]])),
        ("VDJ", np.array([[1, 0], [0, 1]])),
    ],
)
def test_compute_distances_2(
    adata_cdr3_2,
    adata_cdr3_mock_distance_calculator,
    receptor_arms,
    dual_ir,
    expected,
    n_jobs,
    with_adata2,
):
    """Test that `dual_ir` does not impact the second reduction step"""
    adata2 = adata_cdr3_2 if with_adata2 else None
    ir.pp.ir_dist(
        adata_cdr3_2,
        adata2,
        metric=adata_cdr3_mock_distance_calculator,
        sequence="aa",
        key_added="ir_dist_aa_custom",
    )
    cn = ClonotypeNeighbors(
        adata_cdr3_2,
        adata2,
        receptor_arms=receptor_arms,
        dual_ir=dual_ir,
        distance_key="ir_dist_aa_custom",
        sequence_key="junction_aa",
        n_jobs=n_jobs,
        chunksize=1,
    )
    dist = cn.compute_distances().toarray()
    print(dist)
    npt.assert_equal(dist, expected)


@pytest.mark.parametrize("with_adata2", [False, True])
def test_compute_distances_no_dist(
    adata_cdr3, adata_cdr3_mock_distance_calculator, with_adata2
):
    adata2 = adata_cdr3 if with_adata2 else None
    """Test for #174. Gracefully handle the case when there are no distances."""
    adata_cdr3.obs["IR_VJ_1_junction_aa"] = np.nan
    adata_cdr3.obs["IR_VDJ_1_junction_aa"] = np.nan
    # test both receptor arms, primary chain only
    ir.pp.ir_dist(
        adata_cdr3,
        adata2,
        metric=adata_cdr3_mock_distance_calculator,
        sequence="aa",
        key_added="ir_dist_aa_custom",
    )
    cn = ClonotypeNeighbors(
        adata_cdr3,
        adata2,
        receptor_arms="all",
        dual_ir="primary_only",
        distance_key="ir_dist_aa_custom",
        sequence_key="junction_aa",
    )
    _assert_frame_equal(
        cn.clonotypes,
        pd.DataFrame(
            {
                "IR_VJ_1_junction_aa": ["nan"],
                "IR_VDJ_1_junction_aa": ["nan"],
            }
        ),
    )
    dist = cn.compute_distances()
    npt.assert_equal(dist.toarray(), np.zeros((1, 1)))


def test_compute_distances_no_ir(adata_cdr3, adata_cdr3_mock_distance_calculator):
    """Test for #174. Gracefully handle the case when there are no IR."""
    adata_cdr3.obs["IR_VJ_1_junction_aa"] = np.nan
    adata_cdr3.obs["IR_VDJ_1_junction_aa"] = np.nan
    adata_cdr3.obs["has_ir"] = "False"
    # test both receptor arms, primary chain only
    ir.pp.ir_dist(adata_cdr3, metric=adata_cdr3_mock_distance_calculator, sequence="aa")
    with pytest.raises(ValueError):
        cn = ClonotypeNeighbors(
            adata_cdr3,
            receptor_arms="all",
            dual_ir="primary_only",
            distance_key="ir_dist_aa_custom",
            sequence_key="junction_aa",
        )


@pytest.mark.parametrize("swap_query_reference", [True, False])
@pytest.mark.parametrize(
    "comment,metric,ctn_kwargs,expected_clonotype_df,expected_clonotype_df2,expected_dist",
    (
        [
            "VJ, primary_only",
            "identity",
            {"receptor_arms": "VJ", "dual_ir": "primary_only"},
            {"IR_VJ_1_junction_aa": ["AAA", "AHA", "nan"]},
            {"IR_VJ_1_junction_aa": ["AAA", "nan"]},
            [
                [1, 0],
                [0, 0],
                [0, 0],
            ],
        ],
        [
            "receptor_arms=all, dual_ir=primary_only",
            "identity",
            {"receptor_arms": "all", "dual_ir": "primary_only"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL"],
            },
            {
                "IR_VJ_1_junction_aa": ["AAA", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKK", "LLL", "LLL"],
            },
            [
                [0, 0, 0],
                [0, 0, 0],
                [0, 0, 0],
                [0, 1, 0],
            ],
        ],
        [
            "receptor_arms=all, dual_ir=any",
            "identity",
            {"receptor_arms": "all", "dual_ir": "any"},
            {
                "IR_VJ_1_junction_aa": ["AAA", "AHA", "nan", "AAA", "AAA"],
                "IR_VJ_2_junction_aa": ["AHA", "nan", "nan", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKY", "KK", "nan", "LLL", "LLL"],
                "IR_VDJ_2_junction_aa": ["KKK", "KKK", "nan", "AAA", "nan"],
            },
            {
                "IR_VJ_1_junction_aa": ["AAA", "AAA", "nan"],
                "IR_VJ_2_junction_aa": ["AAA", "AAA", "nan"],
                "IR_VDJ_1_junction_aa": ["KKK", "LLL", "LLL"],
                "IR_VDJ_2_junction_aa": ["KKK", "LLL", "LLL"],
            },
            [
                [1, 0, 0],
                [0, 0, 0],
                [0, 0, 0],
                [0, 1, 0],
                [0, 1, 0],
            ],
        ],
    ),
)
def test_compute_distances_second_anndata(
    adata_cdr3,
    adata_cdr3_2,
    comment,
    metric,
    ctn_kwargs,
    expected_clonotype_df,
    expected_clonotype_df2,
    expected_dist,
    swap_query_reference,
):
    f"""
    Test that the distance calculation works with two different anndata objects
    {comment}
    """
    query = adata_cdr3 if not swap_query_reference else adata_cdr3_2
    reference = adata_cdr3_2 if not swap_query_reference else adata_cdr3
    distance_key = f"ir_dist_aa_{metric}"
    expected_dist = np.array(expected_dist)
    ir.pp.ir_dist(
        query, reference, metric=metric, sequence="aa", key_added=distance_key
    )
    cn = ClonotypeNeighbors(
        query,
        reference,
        distance_key=distance_key,
        sequence_key="junction_aa",
        **ctn_kwargs,
    )
    _assert_frame_equal(
        cn.clonotypes,
        pd.DataFrame(
            expected_clonotype_df
            if not swap_query_reference
            else expected_clonotype_df2
        ),
    )
    _assert_frame_equal(
        cn.clonotypes2,
        pd.DataFrame(
            expected_clonotype_df2
            if not swap_query_reference
            else expected_clonotype_df
        ),
    )
    dist = cn.compute_distances()
    dist = dist.toarray()
    print(dist)
    npt.assert_equal(
        dist, expected_dist if not swap_query_reference else expected_dist.T
    )


@pytest.mark.parametrize("metric", ["identity", "levenshtein", "alignment"])
def test_ir_dist_empty_anndata(adata_cdr3, metric):
    adata_empty = AnnData()
    ir.pp.ir_dist(
        adata_cdr3, adata_empty, metric=metric, sequence="aa", key_added="ir_dist"
    )
    print(adata_cdr3.uns["ir_dist"]["seqs"])
    print(adata_cdr3.uns["ir_dist"]["seqs2"])
    print(adata_cdr3.uns["ir_dist"]["distances"])
