#!/bin/bash

# Copyright   2014  Johns Hopkins University (author: Daniel Povey)
#             2017  Xingyu Na
# Apache 2.0
# 主要任务是下载数据压缩包并解压缩

remove_archive=false

if [ "$1" == --remove-archive ]; then
  remove_archive=true
  shift
fi

if [ $# -ne 3 ]; then
  echo "Usage: $0 [--remove-archive] <data-base> <url-base> <corpus-part>"
  echo "e.g.: $0 /export/a05/xna/data www.openslr.org/resources/33 data_aishell"
  echo "With --remove-archive it will remove the archive after successfully un-tarring it."
  echo "<corpus-part> can be one of: data_aishell, resource_aishell."
fi

#这里data是数据根路径，url是下载地址，part是resource和data两个子文件夹，每次传入一个
data=$1
url=$2
part=$3

#是否存在文件夹
if [ ! -d "$data" ]; then
  echo "$0: no such directory $data"
  exit 1;
fi

#检查part参数是否正确
part_ok=false
list="data_aishell resource_aishell"
for x in $list; do
  if [ "$part" == $x ]; then part_ok=true; fi
done
if ! $part_ok; then
  echo "$0: expected <corpus-part> to be one of $list, but got '$part'"
  exit 1;
fi

#检测url是否为空,https://blog.csdn.net/phone1126/article/details/126365546
if [ -z "$url" ]; then
  echo "$0: empty URL base."
  exit 1;
fi

#查看complete文件是否存在，存在则表示已经解压缩过了，结束即可，如果没有，则继续
if [ -f $data/$part/.complete ]; then
  echo "$0: data part $part was already successfully extracted, nothing to do."
  exit 0;
fi

#检查压缩包文件大小是否符合预期
# sizes of the archive files in bytes.
sizes="15582913665 1246920"

if [ -f $data/$part.tgz ]; then
  size=$(/bin/ls -l $data/$part.tgz | awk '{print $5}')
  size_ok=false
  for s in $sizes; do if [ $s == $size ]; then size_ok=true; fi; done
  if ! $size_ok; then
    echo "$0: removing existing file $data/$part.tgz because its size in bytes $size"
    echo "does not equal the size of one of the archives."
    rm $data/$part.tgz
  else
    echo "$data/$part.tgz exists and appears to be complete."
  fi
fi

#如果没有对应的压缩包，则执行下载
if [ ! -f $data/$part.tgz ]; then
  if ! which wget >/dev/null; then
    echo "$0: wget is not installed."
    exit 1;
  fi
  full_url=$url/$part.tgz
  echo "$0: downloading data from $full_url.  This may take some time, please be patient."

  cd $data
  if ! wget --no-check-certificate $full_url; then
    echo "$0: error executing wget $full_url"
    exit 1;
  fi
fi

cd $data

#解压缩
if ! tar -xvzf $part.tgz; then
  echo "$0: error un-tarring archive $data/$part.tgz"
  exit 1;
fi

#创建complete
touch $data/$part/.complete

#对子压缩包解压缩
if [ $part == "data_aishell" ]; then
  cd $data/$part/wav
  for wav in ./*.tar.gz; do
    echo "Extracting wav from $wav"
    tar -zxf $wav && rm $wav
  done
fi

echo "$0: Successfully downloaded and un-tarred $data/$part.tgz"

#如果需要，则删掉总压缩包，看起来没有删掉子压缩包
if $remove_archive; then
  echo "$0: removing $data/$part.tgz file since --remove-archive option was supplied."
  rm $data/$part.tgz
fi

exit 0;
