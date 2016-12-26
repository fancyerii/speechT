# Copyright 2016 Louis Kirsch. All Rights Reserved.
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

import tensorflow as tf
import numpy as np


class Wav2LetterModel:

  def __init__(self, input_size, num_classes,
               learning_rate, max_gradient_norm):
    self.input_size = input_size

    # Define input placeholders
    self.inputs = tf.placeholder(tf.float32, [None, None, input_size], name='inputs')
    self.sequence_lengths = tf.placeholder(tf.int32, [None], name='sequence_lengths')
    self.labels = tf.sparse_placeholder(tf.int32, name='labels')

    def convolution(value, filter_width, stride, input_channels, out_channels):
      filters = tf.Variable(tf.random_normal([filter_width, input_channels, out_channels]))
      convolution_out = tf.nn.conv1d(value, filters, stride, 'SAME', use_cudnn_on_gpu=True)
      convolution_out = tf.nn.relu(convolution_out)
      return convolution_out, out_channels

    # TODO scale up input size of 13 to 250 channels?
    # One striding layer of output size [batch_size, max_time / 2, input_size]
    outputs, channels = convolution(self.inputs, 48, 2, input_size, input_size)

    # 7 layers without striding of output size [batch_size, max_time / 2, input_size]
    for layer_idx in range(7):
      outputs, channels = convolution(outputs, 7, 1, channels, channels)

    # 1 layer with high kernel width and output size [batch_size, max_time / 2, input_size * 8]
    outputs, channels = convolution(outputs, 32, 1, channels, channels * 8)

    # 1 fully connected layer of output size [batch_size, max_time / 2, input_size * 8]
    outputs, channels = convolution(outputs, 1, 1, channels, channels)

    # 1 fully connected layer of output size [batch_size, max_time / 2, num_classes]
    outputs, channels = convolution(outputs, 1, 1, channels, num_classes)

    # transpose logits to size [max_time / 2, batch_size, num_classes]
    logits = tf.transpose(outputs, (1, 0, 2))

    # Define loss and optimizer
    self.cost = tf.nn.ctc_loss(logits, self.labels, self.sequence_lengths // 2)
    self.avg_loss = tf.reduce_mean(self.cost)
    optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
    gvs = optimizer.compute_gradients(self.cost)
    gradients, trainables = zip(*gvs)
    clipped_gradients, norm = tf.clip_by_global_norm(gradients,
                                                     max_gradient_norm)
    self.update = optimizer.apply_gradients(zip(clipped_gradients, trainables))

    # Decoding
    # TODO use beam search here later
    self.decoded = tf.nn.ctc_greedy_decoder(logits, self.sequence_lengths // 2)

    # TODO evaluate model

    # Initializing the variables
    self.init = tf.initialize_all_variables()

  def init_session(self, sess):
    sess.run(self.init)

  def step(self, sess, input_list, label_list):
    """

    Args:
      sess: tensorflow session
      input_list: spectrogram inputs, list of Tensors [time, input_size]
      label_list: identifiers from vocabulary, list of list of int32

    Returns: update, avg_loss

    """
    if len(input_list) != len(label_list):
      raise ValueError('Input list must have same length as label list')

    sequence_lengths = np.array([inp.shape[0] for inp in input_list])
    max_time = sequence_lengths.max()
    input_tensor = np.zeros((len(input_list), max_time, self.input_size))

    # Fill input tensor
    for idx, inp in enumerate(input_list):
      input_tensor[idx, :inp.shape[0], :] = inp

    # Fill label tensor
    label_shape = np.array([len(label_list), max_time], dtype=np.int)
    label_indices = []
    label_values = []
    for labelIdx, label in enumerate(label_list):
      for idIdx, identifier in enumerate(label):
        label_indices.append([labelIdx, idIdx])
        label_values.append(identifier)
    label_indices = np.array(label_indices, dtype=np.int)
    label_values = np.array(label_values, dtype=np.int)

    input_feed = {
      self.inputs: input_tensor,
      self.sequence_lengths: sequence_lengths,
      self.labels: tf.SparseTensorValue(label_indices, label_values, label_shape)
    }

    output_feed = [
      self.update,
      self.avg_loss
    ]

    return sess.run(output_feed, feed_dict=input_feed)