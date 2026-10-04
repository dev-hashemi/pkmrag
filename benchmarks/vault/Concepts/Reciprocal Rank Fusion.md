---
title: Reciprocal Rank Fusion (RRF)
aliases: [RRF]
tags: [algorithm/rrf, information-retrieval]
---
# Reciprocal Rank Fusion (RRF)

## Score Normalization
RRF calculates ranking score as:
`RRF_Score(d) = sum(1.0 / (k + rank(d, system)))` where `k = 60`.

Feeds into [[Hybrid Search]].
#ranking/unsupervised
