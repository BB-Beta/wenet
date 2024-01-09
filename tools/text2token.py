#!/usr/bin/env python3

# Copyright 2017 Johns Hopkins University (Shinji Watanabe)
# Copyright 2021 JD AI Lab. All Rights Reserved. (authors: Lu Fan)
# Copyright 2021 Mobvoi Inc. All Rights Reserved. (Di Wu)
#  Apache 2.0  (http://www.apache.org/licenses/LICENSE-2.0)

from __future__ import print_function
from __future__ import unicode_literals

import argparse
import codecs
import re
import sys

is_python2 = sys.version_info[0] == 2


def exist_or_not(i, match_pos):
    start_pos = None
    end_pos = None
    for pos in match_pos:
        if pos[0] <= i < pos[1]:
            start_pos = pos[0]
            end_pos = pos[1]
            break

    return start_pos, end_pos


def seg_char(sent):
    #由于complie的时候给分隔符加了括号，所以分割后会保留分隔符，这样的话就是按照汉字来切分
    pattern = re.compile(r'([\u4e00-\u9fa5])')
    chars = pattern.split(sent)
    chars = [w for w in chars if len(w.strip()) > 0]
    return chars

def get_parser():
    parser = argparse.ArgumentParser(
        description='convert raw text to tokenized text',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--nchar',
                        '-n',
                        default=1,
                        type=int,
                        help='number of characters to split, i.e., \
                        aabb -> a a b b with -n 1 and aa bb with -n 2')
    parser.add_argument('--skip-ncols',
                        '-s',
                        default=0,
                        type=int,
                        help='skip first n columns')
    parser.add_argument('--space',
                        default='<space>',
                        type=str,
                        help='space symbol')
    parser.add_argument('--bpe-model',
                        '-m',
                        default=None,
                        type=str,
                        help='bpe model for english part')
    parser.add_argument('--non-lang-syms',
                        '-l',
                        default=None,
                        type=str,
                        help='list of non-linguistic symobles,'
                        ' e.g., <NOISE> etc.')
    parser.add_argument('text',
                        type=str,
                        default=False,
                        nargs='?',
                        help='input text')
    parser.add_argument('--trans_type',
                        '-t',
                        type=str,
                        default="char",
                        choices=["char", "phn", "cn_char_en_bpe"],
                        help="""Transcript type. char/phn. e.g., for TIMIT
                             FADG0_SI1279 -
                             If trans_type is char, read from
                             SI1279.WRD file -> "bricks are an alternative"
                             Else if trans_type is phn,
                             read from SI1279.PHN file ->
                             "sil b r ih sil k s aa r er n aa l
                             sil t er n ih sil t ih v sil" """)
    return parser


def main():
    #参数解析
    parser = get_parser()
    args = parser.parse_args()

    #如果指定了非语言信息，则将非语言信息读取到rs中，构造出正则匹配表达式
    rs = []
    if args.non_lang_syms is not None:
        with codecs.open(args.non_lang_syms, 'r', encoding="utf-8") as f:
            nls = [x.rstrip() for x in f.readlines()]
            rs = [re.compile(re.escape(x)) for x in nls]

    #如果bpe model非空，家在sentence piece处理模块
    if args.bpe_model is not None:
        import sentencepiece as spm
        sp = spm.SentencePieceProcessor()
        sp.load(args.bpe_model)

    #打开文本文件
    if args.text:
        f = codecs.open(args.text, encoding="utf-8")
    else:
        f = codecs.getreader("utf-8")(
            sys.stdin if is_python2 else sys.stdin.buffer)

    sys.stdout = codecs.getwriter("utf-8")(
        sys.stdout if is_python2 else sys.stdout.buffer)
    
    #读取每一行，n表示每组的字数
    line = f.readline()
    n = args.nchar
    while line:
        x = line.split()
        print(' '.join(x[:args.skip_ncols]), end=" ")
        a = ' '.join(x[args.skip_ncols:])

        # 对于非语言类信息，查找对应位置，存储到match pos中
        # get all matched positions
        match_pos = []
        for r in rs:
            i = 0
            while i >= 0:
                m = r.search(a, i)
                if m:
                    match_pos.append([m.start(), m.end()])
                    i = m.end()
                else:
                    break

        # 如果存在非语言信息，则将该部分信息作为整体保存为一个char，其余的保存为单个char，这里疑似有问题，a怎么变成list了，后续还怎么split
        if len(match_pos) > 0:
            chars = []
            i = 0
            while i < len(a):
                start_pos, end_pos = exist_or_not(i, match_pos)
                if start_pos is not None:
                    chars.append(a[start_pos:end_pos])
                    i = end_pos
                else:
                    chars.append(a[i])
                    i += 1
            a = chars

        #phn没搞太懂是什么含义，应该是音素标注之类的吧
        if (args.trans_type == "phn"):
            a = a.split(" ")
        elif args.trans_type == "cn_char_en_bpe":
            #cn_char_en_bpe表示汉字按照单个字符，非汉字按照bpe方式切分
            b = seg_char(a)
            a = []
            for j in b:
                # we use "▁" to instead of blanks among english words
                # warning: here is "▁", not "_"
                for l in j.strip().split("▁"):
                    if not l.encode('UTF-8').isalpha():
                        a.append(l)
                    else:
                        for k in sp.encode_as_pieces(l):
                            a.append(k)
        else:
            #char表示按照单个字符分割，参照n参数来做分割
            a = [a[j:j + n] for j in range(0, len(a), n)]

        #合并为一个字符串
        a_flat = []
        for z in a:
            a_flat.append("".join(z))

        #替换掉空格为space符号，如果是按照phn分割，替换sil为space符号
        a_chars = [z.replace(' ', args.space) for z in a_flat]
        if (args.trans_type == "phn"):
            a_chars = [z.replace("sil", args.space) for z in a_chars]
        print(' '.join(a_chars))
        line = f.readline()


if __name__ == '__main__':
    main()
