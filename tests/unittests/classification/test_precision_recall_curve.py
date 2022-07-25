# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from functools import partial

import numpy as np
import pytest
import torch
from scipy.special import expit as sigmoid
from scipy.special import softmax
from sklearn.metrics import precision_recall_curve as sk_precision_recall_curve

from torchmetrics.classification.precision_recall_curve import (
    BinaryPrecisionRecallCurve,
    MulticlassPrecisionRecallCurve,
)
from torchmetrics.functional.classification.precision_recall_curve import (
    binary_precision_recall_curve,
    multiclass_precision_recall_curve,
    multilabel_precision_recall_curve,
)
from torchmetrics.utilities.imports import _TORCH_GREATER_EQUAL_1_6
from unittests.classification.inputs import _binary_cases, _multiclass_cases, _multilabel_cases
from unittests.helpers import seed_all
from unittests.helpers.testers import NUM_CLASSES, MetricTester, inject_ignore_index, remove_ignore_index

seed_all(42)


def _sk_precision_recall_curve_binary(preds, target, ignore_index=None):
    preds = preds.flatten().numpy()
    target = target.flatten().numpy()
    if np.issubdtype(preds.dtype, np.floating):
        if not ((0 < preds) & (preds < 1)).all():
            preds = sigmoid(preds)
    target, preds = remove_ignore_index(target, preds, ignore_index)
    return sk_precision_recall_curve(target, preds)


@pytest.mark.parametrize("input", (_binary_cases[1], _binary_cases[2], _binary_cases[4], _binary_cases[5]))
class TestBinaryPrecisionRecallCurve(MetricTester):
    @pytest.mark.parametrize("ignore_index", [None, -1, 0])
    @pytest.mark.parametrize("ddp", [True, False])
    def test_binary_precision_recall_curve(self, input, ddp, ignore_index):
        preds, target = input
        if ignore_index is not None:
            target = inject_ignore_index(target, ignore_index)
        self.run_class_metric_test(
            ddp=ddp,
            preds=preds,
            target=target,
            metric_class=BinaryPrecisionRecallCurve,
            sk_metric=partial(_sk_precision_recall_curve_binary, ignore_index=ignore_index),
            metric_args={
                "thresholds": None,
                "ignore_index": ignore_index,
            },
        )

    @pytest.mark.parametrize("ignore_index", [None, -1, 0])
    def test_binary_precision_recall_curve_functional(self, input, ignore_index):
        preds, target = input
        if ignore_index is not None:
            target = inject_ignore_index(target, ignore_index)
        self.run_functional_metric_test(
            preds=preds,
            target=target,
            metric_functional=binary_precision_recall_curve,
            sk_metric=partial(_sk_precision_recall_curve_binary, ignore_index=ignore_index),
            metric_args={
                "thresholds": None,
                "ignore_index": ignore_index,
            },
        )

    def test_binary_precision_recall_curve_differentiability(self, input):
        preds, target = input
        self.run_differentiability_test(
            preds=preds,
            target=target,
            metric_module=BinaryPrecisionRecallCurve,
            metric_functional=binary_precision_recall_curve,
            metric_args={"thresholds": None},
        )

    @pytest.mark.parametrize("dtype", [torch.half, torch.double])
    def test_binary_precision_recall_curve_dtype_cpu(self, input, dtype):
        preds, target = input
        if dtype == torch.half and not _TORCH_GREATER_EQUAL_1_6:
            pytest.xfail(reason="half support of core ops not support before pytorch v1.6")
        if (preds < 0).any() and dtype == torch.half:
            pytest.xfail(reason="torch.sigmoid in metric does not support cpu + half precision")
        self.run_precision_test_cpu(
            preds=preds,
            target=target,
            metric_module=BinaryPrecisionRecallCurve,
            metric_functional=binary_precision_recall_curve,
            metric_args={"thresholds": None},
            dtype=dtype,
        )

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="test requires cuda")
    @pytest.mark.parametrize("dtype", [torch.half, torch.double])
    def test_binary_precision_recall_curve_dtype_gpu(self, input, dtype):
        preds, target = input
        self.run_precision_test_gpu(
            preds=preds,
            target=target,
            metric_module=BinaryPrecisionRecallCurve,
            metric_functional=binary_precision_recall_curve,
            metric_args={"thresholds": None},
            dtype=dtype,
        )

    def test_binary_precision_recall_curve_threshold_arg(self, input):
        preds, target = input

        precision, recall, thresholds = binary_precision_recall_curve(
            preds[0],
            target[0],
            thresholds=None,
        )
        precision_tensor, recall_tensor, thresholds_tensor = binary_precision_recall_curve(
            preds[0],
            target[0],
            thresholds=thresholds,
        )
        precision_list, recall_list, thresholds_list = binary_precision_recall_curve(
            preds[0],
            target[0],
            thresholds=thresholds.numpy().tolist(),
        )
        assert torch.allclose(precision_tensor, precision)
        assert torch.allclose(recall_tensor, recall)
        assert torch.allclose(thresholds_tensor, thresholds)
        assert torch.allclose(precision_list, precision)
        assert torch.allclose(recall_list, recall)
        assert torch.allclose(thresholds_list, thresholds)


