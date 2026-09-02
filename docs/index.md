---
layout: default
title: AI FDE Radar
---

# AI FDE Radar

每天从开放互联网筛选最多 20 条高价值 AI 产品、FDE、研究与工程情报。北京时间约 09:15 启动，内容由模型辅助评分与原创转述，所有条目保留原始来源链接。

[查看最新运行指标](metrics/latest.json)

## 每日归档 <a class="rss-icon" href="{{ '/feed-zh.xml' | relative_url }}" aria-label="订阅中文 RSS">RSS</a>

<ul>
  {% assign zh_posts = site.posts | where: "lang", "zh" %}
  {% for post in zh_posts limit:30 %}
    <li>
      <a href="{{ post.url | relative_url }}">{{ post.date | date: "%Y-%m-%d" }} — {{ post.title }}</a>
    </li>
  {% else %}
    <li><em>首次成功运行后会在这里出现日报。</em></li>
  {% endfor %}
</ul>

## 选取原则

- 7/10 质量门槛，最多 20 条，宁缺毋滥。
- 目标比例：海外 12 / 中国 8；AI 产品与 FDE 10 / 技术研究与工程 10。
- Top 5 提供深度解读，其余提供短摘要。
- 事实与分析分开，无法确认原始来源或正文时不做推测性总结。

本项目基于 [Horizon](https://github.com/Thysrael/Horizon) 改造并遵循 MIT License。
