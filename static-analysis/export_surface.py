#!/usr/bin/env python3
"""从 APK 合并 manifest 提取 exported 组件暴露面，输出 JSON。

用法：
    python3 export_surface.py <apk> [-o output.json] [--aapt /path/to/aapt]

aapt 缺省取 $ANDROID_HOME/build-tools 下最新版本。输出结构：
    {
      "package": ...,
      "version_name": ...,
      "components": [
        {
          "name": ..., "type": "activity|activity-alias|service|receiver|provider",
          "exported": true|false|null,   # null = manifest 未显式声明
          "enabled": true|false|null,
          "permission": ...|null,
          "target_activity": ...|null,   # 仅 activity-alias
          "intent_filters": [
            {"actions": [...], "categories": [...],
             "data": [{"scheme": ..., "host": ..., "mimeType": ...}, ...]}
          ]
        }
      ]
    }
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")

_E_LINE = re.compile(r"^(\s*)E: (\S+) \(line=\d+\)")
_A_LINE = re.compile(r"^\s*A: ([\w:.-]+)(?:\(0x[0-9a-f]+\))?=(.*)$")
_RAW = re.compile(r'\(Raw: "(.*)"\)\s*$')
_QUOTED = re.compile(r'^"(.*)"$')
_TYPED = re.compile(r"^\(type 0x([0-9a-f]+)\)(0x[0-9a-f]+)$")


def find_aapt(explicit=None):
    """定位 aapt：显式参数 > $ANDROID_HOME/build-tools 最新版本。"""
    if explicit:
        return explicit if os.path.exists(explicit) else None
    android_home = os.environ.get("ANDROID_HOME")
    if not android_home:
        return None
    candidates = sorted(
        glob.glob(os.path.join(android_home, "build-tools", "*", "aapt"))
    )
    return candidates[-1] if candidates else None


def _parse_attr_value(raw):
    """把 aapt 属性值还原为 Python 值：Raw 字符串 > 引用字符串 > 布尔/整数 > 资源引用。"""
    m = _RAW.search(raw)
    if m:
        return m.group(1)
    value = raw.split(" (Raw:")[0].strip()
    m = _QUOTED.match(value)
    if m:
        return m.group(1)
    m = _TYPED.match(value)
    if m:
        type_code, hexval = m.group(1), int(m.group(2), 16)
        if type_code == "12":  # boolean：0xffffffff = true，0x0 = false
            return hexval != 0
        return hexval
    return value  # @0x7f... 资源引用等，原样保留


def _indent(line):
    return (len(line) - len(line.lstrip())) // 2


class _Node:
    __slots__ = ("tag", "attrs", "children", "depth")

    def __init__(self, tag, depth):
        self.tag = tag
        self.attrs = {}
        self.children = []
        self.depth = depth


def _build_tree(text):
    """把 aapt xmltree 输出解析成节点树，返回根节点列表。"""
    roots = []
    stack = []  # 当前路径上的 _Node
    for line in text.splitlines():
        m = _E_LINE.match(line)
        if m:
            node = _Node(m.group(2), _indent(line))
            while stack and stack[-1].depth >= node.depth:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
            continue
        m = _A_LINE.match(line)
        if m and stack:
            name = m.group(1).split(":", 1)[-1]  # 去掉 android: 前缀
            stack[-1].attrs[name] = _parse_attr_value(m.group(2).strip())
    return roots


def _find(node, tag):
    return [c for c in node.children if c.tag == tag]


def _component_from_node(node):
    comp = {
        "name": node.attrs.get("name"),
        "type": node.tag,
        "exported": node.attrs.get("exported"),
        "enabled": node.attrs.get("enabled"),
        "permission": node.attrs.get("permission"),
        "target_activity": node.attrs.get("targetActivity"),
        "intent_filters": [],
    }
    for f in _find(node, "intent-filter"):
        intent_filter = {
            "actions": [a.attrs.get("name") for a in _find(f, "action")],
            "categories": [c.attrs.get("name") for c in _find(f, "category")],
            "data": [dict(d.attrs) for d in _find(f, "data")],
        }
        comp["intent_filters"].append(intent_filter)
    return comp


def dump_xmltree(apk, aapt):
    """跑 `aapt dump xmltree <apk> AndroidManifest.xml`，返回 xmltree 文本。"""
    return subprocess.run(
        [aapt, "dump", "xmltree", apk, "AndroidManifest.xml"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def parse_xmltree(text):
    """解析 `aapt dump xmltree <apk> AndroidManifest.xml` 的输出。"""
    roots = _build_tree(text)
    manifest = next((n for n in roots if n.tag == "manifest"), None)
    if manifest is None:
        raise ValueError("xmltree 中找不到 manifest 根节点")
    components = []
    for app in _find(manifest, "application"):
        for node in app.children:
            if node.tag in COMPONENT_TAGS:
                components.append(_component_from_node(node))
    return {
        "package": manifest.attrs.get("package"),
        "version_name": manifest.attrs.get("versionName"),
        "components": components,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("apk", help="被测 APK 路径")
    parser.add_argument("-o", "--output", help="输出 JSON 路径（缺省打到 stdout）")
    parser.add_argument("--aapt", help="aapt 路径（缺省自动探测）")
    args = parser.parse_args(argv)

    aapt = find_aapt(args.aapt)
    if not aapt:
        sys.exit("找不到 aapt：请设 --aapt 或 ANDROID_HOME")
    manifest = parse_xmltree(dump_xmltree(args.apk, aapt))
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
