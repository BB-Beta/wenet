# Copyright (c) 2021 Shaoshang Qi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy


def override_config(configs, override_list):
    #拷贝一份原始配置，作为最终返回
    new_configs = copy.deepcopy(configs)
    #遍历需要覆盖的配置
    for item in override_list:
        arr = item.split()
        if len(arr) != 2:
            print(f"the overrive {item} format not correct, skip it")
            continue
        #keys应该是一组被分隔符切分的字符串，应该是多个层级，后续如果遇到非叶子节点，则向下跳节点，如果是叶子节点，则做配置覆盖
        keys = arr[0].split('.')
        s_configs = new_configs
        for i, key in enumerate(keys):
            if key not in s_configs:
                print(f"the overrive {item} format not correct, skip it")
            #如果是最后一个key，配置覆盖
            if i == len(keys) - 1:
                param_type = type(s_configs[key])
                if param_type != bool:
                    s_configs[key] = param_type(arr[1])
                else:
                    s_configs[key] = arr[1] in ['true', 'True']
                print(f"override {arr[0]} with {arr[1]}")
            else:
                #跳到下一层级
                s_configs = s_configs[key]
    return new_configs