def _sk_precision_recall_curve_multiclass(preds, target, ignore_index=None):
    preds = np.moveaxis(preds.numpy(), 1, -1).reshape((-1, preds.shape[1]))
    target = target.numpy().flatten()
    if not ((0 < preds) & (preds < 1)).all():
        preds = softmax(preds, 1)
    target, preds = remove_ignore_index(target, preds, ignore_index)

    precision, recall, thresholds = [], [], []
    for i in range(NUM_CLASSES):
        target_temp = np.zeros_like(target)
        target_temp[target == i] = 1
        res = sk_precision_recall_curve(target_temp, preds[:, i])
        precision.append(res[0])
        recall.append(res[1])
        thresholds.append(res[2])
    return precision, recall, thresholds


@pytest.mark.parametrize(
    "input", (_multiclass_cases[1], _multiclass_cases[2], _multiclass_cases[4], _multiclass_cases[5])
)
class TestMulticlassPrecisionRecallCurve(MetricTester):
    @pytest.mark.parametrize("ignore_index", [None, -1, 0])
    @pytest.mark.parametrize("ddp", [True, False])
    def test_multiclass_precision_recall_curve(self, input, ddp, ignore_index):
        preds, target = input
        if ignore_index is not None:
            target = inject_ignore_index(target, ignore_index)
        self.run_class_metric_test(
            ddp=ddp,
            preds=preds,
            target=target,
            metric_class=MulticlassPrecisionRecallCurve,
            sk_metric=partial(_sk_precision_recall_curve_multiclass, ignore_index=ignore_index),
            metric_args={
                "thresholds": None,
                "num_classes": NUM_CLASSES,
                "ignore_index": ignore_index,
            },
        )

    @pytest.mark.parametrize("ignore_index", [None, -1, 0])
    def test_multiclass_precision_recall_curve_functional(self, input, ignore_index):
        preds, target = input
        if ignore_index is not None:
            target = inject_ignore_index(target, ignore_index)
        self.run_functional_metric_test(
            preds=preds,
            target=target,
            metric_functional=multiclass_precision_recall_curve,
            sk_metric=partial(_sk_precision_recall_curve_multiclass, ignore_index=ignore_index),
            metric_args={
                "thresholds": None,
                "num_classes": NUM_CLASSES,
                "ignore_index": ignore_index,
            },
        )

    def test_multiclass_precision_recall_curve_differentiability(self, input):
        preds, target = input
        self.run_differentiability_test(
            preds=preds,
            target=target,
            metric_module=MulticlassPrecisionRecallCurve,
            metric_functional=multiclass_precision_recall_curve,
            metric_args={"thresholds": None, "num_classes": NUM_CLASSES},
        )

    @pytest.mark.parametrize("dtype", [torch.half, torch.double])
    def test_multiclass_precision_recall_curve_dtype_cpu(self, input, dtype):
        preds, target = input
        if dtype == torch.half and not _TORCH_GREATER_EQUAL_1_6:
            pytest.xfail(reason="half support of core ops not support before pytorch v1.6")
        if dtype == torch.half and not ((0 < preds) & (preds < 1)).all():
            pytest.xfail(reason="half support for torch.softmax on cpu not implemented")
        self.run_precision_test_cpu(
            preds=preds,
            target=target,
            metric_module=MulticlassPrecisionRecallCurve,
            metric_functional=multiclass_precision_recall_curve,
            metric_args={"thresholds": None, "num_classes": NUM_CLASSES},
            dtype=dtype,
        )

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="test requires cuda")
    @pytest.mark.parametrize("dtype", [torch.half, torch.double])
    def test_multiclass_precision_recall_curve_dtype_gpu(self, input, dtype):
        preds, target = input
        self.run_precision_test_gpu(
            preds=preds,
            target=target,
            metric_module=MulticlassPrecisionRecallCurve,
            metric_functional=multiclass_precision_recall_curve,
            metric_args={"thresholds": None, "num_classes": NUM_CLASSES},
            dtype=dtype,
        )


