# Copyright (c) 2021 Mobvoi Inc. (authors: Binbin Zhang)
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
# 数据集构造，最终返回一个IterableDataset，每个数据都嵌套添加了一组处理方法

import random

import torch
import torch.distributed as dist
from torch.utils.data import IterableDataset

import wenet.dataset.processor as processor
from wenet.text.base_tokenizer import BaseTokenizer
from wenet.utils.file_utils import read_lists


class Processor(IterableDataset):

    def __init__(self, source, f, *args, **kw):
        assert callable(f)
        #dataset
        self.source = source
        #待使用的处理方法
        self.f = f
        #参数，tuple参数，使用的时候*对应这个，名字不重要
        self.args = args
        #参数，key-value参数，使用的时候**对应这个，名字不重要
        self.kw = kw

    def set_epoch(self, epoch):
        self.source.set_epoch(epoch)

    def __iter__(self):
        """ Return an iterator over the source dataset processed by the
            given processor.
        """
        assert self.source is not None
        assert callable(self.f)
        #调用指定的f函数，处理数据
        return self.f(iter(self.source), *self.args, **self.kw)

    #这个看不出有什么作用，就是把自身再创建个新对象并返回，也没有实际调用
    def apply(self, f):
        assert callable(f)
        return Processor(self, f, *self.args, **self.kw)


class DistributedSampler:

    def __init__(self, shuffle=True, partition=True):
        #epoch是随机种子
        self.epoch = -1
        self.update()
        self.shuffle = shuffle
        self.partition = partition

    def update(self):
        assert dist.is_available()
        #如果是多卡并行，rank和world size由dist获取，否则走默认值
        if dist.is_initialized():
            self.rank = dist.get_rank()
            self.world_size = dist.get_world_size()
        else:
            self.rank = 0
            self.world_size = 1
        #torch来获取当前的workerinfo，以torch结果为优先，多线并行，https://pytorch.org/docs/stable/data.html#torch.utils.data.get_worker_info
        worker_info = torch.utils.data.get_worker_info()
        if worker_info is None:
            self.worker_id = 0
            self.num_workers = 1
        else:
            self.worker_id = worker_info.id
            self.num_workers = worker_info.num_workers
        #返回当前worker对应的信息数据
        return dict(rank=self.rank,
                    world_size=self.world_size,
                    worker_id=self.worker_id,
                    num_workers=self.num_workers)

    def set_epoch(self, epoch):
        self.epoch = epoch

    def sample(self, data):
        """ Sample data according to rank/world_size/num_workers

            Args:
                data(List): input data list

            Returns:
                List: data list after sample
        """
        #将data数据转换为索引数组
        data = list(range(len(data)))
        # TODO(Binbin Zhang): fix this
        # We can not handle uneven data for CV on DDP, so we don't
        # sample data by rank, that means every GPU gets the same
        # and all the CV data
        #如果是partition，则使用rank来切分，而不是worker_id，这里是两种分组模式，有什么区别还不了解，这里使用的是partition
        if self.partition:
            if self.shuffle:
                random.Random(self.epoch).shuffle(data)
            data = data[self.rank::self.world_size]
        #如果不是partition模式，则按照workerid切分数据集
        data = data[self.worker_id::self.num_workers]
        return data


class DataList(IterableDataset):

    def __init__(self, lists, shuffle=True, partition=True):
        self.lists = lists
        self.sampler = DistributedSampler(shuffle, partition)

    def set_epoch(self, epoch):
        self.sampler.set_epoch(epoch)

    def __iter__(self):
        sampler_info = self.sampler.update()
        #生成采样，如果是partition，可以指定shuffle，否则按照workerid或者rank读取当前worker对应的数据列表
        indexes = self.sampler.sample(self.lists)
        for index in indexes:
            # yield dict(src=src)
            data = dict(src=self.lists[index])
            #每一条数据，都赋值rank，workerid等信息
            data.update(sampler_info)
            #https://blog.csdn.net/mieleizhi0522/article/details/82142856 yield方法的解释，这个不是顺序执行的函数，而是一个生成器，外部执行next，这里就会执行一轮
            yield data


