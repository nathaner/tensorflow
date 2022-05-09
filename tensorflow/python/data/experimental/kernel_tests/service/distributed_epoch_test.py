# Copyright 2020 The TensorFlow Authors. All Rights Reserved.
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
# ==============================================================================
"""Tests for distributed_epoch processing mode."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import parameterized
import numpy as np

from tensorflow.python.data.experimental.kernel_tests.service import test_base as data_service_test_base
from tensorflow.python.data.experimental.ops import interleave_ops
from tensorflow.python.data.kernel_tests import test_base
from tensorflow.python.data.ops import dataset_ops
from tensorflow.python.framework import combinations
from tensorflow.python.framework import errors
from tensorflow.python.framework import random_seed
from tensorflow.python.ops import math_ops
from tensorflow.python.platform import test


class DistributedEpochTest(data_service_test_base.TestBase,
                           parameterized.TestCase):

  @combinations.generate(test_base.default_test_combinations())
  def testBasic(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    num_elements = 100
    ds = dataset_ops.Dataset.range(num_elements)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(
        ds, list(range(num_elements)), assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testTensorSlices(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    vals = [5, 1, 2, 4]
    ds = dataset_ops.Dataset.from_tensor_slices(vals)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(ds, vals, assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testInterleave(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    elements = [1, 5, 0]
    ds = dataset_ops.Dataset.from_tensor_slices(elements)
    ds = ds.interleave(lambda x: dataset_ops.Dataset.from_tensor_slices([x]))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(ds, elements, assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testParallelInterleave(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    elements = [1, 5, 0]
    ds = dataset_ops.Dataset.from_tensor_slices(elements)
    ds = ds.interleave(
        lambda x: dataset_ops.Dataset.from_tensor_slices([x]),
        num_parallel_calls=dataset_ops.AUTOTUNE)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(ds, elements, assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testFlatMap(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    elements = [1, 5, 0]
    ds = dataset_ops.Dataset.from_tensor_slices(elements)
    ds = ds.flat_map(lambda x: dataset_ops.Dataset.from_tensor_slices([x]))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(ds, elements, assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testRepeat(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    num_repeats = 5
    num_elements = 20
    ds = dataset_ops.Dataset.range(num_elements).repeat(num_repeats)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(
        ds, num_repeats * list(range(num_elements)), assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testForeverRepeat(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    num_elements = 20
    elements_to_read = 1000
    ds = dataset_ops.Dataset.range(num_elements).repeat()
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    get_next = self.getNext(ds)
    results = {}
    for _ in range(elements_to_read):
      val = self.evaluate(get_next())
      if val not in results:
        results[val] = 0
      results[val] += 1
    for i in range(num_elements):
      self.assertGreater(results[i], elements_to_read / num_elements / 2)

  @combinations.generate(test_base.default_test_combinations())
  def testForeverRepeatFewElements(self):
    num_workers = 5
    cluster = data_service_test_base.TestCluster(num_workers=num_workers)
    # Less than the number of workers, so that some workers get zero elements on
    # the first repetition.
    num_elements = 1
    ds = dataset_ops.Dataset.range(num_elements).repeat()
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    get_next = self.getNext(ds)
    for _ in range(20):
      self.assertEqual(self.evaluate(get_next()), 0)

    # Stop all but one worker and check that we can still read.
    for i in range(num_workers - 1):
      cluster.workers[i].stop()
    for _ in range(20):
      self.assertEqual(self.evaluate(get_next()), 0)

  @combinations.generate(test_base.default_test_combinations())
  def testShuffleAndRepeat(self):
    cluster = data_service_test_base.TestCluster(num_workers=2)
    num_repeats = 5
    num_elements = 20
    ds = dataset_ops.Dataset.range(num_elements).shuffle(num_elements).repeat(
        num_repeats)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    self.assertDatasetProduces(
        ds, num_repeats * list(range(num_elements)), assert_items_equal=True)

  @combinations.generate(test_base.default_test_combinations())
  def testZip(self):
    num_elements = 10
    cluster = data_service_test_base.TestCluster(num_workers=1)
    a = dataset_ops.Dataset.range(num_elements)

    ds = dataset_ops.Dataset.zip((a, a))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    self.assertDatasetProduces(
        ds, list(zip(range(num_elements), range(num_elements))))

  @combinations.generate(test_base.default_test_combinations())
  def testNestedZip(self):
    num_elements = 10
    cluster = data_service_test_base.TestCluster(num_workers=1)
    a = dataset_ops.Dataset.range(num_elements)

    ds = dataset_ops.Dataset.zip((a, a))
    ds = dataset_ops.Dataset.zip((a, a, ds, a))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    b = list(range(10))
    self.assertDatasetProduces(ds, list(zip(b, b, zip(b, b), b)))

  @combinations.generate(test_base.default_test_combinations())
  def testImbalancedZip(self):
    smaller_num_elements = 200
    larger_num_elements = 1000

    cluster = data_service_test_base.TestCluster(num_workers=1)
    a = dataset_ops.Dataset.range(smaller_num_elements)
    b = dataset_ops.Dataset.range(larger_num_elements)

    ds = dataset_ops.Dataset.zip((a, b))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    self.assertDatasetProduces(
        ds, list(zip(range(smaller_num_elements), range(smaller_num_elements))))

  @combinations.generate(test_base.default_test_combinations())
  def testImbalancedZipMultiWorker(self):
    smaller_num_elements = 200
    larger_num_elements = 1000
    cluster = data_service_test_base.TestCluster(num_workers=3)
    a = dataset_ops.Dataset.range(smaller_num_elements)
    b = dataset_ops.Dataset.range(larger_num_elements)

    ds = dataset_ops.Dataset.zip((a, b))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    # Cannot assert specific elements because the range datasets are split
    # nondeterministically and may not line up.
    self.assertLen(self.getDatasetOutput(ds), smaller_num_elements)

  @combinations.generate(test_base.default_test_combinations())
  def testZipDifferentRates(self):
    cluster = data_service_test_base.TestCluster(num_workers=3)
    a = dataset_ops.Dataset.range(100)
    b = dataset_ops.Dataset.range(100).filter(
        lambda x: math_ops.equal(x % 10, 0))

    ds = dataset_ops.Dataset.zip((a, b))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    self.assertLen(self.getDatasetOutput(ds), 10)

  @combinations.generate(test_base.default_test_combinations())
  def testZipDifferentRepeats(self):
    cluster = data_service_test_base.TestCluster(num_workers=3)
    a = dataset_ops.Dataset.range(50)
    b = dataset_ops.Dataset.range(10).repeat(10)

    ds = dataset_ops.Dataset.zip((a, b))
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    self.assertLen(self.getDatasetOutput(ds), 50)

  @combinations.generate(test_base.default_test_combinations())
  def testSampleFromDatasets(self):
    cluster = data_service_test_base.TestCluster(num_workers=3)
    random_seed.set_random_seed(1619)
    num_samples = 5000
    rand_probs = np.random.random_sample((5,))
    rand_probs = rand_probs / rand_probs.sum()

    # Use chi-squared test to assert that the observed distribution matches the
    # expected distribution. Based on the implementation in
    # "third_party/tensorflow/python/kernel_tests/multinomial_op_test.py".
    for weights in [[.85, .05, .1], rand_probs, [1.]]:
      classes = len(weights)

      # Create a dataset that samples each integer in `[0, num_datasets)`
      # with probability given by `weights[i]`.
      ds = interleave_ops.sample_from_datasets([
          dataset_ops.Dataset.from_tensors(i).repeat() for i in range(classes)
      ], weights)
      ds = self.make_distributed_dataset(
          ds, cluster, processing_mode="distributed_epoch")
      ds = ds.take(num_samples)

      freqs = np.zeros([classes])
      for v in self.getDatasetOutput(ds):
        freqs[v] += 1

      expected = np.asarray(weights)
      actual = np.asarray(freqs / num_samples)
      diff = actual - expected
      chi2 = np.sum(diff * diff / expected, axis=0)
      self.assertLess(chi2, 1e-2)

  @combinations.generate(
      combinations.times(test_base.default_test_combinations(),
                         combinations.combine(num_workers=[1, 3])))
  def testChooseFromDatasets(self, num_workers):
    cluster = data_service_test_base.TestCluster(num_workers=num_workers)
    words = [b"foo", b"bar", b"baz"]
    datasets = [dataset_ops.Dataset.from_tensors(w).repeat() for w in words]
    choice_array = np.random.randint(3, size=(15,), dtype=np.int64)
    choice_dataset = dataset_ops.Dataset.from_tensor_slices(choice_array)
    ds = interleave_ops.choose_from_datasets(datasets, choice_dataset)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")
    expected = [words[i] for i in choice_array]

    assert_items_equal = (num_workers > 1)
    self.assertDatasetProduces(
        ds, expected, assert_items_equal=assert_items_equal)

  @combinations.generate(
      combinations.times(test_base.default_test_combinations(),
                         combinations.combine(num_workers=[1, 3])))
  def testConcatenate(self, num_workers):
    cluster = data_service_test_base.TestCluster(num_workers=num_workers)
    a = dataset_ops.Dataset.range(100)
    b = dataset_ops.Dataset.range(100, 200)
    ds = a.concatenate(b)
    ds = self.make_distributed_dataset(
        ds, cluster, processing_mode="distributed_epoch")

    assert_items_equal = (num_workers > 1)
    self.assertDatasetProduces(
        ds, list(range(200)), assert_items_equal=assert_items_equal)

  @combinations.generate(test_base.default_test_combinations())
  def testDistributedDataset(self):
    cluster_1 = data_service_test_base.TestCluster(num_workers=1)
    cluster_2 = data_service_test_base.TestCluster(num_workers=1)
    num_sizes = 10
    size_repeats = 5
    numbers = [1 * i for i in range(num_sizes)] * size_repeats
    ds = dataset_ops.Dataset.from_tensor_slices(numbers)
    ds = self.make_distributed_dataset(
        ds, cluster_1, processing_mode="parallel_epochs")
    ds = ds.map(lambda x: x + 1)
    ds = self.make_distributed_dataset(
        ds, cluster_2, processing_mode="distributed_epoch")

    error_regex = ("Cannot create split providers for dataset " +
                   "of type DataServiceDataset")
    with self.assertRaisesRegex(errors.UnimplementedError, error_regex):
      self.getDatasetOutput(ds)


if __name__ == "__main__":
  test.main()