def _sk_precision_recall_curve_multilabel(preds, target, ignore_index=None):
    precision, recall, thresholds = [], [], []
    for i in range(NUM_CLASSES):
        res = _sk_precision_recall_curve_binary(preds[:, i], target[:, i], ignore_index)
        precision.append(res[0])
        recall.append(res[1])
        thresholds.append(res[2])
    return precision, recall, thresholds


@pytest.mark.parametrize(
    "input", (_multilabel_cases[1], _multilabel_cases[2], _multilabel_cases[4], _multilabel_cases[5])
)
class TestMultilabelPrecisionRecallCurve(MetricTester):
    # @pytest.mark.parametrize("ignore_index", [None, -1, 0])
    # @pytest.mark.parametrize("ddp", [True, False])
    # def test_multilabel_precision_recall_curve(self, input, ddp, ignore_index):
    #     preds, target = input
    #     if ignore_index is not None:
    #         target = inject_ignore_index(target, ignore_index)
    #     self.run_class_metric_test(
    #         ddp=ddp,
    #         preds=preds,
    #         target=target,
    #         metric_class=MultilabelPrecisionRecallCurve,
    #         sk_metric=partial(_sk_precision_recall_curve_multilabel, ignore_index=ignore_index),
    #         metric_args={
    #             "thresholds": None,
    #             "num_classes": NUM_CLASSES,
    #             "ignore_index": ignore_index,
    #         },
    #     )

    @pytest.mark.parametrize("ignore_index", [None, -1, 0])
    def test_multilabel_precision_recall_curve_functional(self, input, ignore_index):
        preds, target = input
        if ignore_index is not None:
            target = inject_ignore_index(target, ignore_index)
        self.run_functional_metric_test(
            preds=preds,
            target=target,
            metric_functional=multilabel_precision_recall_curve,
            sk_metric=partial(_sk_precision_recall_curve_multilabel, ignore_index=ignore_index),
            metric_args={
                "thresholds": None,
                "num_labels": NUM_CLASSES,
                "ignore_index": ignore_index,
            },
        )

    # def test_multiclass_precision_recall_curve_differentiability(self, input):
    #     preds, target = input
    #     self.run_differentiability_test(
    #         preds=preds,
    #         target=target,
    #         metric_module=MultilabelPrecisionRecallCurve,
    #         metric_functional=multilabel_precision_recall_curve,
    #         metric_args={"thresholds": None, "num_labels": NUM_CLASSES},
    #     )

    # @pytest.mark.parametrize("dtype", [torch.half, torch.double])
    # def test_multilabel_precision_recall_curve_dtype_cpu(self, input, dtype):
    #     preds, target = input
    #     if dtype == torch.half and not _TORCH_GREATER_EQUAL_1_6:
    #         pytest.xfail(reason="half support of core ops not support before pytorch v1.6")
    #     if dtype == torch.half and not ((0 < preds) & (preds < 1)).all():
    #         pytest.xfail(reason="half support for torch.softmax on cpu not implemented")
    #     self.run_precision_test_cpu(
    #         preds=preds,
    #         target=target,
    #         metric_module=MultilabelsPrecisionRecallCurve,
    #         metric_functional=multilabel_precision_recall_curve,
    #         metric_args={"thresholds": None, "num_labels": NUM_CLASSES},
    #         dtype=dtype,
    #     )

    # @pytest.mark.skipif(not torch.cuda.is_available(), reason="test requires cuda")
    # @pytest.mark.parametrize("dtype", [torch.half, torch.double])
    # def test_multiclass_precision_recall_curve_dtype_gpu(self, input, dtype):
    #     preds, target = input
    #     self.run_precision_test_gpu(
    #         preds=preds,
    #         target=target,
    #         metric_module=MultilabelPrecisionRecallCurve,
    #         metric_functional=multilabel_precision_recall_curve,
    #         metric_args={"thresholds": None, "num_classes": NUM_CLASSES},
    #         dtype=dtype,
    #     )


# -------------------------- Old stuff --------------------------


# def _sk_precision_recall_curve(y_true, probas_pred, num_classes=1):
#     """Adjusted comparison function that can also handles multiclass."""
#     if num_classes == 1:
#         return sk_precision_recall_curve(y_true, probas_pred)

#     precision, recall, thresholds = [], [], []
#     for i in range(num_classes):
#         y_true_temp = np.zeros_like(y_true)
#         y_true_temp[y_true == i] = 1
#         res = sk_precision_recall_curve(y_true_temp, probas_pred[:, i])
#         precision.append(res[0])
#         recall.append(res[1])
#         thresholds.append(res[2])
#     return precision, recall, thresholds


# def _sk_prec_rc_binary_prob(preds, target, num_classes=1):
#     sk_preds = preds.view(-1).numpy()
#     sk_target = target.view(-1).numpy()