def Dataset(data_type,
            data_list_file,
            tokenizer: BaseTokenizer,
            conf,
            partition=True):
    """ Construct dataset from arguments

        We have two shuffle stage in the Dataset. The first is global
        shuffle at shards tar/raw file level. The second is global shuffle
        at training samples level.

        Args:
            data_type(str): raw/shard
            bpe_model(str): model for english bpe part
            partition(bool): whether to do data partition in terms of rank
    """
    assert data_type in ['raw', 'shard']
    #按行读取数据文件
    lists = read_lists(data_list_file)
    shuffle = conf.get('shuffle', True)
    #构造datalist
    dataset = DataList(lists, shuffle=shuffle, partition=partition)
    #两种模式，读取key，text，wav，sample_rates
    if data_type == 'shard':
        dataset = Processor(dataset, processor.url_opener)
        dataset = Processor(dataset, processor.tar_file_and_group)
    else:
        dataset = Processor(dataset, processor.parse_raw)

    #执行tokenize，添加转换后的结果，数据转化为{key, wav, txt, tokens, label, sample_rate}
    dataset = Processor(dataset, processor.tokenize, tokenizer)
    filter_conf = conf.get('filter_conf', {})
    #过滤掉过长或着过短的音频case
    dataset = Processor(dataset, processor.filter, **filter_conf)

    #重采样，重新设定data的wav和采样率
    resample_conf = conf.get('resample_conf', {})
    dataset = Processor(dataset, processor.resample, **resample_conf)

    #wav添加扰动，inplace操作
    speed_perturb = conf.get('speed_perturb', False)
    if speed_perturb:
        dataset = Processor(dataset, processor.speed_perturb)

    #读取特征，一般都是fbank，与mfcc特征可以转换，加入feat元素
    feats_type = conf.get('feats_type', 'fbank')
    assert feats_type in ['fbank', 'mfcc', 'log_mel_spectrogram']
    if feats_type == 'fbank':
        fbank_conf = conf.get('fbank_conf', {})
        dataset = Processor(dataset, processor.compute_fbank, **fbank_conf)
    elif feats_type == 'mfcc':
        mfcc_conf = conf.get('mfcc_conf', {})
        dataset = Processor(dataset, processor.compute_mfcc, **mfcc_conf)
    elif feats_type == 'log_mel_spectrogram':
        log_mel_spectrogram_conf = conf.get('log_mel_spectrogram_conf', {})
        dataset = Processor(dataset, processor.compute_log_mel_spectrogram,
                            **log_mel_spectrogram_conf)

    spec_aug = conf.get('spec_aug', True)
    spec_sub = conf.get('spec_sub', False)
    spec_trim = conf.get('spec_trim', False)
    #频谱增强，inplace操作，替换feat
    if spec_aug:
        spec_aug_conf = conf.get('spec_aug_conf', {})
        dataset = Processor(dataset, processor.spec_aug, **spec_aug_conf)
    #随机代换掉部分数据
    if spec_sub:
        spec_sub_conf = conf.get('spec_sub_conf', {})
        dataset = Processor(dataset, processor.spec_sub, **spec_sub_conf)
    #随机裁剪掉部分尾部数据
    if spec_trim:
        spec_trim_conf = conf.get('spec_trim_conf', {})
        dataset = Processor(dataset, processor.spec_trim, **spec_trim_conf)

    #当数量大于shuffle size的时候，执行shuffle
    if shuffle:
        shuffle_conf = conf.get('shuffle_conf', {})
        dataset = Processor(dataset, processor.shuffle, **shuffle_conf)

    #排序，将长度相当的数据分到一组，sort的阈值要小于shuffle的，否则sort只会在最后一轮触发一次
    sort = conf.get('sort', True)
    if sort:
        sort_conf = conf.get('sort_conf', {})
        dataset = Processor(dataset, processor.sort, **sort_conf)

    #执行batch，如果是static，则按照batch size分组，如果是dynamic，则按照padding后达到frame数量上限为1组，如果是dynamic，需要max_frames_in_batch参数
    batch_conf = conf.get('batch_conf', {})
    dataset = Processor(dataset, processor.batch, **batch_conf)
    #执行padding
    dataset = Processor(dataset, processor.padding)
    return dataset
