#!/bin/bash

# Copyright 2017 Xingyu Na
# Apache 2.0
# 根据文件名称作为id，生成id到audio路径，以及id到text的映射文件

. ./path.sh || exit 1;

if [ $# != 2 ]; then
  echo "Usage: $0 <audio-path> <text-path>"
  echo " $0 /export/a05/xna/data/data_aishell/wav /export/a05/xna/data/data_aishell/transcript"
  exit 1;
fi

#参数上一共两个，一个是audio的位置，一个是对应文本的位置
aishell_audio_dir=$1
aishell_text=$2/aishell_transcript_v0.8.txt

#创建data路径下的train，dev，test，tmp四个文件夹
train_dir=data/local/train
dev_dir=data/local/dev
test_dir=data/local/test
tmp_dir=data/local/tmp

mkdir -p $train_dir
mkdir -p $dev_dir
mkdir -p $test_dir
mkdir -p $tmp_dir

# 检查audio和text是否存在
# data directory check
if [ ! -d $aishell_audio_dir ] || [ ! -f $aishell_text ]; then
  echo "Error: $0 requires two directory arguments"
  exit 1;
fi

# 将所有audio的路径输入到tmp下的flish文件里面，并check数量
# find wav audio file for train, dev and test resp.
find $aishell_audio_dir -iname "*.wav" > $tmp_dir/wav.flist
n=`cat $tmp_dir/wav.flist | wc -l`
[ $n -ne 141925 ] && \
  echo Warning: expected 141925 data data files, found $n

# 根据路径上的train，dev，test标识，将数据分别放到对应文件夹下的flish文件里面，并删除tmp文件夹
grep -i "wav/train" $tmp_dir/wav.flist > $train_dir/wav.flist || exit 1;
grep -i "wav/dev" $tmp_dir/wav.flist > $dev_dir/wav.flist || exit 1;
grep -i "wav/test" $tmp_dir/wav.flist > $test_dir/wav.flist || exit 1;

rm -r $tmp_dir

# 
# Transcriptions preparation
for dir in $train_dir $dev_dir $test_dir; do
  echo Preparing $dir transcriptions
  #从flist里面读取所有id输出到utt，id就是文件名称
  sed -e 's/\.wav//' $dir/wav.flist | awk -F '/' '{print $NF}' > $dir/utt.list
  #将文件id与路径一起放到scp all文件中
  paste -d' ' $dir/utt.list $dir/wav.flist > $dir/wav.scp_all
  # 将id和id对应的文本配对输出到transcripts文件中
  tools/filter_scp.pl -f 1 $dir/utt.list $aishell_text > $dir/transcripts.txt
  # 将能与文件配对的id重新整理输出到utt
  awk '{print $1}' $dir/transcripts.txt > $dir/utt.list
  # 将id与audio路径重新配对，输出到scp
  tools/filter_scp.pl -f 1 $dir/utt.list $dir/wav.scp_all | sort -u > $dir/wav.scp
  #对id与文本的对应文件排序并输出
  sort -u $dir/transcripts.txt > $dir/text
done

#将最终结果scp和text两个文件输出到data文件夹下
mkdir -p data/train data/dev data/test

for f in wav.scp text; do
  cp $train_dir/$f data/train/$f || exit 1;
  cp $dev_dir/$f data/dev/$f || exit 1;
  cp $test_dir/$f data/test/$f || exit 1;
done

echo "$0: AISHELL data preparation succeeded"
exit 0;