#     return _sk_precision_recall_curve(y_true=sk_target, probas_pred=sk_preds, num_classes=num_classes)


# def _sk_prec_rc_multiclass_prob(preds, target, num_classes=1):
#     sk_preds = preds.reshape(-1, num_classes).numpy()
#     sk_target = target.view(-1).numpy()

#     return _sk_precision_recall_curve(y_true=sk_target, probas_pred=sk_preds, num_classes=num_classes)


# def _sk_prec_rc_multidim_multiclass_prob(preds, target, num_classes=1):
#     sk_preds = preds.transpose(0, 1).reshape(num_classes, -1).transpose(0, 1).numpy()
#     sk_target = target.view(-1).numpy()
#     return _sk_precision_recall_curve(y_true=sk_target, probas_pred=sk_preds, num_classes=num_classes)


# @pytest.mark.parametrize(
#     "preds, target, sk_metric, num_classes",
#     [
#         (_input_binary_prob.preds, _input_binary_prob.target, _sk_prec_rc_binary_prob, 1),
#         (_input_mcls_prob.preds, _input_mcls_prob.target, _sk_prec_rc_multiclass_prob, NUM_CLASSES),
#         (_input_mdmc_prob.preds, _input_mdmc_prob.target, _sk_prec_rc_multidim_multiclass_prob, NUM_CLASSES),
#     ],
# )
# class TestPrecisionRecallCurve(MetricTester):
#     @pytest.mark.parametrize("ddp", [True, False])
#     @pytest.mark.parametrize("dist_sync_on_step", [True, False])
#     def test_precision_recall_curve(self, preds, target, sk_metric, num_classes, ddp, dist_sync_on_step):
#         self.run_class_metric_test(
#             ddp=ddp,
#             preds=preds,
#             target=target,
#             metric_class=PrecisionRecallCurve,
#             sk_metric=partial(sk_metric, num_classes=num_classes),
#             dist_sync_on_step=dist_sync_on_step,
#             metric_args={"num_classes": num_classes},
#         )

#     def test_precision_recall_curve_functional(self, preds, target, sk_metric, num_classes):
#         self.run_functional_metric_test(
#             preds,
#             target,
#             metric_functional=precision_recall_curve,
#             sk_metric=partial(sk_metric, num_classes=num_classes),
#             metric_args={"num_classes": num_classes},
#         )

#     def test_precision_recall_curve_differentiability(self, preds, target, sk_metric, num_classes):
#         self.run_differentiability_test(
#             preds,
#             target,
#             metric_module=PrecisionRecallCurve,
#             metric_functional=precision_recall_curve,
#             metric_args={"num_classes": num_classes},
#         )


# @pytest.mark.parametrize(
#     ["pred", "target", "expected_p", "expected_r", "expected_t"],
#     [([1, 2, 3, 4], [1, 0, 0, 1], [0.5, 1 / 3, 0.5, 1.0, 1.0], [1, 0.5, 0.5, 0.5, 0.0], [1, 2, 3, 4])],
# )
# def test_pr_curve(pred, target, expected_p, expected_r, expected_t):
#     p, r, t = precision_recall_curve(tensor(pred), tensor(target))
#     assert p.size() == r.size()
#     assert p.size(0) == t.size(0) + 1

#     assert torch.allclose(p, tensor(expected_p).to(p))
#     assert torch.allclose(r, tensor(expected_r).to(r))
#     assert torch.allclose(t, tensor(expected_t).to(t))


# @pytest.mark.parametrize(
#     "sample_weight, pos_label, exp_shape",
#     [(1, 1.0, 42), (None, 1.0, 42)],
# )
# def test_binary_clf_curve(sample_weight, pos_label, exp_shape):
#     # TODO: move back the pred and target to test func arguments
#     #  if you fix the array inside the function, you'd also have fix the shape,
#     #  because when the array changes, you also have to fix the shape
#     seed_all(0)
#     pred = torch.randint(low=51, high=99, size=(100,), dtype=torch.float) / 100
#     target = tensor([0, 1] * 50, dtype=torch.int)
#     if sample_weight is not None:
#         sample_weight = torch.ones_like(pred) * sample_weight

#     fps, tps, thresh = _binary_clf_curve(preds=pred, target=target, sample_weights=sample_weight, pos_label=pos_label)

#     assert isinstance(tps, Tensor)
#     assert isinstance(fps, Tensor)
#     assert isinstance(thresh, Tensor)
#     assert tps.shape == (exp_shape,)
#     assert fps.shape == (exp_shape,)
#     assert thresh.shape == (exp_shape,)
